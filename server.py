"""
Scale Detector - Local Server
------------------------------
Auto-installs yt-dlp, ffmpeg, librosa on first run.

Endpoints:
  POST /download  { url }           -> MP3 file
  POST /shift     { semitones }     -> pitch-shifted MP3 (send audio as multipart or base64)

Run:
  python server.py
"""

import http.server
import json
import os
import sys
import tempfile
import subprocess
import zipfile
import urllib.request
import io
from pathlib import Path

PORT = 7432
BASE_DIR = Path(__file__).parent
FFMPEG_DIR = BASE_DIR / "ffmpeg_bin"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"


def log(msg):
    print(msg, flush=True)


def get_ytdlp_cmd():
    import shutil
    if shutil.which("yt-dlp"):
        return "yt-dlp"
    candidates = [
        Path(sys.executable).parent / "Scripts" / "yt-dlp.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python313" / "Scripts" / "yt-dlp.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "Scripts" / "yt-dlp.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python311" / "Scripts" / "yt-dlp.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def ensure_ytdlp():
    if get_ytdlp_cmd():
        log("[+] yt-dlp found.")
        return
    log("[!] yt-dlp not found. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
    log("[+] yt-dlp installed.")


def ensure_ffmpeg():
    if FFMPEG_EXE.exists() and FFPROBE_EXE.exists():
        log("[+] ffmpeg found.")
        return
    import shutil
    if shutil.which("ffmpeg"):
        log("[+] ffmpeg found on PATH.")
        return
    log("[!] ffmpeg not found. Downloading...")
    FFMPEG_DIR.mkdir(exist_ok=True)
    ffmpeg_url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    zip_path = FFMPEG_DIR / "ffmpeg.zip"
    log("    Downloading ffmpeg (~30s)...")
    try:
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
    except Exception as e:
        log(f"[!] Download failed: {e}")
        fallback_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        try:
            urllib.request.urlretrieve(fallback_url, zip_path)
        except Exception as e2:
            log(f"[!] Fallback failed: {e2}")
            return
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for name in z.namelist():
                if name.endswith('/ffmpeg.exe'):
                    FFMPEG_EXE.write_bytes(z.read(name))
                    log("    Extracted ffmpeg.exe")
                elif name.endswith('/ffprobe.exe'):
                    FFPROBE_EXE.write_bytes(z.read(name))
                    log("    Extracted ffprobe.exe")
        zip_path.unlink()
        log("[+] ffmpeg ready.")
    except Exception as e:
        log(f"[!] Extraction failed: {e}")


def ensure_librosa():
    try:
        import librosa
        import soundfile
        log("[+] librosa found.")
    except ImportError:
        log("[!] librosa not found. Installing (this may take a minute)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "librosa", "soundfile"], check=True)
        log("[+] librosa installed.")


def get_ffmpeg_path():
    import shutil
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    if FFMPEG_EXE.exists():
        return str(FFMPEG_EXE)
    return "ffmpeg"


def build_download_cmd(url, out_template):
    ytdlp = get_ytdlp_cmd()
    base = [ytdlp] if ytdlp else [sys.executable, "-m", "yt_dlp"]
    cmd = base + ["-x", "--audio-format", "mp3", "--audio-quality", "0", "--no-playlist", "-o", out_template]
    import shutil
    if not shutil.which("ffmpeg") and FFMPEG_EXE.exists():
        cmd += ["--ffmpeg-location", str(FFMPEG_DIR)]
    cmd.append(url)
    return cmd


def pitch_shift_mp3(mp3_bytes, semitones):
    """Pitch shift an MP3 by N semitones, return shifted MP3 bytes."""
    import librosa
    import soundfile as sf
    import numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.mp3")
        wav_path = os.path.join(tmpdir, "input.wav")
        out_wav = os.path.join(tmpdir, "shifted.wav")
        out_mp3 = os.path.join(tmpdir, "shifted.mp3")

        # Write input mp3
        with open(in_path, 'wb') as f:
            f.write(mp3_bytes)

        # Convert mp3 -> wav using ffmpeg
        ffmpeg = get_ffmpeg_path()
        subprocess.run([ffmpeg, "-i", in_path, "-ar", "22050", "-ac", "1", wav_path, "-y"],
                       capture_output=True, check=True)

        log(f"[+] Pitch shifting by {semitones:+d} semitones...")
        y, sr = librosa.load(wav_path, sr=22050, mono=True)
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)

        # Write shifted wav
        sf.write(out_wav, y_shifted, sr)

        # Convert wav -> mp3
        subprocess.run([ffmpeg, "-i", out_wav, "-codec:a", "libmp3lame", "-qscale:a", "2", out_mp3, "-y"],
                       capture_output=True, check=True)

        return Path(out_mp3).read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/download":
            self.handle_download()
        elif self.path == "/shift":
            self.handle_shift()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_download(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            url = data.get("url", "").strip()
        except Exception:
            self._error(400, "Invalid JSON"); return

        if not url:
            self._error(400, "No URL provided"); return
        if "youtube.com" not in url and "youtu.be" not in url:
            self._error(400, "Only YouTube URLs are supported"); return

        log(f"\n[+] Downloading: {url}")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_template = os.path.join(tmpdir, "audio.%(ext)s")
            cmd = build_download_cmd(url, out_template)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode != 0:
                    log(result.stderr[-500:])
                    self._error(500, "Download failed: " + result.stderr[-300:]); return
            except subprocess.TimeoutExpired:
                self._error(500, "Download timed out"); return
            except FileNotFoundError:
                self._error(500, "yt-dlp not found"); return

            mp3_files = list(Path(tmpdir).glob("*.mp3"))
            if not mp3_files:
                audio_files = list(Path(tmpdir).glob("*.m4a")) + list(Path(tmpdir).glob("*.webm"))
                if audio_files:
                    mp3_files = audio_files
                else:
                    self._error(500, "No audio file produced"); return

            mp3_path = mp3_files[0]
            mp3_data = mp3_path.read_bytes()
            mime = "audio/mpeg" if mp3_path.suffix == ".mp3" else "audio/mp4"
            log(f"[+] Done — {len(mp3_data)//1024} KB")
            self._send_bytes(mp3_data, mime, mp3_path.name)

    def handle_shift(self):
        import base64
        length = int(self.headers.get("Content-Length", 0))
        if length > 100 * 1024 * 1024:  # 100MB max
            self._error(400, "File too large"); return
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            semitones = int(data.get("semitones", 0))
            audio_b64 = data.get("audio", "")
            mp3_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            self._error(400, f"Invalid request: {e}"); return

        if semitones == 0:
            self._send_bytes(mp3_bytes, "audio/mpeg", "audio.mp3"); return

        try:
            log(f"[+] Pitch shifting {len(mp3_bytes)//1024} KB by {semitones:+d} semitones...")
            shifted = pitch_shift_mp3(mp3_bytes, semitones)
            log(f"[+] Shift done — {len(shifted)//1024} KB")
            self._send_bytes(shifted, "audio/mpeg", "shifted.mp3")
        except Exception as e:
            log(f"[!] Shift error: {e}")
            self._error(500, f"Pitch shift failed: {e}")

    def _send_bytes(self, data, mime, filename):
        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code, msg):
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ensure_ytdlp()
    ensure_ffmpeg()
    ensure_librosa()

    server = http.server.HTTPServer(("localhost", PORT), Handler)
    print(f"""
+------------------------------------------+
|   Scale Detector -- Local Server  RK    |
+------------------------------------------+
|  Running at  http://localhost:{PORT}       |
|  Open scale-detector.html in Chrome      |
|  Press Ctrl+C to stop                    |
+------------------------------------------+
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Server stopped.")
