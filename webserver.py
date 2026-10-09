import cv2
import urllib.request
import numpy as np
import asyncio
import websockets
import json
from aiohttp import web

# --- Configuration ---
url = "http://192.168.43.82/cam-hi.jpg"

# Load COCO classes
classFile = "coco.names"
try:
    with open(classFile, "rt") as f:
        classNames = f.read().rstrip("\n").split("\n")
except FileNotFoundError:
    print(f"Error: {classFile} not found.")
    exit()

# Load model
configPath = "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt"
weightsPath = "frozen_inference_graph.pb"
try:
    net = cv2.dnn_DetectionModel(weightsPath, configPath)
except Exception as e:
    print(f"Error loading model files: {e}")
    exit()

net.setInputSize(320, 320)
net.setInputScale(1.0 / 127.5)
net.setInputMean((127.5, 127.5, 127.5))
net.setInputSwapRB(True)

connected_clients = set()

async def send_frames():
    while True:
        try:
            if not connected_clients:
                await asyncio.sleep(0.1)
                continue

            imgResp = urllib.request.urlopen(url, timeout=5)
            imgNp = np.array(bytearray(imgResp.read()), dtype=np.uint8)
            img = cv2.imdecode(imgNp, -1)
            if img is None:
                await asyncio.sleep(1)
                continue

            img = cv2.rotate(img, cv2.ROTATE_180)

            classIds, confs, bbox = net.detect(img, confThreshold=0.5)
            detected_objects = []

            if len(classIds) != 0:
                for classId, confidence, box in zip(classIds.flatten(), confs.flatten(), bbox):
                    if 0 < classId <= len(classNames):
                        obj_name = classNames[classId - 1]
                        detected_objects.append(obj_name)
                        cv2.rectangle(img, box, (0, 255, 0), 2)
                        cv2.putText(img, obj_name, (box[0], box[1] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_bytes = buffer.tobytes()
            json_data = json.dumps({"objects": detected_objects})

            send_tasks = []
            for ws in list(connected_clients):
                try:
                    send_tasks.append(ws.send(frame_bytes))
                    send_tasks.append(ws.send(json_data))
                except:
                    connected_clients.discard(ws)

            if send_tasks:
                await asyncio.gather(*send_tasks, return_exceptions=True)

        except Exception as e:
            if "Passing coroutines" not in str(e):
                print(f"Frame processing/sending error: {e}")

        await asyncio.sleep(0.01)

async def ws_handler(websocket, path=None):
    print(f"Client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            print(f"📥 Received: {message}")
            print("⚠ Event handling moved to HTTP endpoints")
        await websocket.wait_closed()
    finally:
        print(f"Client disconnected: {websocket.remote_address}")
        connected_clients.remove(websocket)

# HTTP endpoints
async def call_handler(request):
    print("📞 Emergency CALL triggered via HTTP")
    json_data = json.dumps({"event": "CALL"})
    await asyncio.gather(*(ws.send(json_data) for ws in connected_clients), return_exceptions=True)
    return web.Response(text="CALL event sent")

async def sos_handler(request):
    print("🚨 SOS triggered via HTTP")
    json_data = json.dumps({"event": "SOS"})
    await asyncio.gather(*(ws.send(json_data) for ws in connected_clients), return_exceptions=True)
    return web.Response(text="SOS event sent")

async def main():
    # Start WebSocket server
    ws_server = await websockets.serve(ws_handler, "0.0.0.0", 8765, ping_interval=None)
    print("🚀 WebSocket server started at ws://0.0.0.0:8765")

    # Start HTTP server
    app = web.Application()
    app.add_routes([web.get("/call", call_handler), web.get("/sos", sos_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 HTTP server started at http://0.0.0.0:8080")

    # Run frame sending loop forever
    await send_frames()  # This will run indefinitely

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
