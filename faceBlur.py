import cv2
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk


videoPath = None
def loadFile():
    global videoPath
    path = filedialog.askopenfilename(title="выберите видео")
    if path:
        videoPath = path
        print("Выбран файл:", videoPath)
    else:
        print("Файл не выбран")

savePath = None
def saveFile():
    global savePath
    path = filedialog.asksaveasfilename(title="Сохранить видео")
    if path:
        savePath = path
        print("Файл для сохранения:", savePath)
    else:
        print("Сохранение отменено")

def showFrame(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pilImg = Image.fromarray(rgb).resize((800, 450))
    imgTk = ImageTk.PhotoImage(pilImg)
    videoArea.imgtk = imgTk
    videoArea.config(image = imgTk)

def start():
    global videoPath
    if not videoPath:
        print("Выберите видео")
        return
    fileName = videoPath
    cap = cv2.VideoCapture(fileName)
    if not cap.isOpened():
        print("Не удалось открыть файл:", fileName)
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Создаем обьект записи 
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    global savePath
    if savePath:
        outputName = savePath
    else:
        outputName = "output.mp4"
    out = cv2.VideoWriter(outputName, fourcc, fps, (width, height))
    if not out.isOpened():
        print("Не удалось создать файл для записи:")
        cap.release()
        return

    # Каскад Хаара
    faceCascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if faceCascade.empty():
        print("Не удалось загрузить каскад лиц")
        
        out.release()
        return

    blurStrength = 1.0
    blurStep = 0.2
    blurMin = 0.4
    blurMax = 6.0

    arrayMask = []
    drawing = False
    ix = -1
    iy = -1
    cur = None
    paused = False

    def mouse(event, x, y, flags, param):
        nonlocal drawing, ix, iy, cur, arrayMask, paused
        if not paused:
            return 
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            ix, iy = x, y
            cur = None
        elif event == cv2.EVENT_MOUSEMOVE and drawing:
            x1, y1 = min(ix, x), min(iy, y)
            x2, y2 = max(ix, x), max(iy, y)
            cur = (x1, y1, x2 - x1, y2 - y1)
        elif event == cv2.EVENT_LBUTTONUP and drawing:
            drawing = False
            x1, y1 = min(ix, x), min(iy, y)
            x2, y2 = max(ix, x), max(iy, y)
            w, h = x2 - x1, y2 - y1
            if w > 2 and h> 2:
                arrayMask.append((x1, y1, w, h))
            cur = None

    cv2.namedWindow("Preview", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Preview", mouse)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = faceCascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))

        for (x, y, w, h) in faces:
            roi = frame[y:y+h, x:x+w]
            base = max(3, max(w, h) // 7)
            k = int(base * blurStrength)
            k = max(3, min(k, 99)) | 1
            frame[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (k, k), 0)

        for (mx, my, mw, mh) in arrayMask:
            x1 = max(0, mx); y1 = max(0, my)
            x2 = min(width, mx + mw); y2 = min(height, my + mh)
            if x2 <= x1 or y2 <= y1:
                continue
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            base = max(3, max(mw, mh) // 7)
            k = int(base * blurStrength)
            k = max(3, min(k, 99)) | 1
            frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)



        if not paused:
            out.write(frame)
    
        preview = frame.copy()
        for (x, y, w, h) in arrayMask:
            cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 255), 2)

        if cur is not None:
            x, y, w, h = cur
            cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 180, 255), 2)

        cv2.imshow("Preview", preview)
        showFrame(frame)               
        root.update() 

        # Подключаем клавиши
        key = cv2.waitKey(1) & 0xFF

        if key in (ord('+'), ord('=')):
            blurStrength = min(blurMax, blurStrength + blurStep)
        elif key in (ord('-'), ord('_')):
            blurStrength = max(blurMin, blurStrength - blurStep)
        elif key == ord('p'):
            paused = not paused
        elif key == ord('c'):
            arrayMask.clear()
        elif key == ord('u'):
            if arrayMask:
                arrayMask.pop()
        elif key in (ord('q'), ord('\x1b')):
            break
        
    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print("Готово")


root = tk.Tk()
root.title("Face Blur")
root.geometry("960x600") 
top = tk.Frame(root, padx=8, pady=8)
top.pack(side=tk.TOP, fill=tk.X)

buttonLoad = tk.Button(top, text="Загрузить файл", command = loadFile)
buttonLoad.pack(side = tk.LEFT, padx=6)
buttonStart = tk.Button(top, text = "Старт", command = start)
buttonStart.pack(side = tk.LEFT, padx=6)
buttonSave = tk.Button(top, text = "Сохранить", command = saveFile)
buttonSave.pack(side = tk.LEFT, padx = 6)
videoArea = tk.Label(root, bg = "black")
videoArea.pack(side = tk.TOP, fill = tk.BOTH, expand = True)
root.mainloop() 

