import time
from pathlib import Path
from flask import Flask, request, Response, jsonify, send_from_directory, redirect, url_for, render_template
from werkzeug.utils import secure_filename
import cv2, numpy as np

app = Flask(__name__)
app.secret_key = "123" 

# пути
base = Path.cwd()
uploadDir = base / "uploads"; uploadDir.mkdir(exist_ok=True)
exportDir = base / "exports"; exportDir.mkdir(exist_ok=True)

# детектор лиц
faceCascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


videoFile = None         
blurPower = 1.0         
normMasks = []   

def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)

def blurRect(img, x, y, w, h, s):
    roi = img[y:y+h, x:x+w]
    if roi.size == 0: return
    k = int(max(3, (max(w, h)//7) * s)) | 1
    k = min(k, 99)
    img[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (k, k), 0)

def normToPixels(frame, masks):
    h, w = frame.shape[:2]
    out = []
    for nx, ny, nw, nh in masks:
        x = int(clamp(nx, 0, 1) * w)
        y = int(clamp(ny, 0, 1) * h)
        ww = int(clamp(nw, 0.001, 1 - nx) * w)
        hh = int(clamp(nh, 0.001, 1 - ny) * h)
        out.append((x, y, ww, hh))
    return out

def makeResult(inPath, outPath, s=1.0, masks=None):
    masks = masks or []
    cap = cv2.VideoCapture(str(inPath))
    if not cap.isOpened(): return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(str(outPath), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    while True:
        ok, frame = cap.read()
        if not ok: break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for (x, y, fw, fh) in faceCascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40)):
            blurRect(frame, x, y, fw, fh, s)
        for (x, y, ww, hh) in normToPixels(frame, masks):
            blurRect(frame, x, y, ww, hh, s)
        out.write(frame)
    cap.release(); out.release()
    return True

def makeFrame(imgBytes):
    return b"--frame\nContent-Type: image/jpeg\n\n" + imgBytes + b"\n"

def streamMjpeg():
    if not videoFile:
        img = np.zeros((240, 320, 3), np.uint8)
        ok, jpeg = cv2.imencode(".jpg", img)
        buf = jpeg.tobytes() if ok else b""
        while True:
            yield makeFrame(buf)
            time.sleep(0.1)
    cap = cv2.VideoCapture(videoFile)
    while True:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if not ok: break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for (x, y, fw, fh) in faceCascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40)):
            blurRect(frame, x, y, fw, fh, blurPower)
        for (x, y, ww, hh) in normToPixels(frame, normMasks):
            blurRect(frame, x, y, ww, hh, blurPower)
        ok, jpeg = cv2.imencode(".jpg", frame)
        if ok:
            yield makeFrame(jpeg.tobytes())
        time.sleep(0.03)

# маршруты 
@app.route("/")
def page():
    return render_template("index.html")

@app.post("/upload")
def upload():
    global videoFile
    f = request.files.get("video")
    if not f: return redirect(url_for("page"))
    name = secure_filename(f.filename or "video.mp4")
    path = uploadDir / name
    f.save(path)
    videoFile = str(path)
    return redirect(url_for("page"))

@app.route("/video_feed")
def videoFeed():
    return Response(streamMjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.post("/set_params")
def setParams():
    global blurPower
    data = request.get_json(force=True, silent=True) or {}
    try:
        blurPower = float(data.get("blur_strength", blurPower))
        blurPower = clamp(blurPower, 0.4, 6.0)
    except:
        pass
    return "", 204

@app.post("/set_masks")
def setMasks():
    global normMasks
    data = request.get_json(force=True, silent=True) or {}
    clean = []
    for r in data.get("masks", []):
        try:
            x = float(r["x"]); y = float(r["y"])
            w = float(r["w"]); h = float(r["h"])
            clean.append((x, y, w, h))
        except:
            continue
    normMasks = clean
    return "", 204

@app.post("/save")
def saveVideo():
    if not videoFile:
        return jsonify(ok=False, error="no video"), 400
    outName = f"result_{int(time.time())}.mp4"
    outPath = exportDir / outName
    ok = makeResult(videoFile, outPath, s=blurPower, masks=normMasks)
    if not ok: return jsonify(ok=False), 500
    return jsonify(ok=True, download_url=url_for("getFile", filename=outName))

@app.route("/exports/<path:filename>")
def getFile(filename):
    return send_from_directory(str(exportDir), filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=True)

