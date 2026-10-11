import cv2
import urllib.request
import numpy as np
from ultralytics import YOLO

# Object detection desktop viewer with Ultralytics YOLO
url = 'http://10.119.226.19/cam-hi.jpg'
winName = 'ESP32-CAM AI Detection (YOLO)'
cv2.namedWindow(winName, cv2.WINDOW_NORMAL)

print("Loading YOLO AI model...")
model = YOLO("yolo11n.pt")
print("Model loaded! Press ESC on video window to exit.")

while True:
    try:
        imgResponse = urllib.request.urlopen(url, timeout=2)
        imgNp = np.array(bytearray(imgResponse.read()), dtype=np.uint8)
        img = cv2.imdecode(imgNp, -1)
        if img is None:
            continue

        # Rotate 180 degrees
        img = cv2.rotate(img, cv2.ROTATE_180)

        # YOLO inference
        results = model(img, conf=0.35, verbose=False)
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                name = model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 128), 2)
                label = f"{name} {int(conf * 100)}%"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), (0, 200, 100), -1)
                cv2.putText(img, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        cv2.imshow(winName, img)
    except Exception as e:
        pass

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == 27:
        break

cv2.destroyAllWindows()
