from pathlib import Path
import time
from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, render_template, make_response
from werkzeug.utils import secure_filename
import cv2
import numpy as np

app = Flask(__name__)

# директории для входных и выходных файлов
BASE = Path.cwd()
UPLOAD_DIR = BASE / "uploads"; UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR = BASE / "exports"; EXPORT_DIR.mkdir(exist_ok=True)

# общее состояние приложения
state = {
    "videoPath": None,
    "blurStrength": 1.0,
    "autoFace": True,
    "paused": False, 
    "normMasks": [],
    "_cap": None, 
    "_lastFrame": None,  
    "_frame_idx": 0, 
    "_tracks": [] 
}

# каскад Хаара
faceCascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# параметры стабилизации и частоты детекции
_DET_EVERY   = 5  
_MAX_MISSED  = 8  
_SMOOTH_A    = 0.25
_IOU_THR     = 0.30 
_PAD         = 0.15 
_ROUND       = 4   

# открывает выдеопоток дл текущего файла
def open_cap():
    if state["_cap"] is None and state["videoPath"]:
        cap = cv2.VideoCapture(str(state["videoPath"]))
        state["_cap"] = cap if cap.isOpened() else None
    return state["_cap"]

#возвращает следующий кадр
def read_frame():
    cap = open_cap()
    if cap is None:
        state["_lastFrame"] = np.zeros((360, 640, 3), np.uint8)
        return state["_lastFrame"]

    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
        if not ok:
            frame = np.zeros((360, 640, 3), np.uint8)

    state["_lastFrame"] = frame
    state["_frame_idx"] += 1
    return frame

def clamp(v, lo, hi):
    return max(lo, min(v, hi))

def norm_to_pixels(frame, masks):
    h, w = frame.shape[:2]
    out = []
    for x, y, ww, hh in masks:
        X  = int(clamp(x,  0.0, 1.0) * w)
        Y  = int(clamp(y,  0.0, 1.0) * h)
        WW = int(clamp(ww, 0.001, 1.0) * w)
        HH = int(clamp(hh, 0.001, 1.0) * h)
        out.append((X, Y, WW, HH))
    return out

# гауссово размытие
def blur_rect(img, x, y, w, h, strength):
    if w < 1 or h < 1:
        return
    size = max(w, h) // 7
    k = int(size * float(strength))
    k = (k // 2) * 2 + 1
    k = int(clamp(k, 3, 99))
    if k % 2 == 0:
        k += 1
    roi = img[y:y+h, x:x+w]
    img[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (k, k), 0)

def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax+aw, bx+bw), min(ay+ah, by+bh)
    inter = max(0, x2-x1) * max(0, y2-y1)
    ua = aw*ah + bw*bh - inter
    return inter / ua if ua > 0 else 0.0

def _ema_box(old, new, a=_SMOOTH_A):
    ox, oy, ow, oh = old
    nx, ny, nw, nh = new
    return (ox*(1-a)+nx*a, oy*(1-a)+ny*a, ow*(1-a)+nw*a, oh*(1-a)+nh*a)

# метод Хаара и получение списка масок
def _detect_faces(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = faceCascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(40, 40))
    return [(float(x), float(y), float(w), float(h)) for (x, y, w, h) in faces]

# рамки
def _pad_and_clip(box, W, H, pad=_PAD, rnd=_ROUND):
    x, y, w, h = box
    dx, dy = w*pad, h*pad
    x = max(0.0, x - dx); y = max(0.0, y - dy)
    w = min(W - x, w + 2*dx); h = min(H - y, h + 2*dy)

    xi = int(round(x / rnd) * rnd)
    yi = int(round(y / rnd) * rnd)
    wi = int(round(w / rnd) * rnd)
    hi = int(round(h / rnd) * rnd)

    xi = int(clamp(xi, 0, max(0, W-1)))
    yi = int(clamp(yi, 0, max(0, H-1)))
    wi = max(1, min(wi, W - xi))
    hi = max(1, min(hi, H - yi))
    return (xi, yi, wi, hi)

def _update_face_tracks(img):
    H, W = img.shape[:2]
    tracks = state["_tracks"]

    need_detect = (state["_frame_idx"] % _DET_EVERY == 0) or (len(tracks) == 0)
    if need_detect:
        detections = _detect_faces(img)

        for t in tracks:
            t["missed"] += 1

        for det in detections:
            best_iou, best_idx = 0.0, -1
            for i, t in enumerate(tracks):
                iou = _iou(det, t["bbox"])
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_iou >= _IOU_THR and best_idx >= 0:
                tracks[best_idx]["bbox"] = _ema_box(tracks[best_idx]["bbox"], det)
                tracks[best_idx]["missed"] = 0
            else:
                tracks.append({"bbox": det, "missed": 0})

        tracks = [t for t in tracks if t["missed"] <= _MAX_MISSED]
        state["_tracks"] = tracks

    return [_pad_and_clip(t["bbox"], W, H) for t in state["_tracks"]]

# закрытие текущего потока
def reset_cap():
    if state["_cap"] is not None:
        try:
            state["_cap"].release()
        except:
            pass
    state["_cap"] = None
    state["_lastFrame"] = None
    state["_frame_idx"] = 0
    state["_tracks"] = []

# маршруты
# интерфейс главный
@app.route("/")
def index():
    return render_template("index.html")

# принимает видео 
@app.post("/upload")
def upload():
    file = request.files.get("video")
    if not file:
        return redirect(url_for("index"))

    filename = secure_filename(file.filename) if file.filename else f"video_{int(time.time())}.mp4"
    path = UPLOAD_DIR / filename
    file.save(path)

    state["videoPath"] = str(path)
    state["normMasks"] = []
    reset_cap()

    return redirect(url_for("index"))

# текущий кадр предпросмотра JPEG
@app.route("/snapshot")
def snapshot():
    try:
        frame = render_preview_frame()
    except Exception:
        frame = np.zeros((360, 640, 3), np.uint8)

    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    data = buffer.tobytes() if ok else b""

    resp = make_response(data)
    resp.headers.update({
        "Content-Type": "image/jpeg",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })
    return resp

# обновлние параметров
@app.post("/set_params")
def setParams():
    d = request.get_json(silent=True) or {}
    try:
        bs = float(d.get("blurStrength", state["blurStrength"]))
        state["blurStrength"] = clamp(bs, 0.4, 6.0)
    except:
        pass

    if "autoFace" in d:
        state["autoFace"] = bool(d["autoFace"])
        if not state["autoFace"]:
            state["_tracks"] = []
    return "", 204

# ручные маски
@app.post("/set_masks")
def setMasks():
    d = request.get_json(silent=True) or {}
    masks = d.get("masks", [])
    clean = []
    for r in masks:
        if not all(k in r for k in ("x", "y", "w", "h")):
            continue
        try:
            clean.append((float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"])))
        except:
            continue
    state["normMasks"] = clean
    return "", 204

# пауза
@app.post("/toggle_pause")
def togglePause():
    d = request.get_json(silent=True) or {}
    state["paused"] = bool(d.get("paused", False))
    return "", 204

# делает кадр предпросмотра
def render_preview_frame():
    frame = state["_lastFrame"] if (state["paused"] and state["_lastFrame"] is not None) else read_frame()
    img = frame.copy()

    if state["autoFace"]:
        for (x, y, w, h) in _update_face_tracks(img):
            blur_rect(img, x, y, w, h, state["blurStrength"])

    for (x, y, w, h) in norm_to_pixels(img, state["normMasks"]):
        blur_rect(img, x, y, w, h, state["blurStrength"])

    return img

# полная обработка
def process_video(src_path: Path, dst_path: Path, strength: float, norm_masks, use_auto: bool) -> bool:
    cap = cv2.VideoCapture(str(src_path))
    if not cap.isOpened():
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out = cv2.VideoWriter(str(dst_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

    tracks = []
    frame_idx = 0

    def upd_tracks_local(img):
        nonlocal tracks, frame_idx
        Hh, Ww = img.shape[:2]
        need_detect = (frame_idx % _DET_EVERY == 0) or (len(tracks) == 0)
        if not (use_auto and need_detect):
            return [_pad_and_clip(t["bbox"], Ww, Hh) for t in tracks]

        dets = _detect_faces(img)

        for t in tracks:
            t["missed"] += 1

        for det in dets:
            best_iou, best_idx = 0.0, -1
            for i, t in enumerate(tracks):
                iou = _iou(det, t["bbox"])
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_iou >= _IOU_THR and best_idx >= 0:
                tracks[best_idx]["bbox"] = _ema_box(tracks[best_idx]["bbox"], det)
                tracks[best_idx]["missed"] = 0
            else:
                tracks.append({"bbox": det, "missed": 0})

        tracks = [t for t in tracks if t["missed"] <= _MAX_MISSED]
        return [_pad_and_clip(t["bbox"], Ww, Hh) for t in tracks]

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1

        if use_auto:
            for (x, y, w, h) in upd_tracks_local(frame):
                blur_rect(frame, x, y, w, h, strength)

        for (x, y, w, h) in norm_to_pixels(frame, norm_masks):
            blur_rect(frame, x, y, w, h, strength)

        out.write(frame)

    cap.release()
    out.release()
    return True

# экспорт
@app.post("/save")
def saveVideo():
    if not state["videoPath"]:
        return jsonify(ok=False, error="noVideo"), 400

    name = f"result_{int(time.time())}.mp4"
    dst = EXPORT_DIR / name

    ok = process_video(
        src_path=Path(state["videoPath"]),
        dst_path=dst,
        strength=state["blurStrength"],
        norm_masks=state["normMasks"],
        use_auto=state["autoFace"]
    )

    if ok:
        return jsonify(ok=True, downloadUrl=url_for("download_file", filename=name))
    else:
        return jsonify(ok=False, error="processingFailed"), 500

# скачивание
@app.route("/exports/<path:filename>")
def download_file(filename):
    return send_from_directory(str(EXPORT_DIR), filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=True)
