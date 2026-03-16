"""
Run this directly on your machine to diagnose what yt-dlp returns.
Copy this file to your backend folder and run: python test_ytdlp.py
"""
import subprocess, sys

BINARY = r"C:\Users\Dell\AppData\Local\Programs\Python\Python312\Scripts\yt-dlp.exe"
URL    = "https://youtu.be/QYKsaaUyM_A"

clients = ["tv_embedded", "mediaconnect", "android_embedded", "android_vr", "web"]

for client in clients:
    print(f"\n{'='*50}")
    print(f"Testing client: {client}")
    result = subprocess.run(
        [BINARY,
         "--no-check-certificates",
         "--extractor-args", f"youtube:player-client={client}",
         "--dump-json", "--no-playlist", "--no-warnings",
         URL],
        capture_output=True, text=True, timeout=60
    )
    print(f"  returncode : {result.returncode}")
    print(f"  stdout[:200]: {result.stdout[:200]!r}")
    print(f"  stderr[:300]: {result.stderr[:300]!r}")
    if result.returncode == 0 and result.stdout.strip():
        print("  >>> SUCCESS <<<")
        break
