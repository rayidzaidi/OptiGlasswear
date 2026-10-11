import cv2
import numpy as np
import asyncio
import websockets
import json
import threading
import time
import requests
from aiohttp import web
from ultralytics import YOLO

CAMERA_IP_FILE = "camera_ip.txt"
DEFAULT_IP = "10.119.226.19"


def load_saved_ip():
    try:
        with open(CAMERA_IP_FILE, "r") as f:
            saved = f.read().strip()
            if saved:
                return saved
    except Exception:
        pass
    return DEFAULT_IP


current_camera_ip = load_saved_ip()
URL = f"http://{current_camera_ip}/cam-hi.jpg"
CONF_THRESHOLD = 0.35
JPEG_QUALITY = 80
DETECTION_INTERVAL = 1.0  # Detect once per second for maximal streaming FPS

print(f"[*] Starting OPTIGLASSWEAR Engine with Camera IP: {current_camera_ip}", flush=True)
print("[*] Loading YOLO11 AI model...", flush=True)
model = YOLO("yolo11n.pt")
# Pre-warm model
model(np.zeros((320, 320, 3), dtype=np.uint8), verbose=False)
print("[*] YOLO11 model warmed up and ready!", flush=True)

connected_clients = set()

# Thread-safe shared states
state_lock = threading.Lock()
latest_frame = None
latest_frame_id = 0
last_frame_captured_at = 0

detections_lock = threading.Lock()
cached_boxes = []      # list of (x1, y1, x2, y2, label)
cached_objects = []    # list of unique object names
last_detection_time = 0


# ---------- Thread 1: Continuous Camera Ingestion ----------
def capture_loop():
    global latest_frame, latest_frame_id, last_frame_captured_at
    session = requests.Session()

    while True:
        try:
            r = session.get(URL, timeout=1.8)
            if r.status_code == 200 and len(r.content) > 1000:
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    # Invert 180° for proper orientation
                    img = cv2.rotate(img, cv2.ROTATE_180)
                    with state_lock:
                        latest_frame = img
                        latest_frame_id += 1
                        last_frame_captured_at = time.time()
                time.sleep(0.02)  # 20ms breathing room for ESP32 lwIP stack
            else:
                time.sleep(0.5)
        except Exception:
            time.sleep(1.2)  # Gentle 1.2s backoff on disconnect/RST so ESP32 socket recovers


# ---------- Thread 2: Periodic AI Detection Worker (1 per second) ----------
def detection_worker():
    global cached_boxes, cached_objects, last_detection_time

    while True:
        now = time.time()
        time.sleep(max(0.05, DETECTION_INTERVAL - (time.time() - now)))

        with state_lock:
            if latest_frame is None:
                continue
            frame_to_process = latest_frame.copy()

        try:
            results = model(frame_to_process, conf=CONF_THRESHOLD, verbose=False)
            new_boxes = []
            new_objects = []

            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    name = model.names[cls_id]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    label = f"{name} {int(conf * 100)}%"

                    new_boxes.append((x1, y1, x2, y2, label))
                    if name not in new_objects:
                        new_objects.append(name)

            with detections_lock:
                cached_boxes = new_boxes
                cached_objects = new_objects
                last_detection_time = time.time()
        except Exception:
            pass


# ---------- Fast Frame Compositor & Streamer ----------
def composite_and_encode(frame):
    with detections_lock:
        boxes_copy = list(cached_boxes)
        objects_copy = list(cached_objects)

    for x1, y1, x2, y2, label in boxes_copy:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (16, 185, 129), 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), (16, 185, 129), -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buffer.tobytes(), json.dumps({
        "objects": objects_copy,
        "timestamp": time.time()
    })


async def send_to(ws, frame_bytes, json_data):
    try:
        if isinstance(ws, web.WebSocketResponse):
            if not ws.closed:
                await ws.send_bytes(frame_bytes)
                await ws.send_str(json_data)
        else:
            if not ws.closed:
                await ws.send(frame_bytes)
                await ws.send(json_data)
    except Exception:
        connected_clients.discard(ws)


async def send_frames():
    loop = asyncio.get_running_loop()
    last_sent_id = 0

    while True:
        if not connected_clients:
            await asyncio.sleep(0.04)
            continue

        with state_lock:
            frame = latest_frame
            fid = latest_frame_id

        if frame is None or fid == last_sent_id:
            await asyncio.sleep(0.005)
            continue
        last_sent_id = fid

        try:
            frame_bytes, json_data = await loop.run_in_executor(None, composite_and_encode, frame.copy())
            await asyncio.gather(
                *(send_to(ws, frame_bytes, json_data) for ws in list(connected_clients)),
                return_exceptions=True
            )
        except Exception:
            pass


# Standalone WebSocket handler (port 8765)
async def ws_handler(websocket, *args):
    connected_clients.add(websocket)
    print(f"[*] Standalone client connected. Total: {len(connected_clients)}", flush=True)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"[*] Standalone client disconnected. Total: {len(connected_clients)}", flush=True)


# aiohttp Integrated WebSocket handler (port 8080 /ws)
async def aiohttp_ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=15)
    await ws.prepare(request)
    connected_clients.add(ws)
    print(f"[*] /ws client connected. Total: {len(connected_clients)}", flush=True)
    try:
        async for msg in ws:
            pass
    finally:
        connected_clients.discard(ws)
        print(f"[*] /ws client disconnected. Total: {len(connected_clients)}", flush=True)
    return ws


# HTTP Endpoints
async def index_handler(request):
    return web.FileResponse("index.html")


async def broadcast_event(event):
    data = json.dumps({"event": event})
    for ws in list(connected_clients):
        try:
            if isinstance(ws, web.WebSocketResponse):
                if not ws.closed:
                    await ws.send_str(data)
            else:
                if not ws.closed:
                    await ws.send(data)
        except Exception:
            connected_clients.discard(ws)


async def call_handler(request):
    await broadcast_event("CALL")
    return web.Response(text="CALL event sent")


async def sos_handler(request):
    await broadcast_event("SOS")
    return web.Response(text="SOS event sent")


async def logo_handler(request):
    return web.FileResponse("logo.png")


async def favicon_handler(request):
    return web.FileResponse("favicon.png")


async def manifest_handler(request):
    return web.FileResponse("manifest.json")


async def get_ip_handler(request):
    return web.json_response({
        "ip": current_camera_ip,
        "url": URL
    })


async def set_ip_handler(request):
    global current_camera_ip, URL
    try:
        data = await request.json()
        new_ip = data.get("ip", "").strip()
        if new_ip:
            new_ip = new_ip.replace("http://", "").replace("https://", "").split("/")[0]
            current_camera_ip = new_ip
            URL = f"http://{current_camera_ip}/cam-hi.jpg"
            if data.get("save", True):
                try:
                    with open(CAMERA_IP_FILE, "w") as f:
                        f.write(new_ip)
                except Exception:
                    pass
            print(f"[*] Camera IP dynamically set to: {new_ip} -> {URL}", flush=True)
            return web.json_response({"success": True, "ip": new_ip, "url": URL})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    return web.json_response({"success": False, "error": "Invalid IP provided"}, status=400)


async def status_handler(request):
    camera_fresh = (time.time() - last_frame_captured_at) < 3.0
    return web.json_response({
        "status": "online",
        "camera_ip": current_camera_ip,
        "camera_url": URL,
        "camera_fresh": camera_fresh,
        "last_frame_id": latest_frame_id,
        "connected_clients": len(connected_clients),
        "uptime": time.time()
    })


async def main():
    await websockets.serve(ws_handler, "0.0.0.0", 8765, ping_interval=20, ping_timeout=20)
    print("[*] Standalone WebSocket listening on ws://0.0.0.0:8765", flush=True)

    app = web.Application()
    app.add_routes([
        web.get("/", index_handler),
        web.get("/ws", aiohttp_ws_handler),
        web.get("/logo.png", logo_handler),
        web.get("/favicon.png", favicon_handler),
        web.get("/favicon.ico", favicon_handler),
        web.get("/manifest.json", manifest_handler),
        web.get("/call", call_handler),
        web.get("/sos", sos_handler),
        web.get("/api/get-ip", get_ip_handler),
        web.post("/api/set-ip", set_ip_handler),
        web.get("/api/status", status_handler)
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    print("[*] Web server ready on http://0.0.0.0:8080 (and WSS on /ws)", flush=True)

    # Start dedicated ingestion and detection background threads
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=detection_worker, daemon=True).start()
    await send_frames()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer terminated.", flush=True)