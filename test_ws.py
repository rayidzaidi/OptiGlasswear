import asyncio
import websockets

async def main():
    print("Connecting to wss://composed-anthropology-responded-gis.trycloudflare.com/ws...")
    try:
        async with websockets.connect("wss://composed-anthropology-responded-gis.trycloudflare.com/ws") as ws:
            print("Connected! Waiting for message...")
            for i in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print(f"Message {i+1} received! Type: {type(msg)}, len: {len(msg)}")
    except Exception as e:
        print("Error:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
