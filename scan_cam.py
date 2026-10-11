import socket
from concurrent.futures import ThreadPoolExecutor

def check_ip(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        if s.connect_ex((ip, 80)) == 0:
            print(f"FOUND OPEN PORT 80 ON: {ip}")
            return ip
    except Exception:
        pass
    finally:
        s.close()
    return None

ips = [f"10.119.226.{i}" for i in range(2, 255)]
with ThreadPoolExecutor(max_workers=50) as executor:
    results = list(executor.map(check_ip, ips))

found = [r for r in results if r]
print("Scan complete. Active port 80 devices:", found)
