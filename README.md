# 🎵 Scale Detector

**Drop a song. Get the key. Shift the pitch.**

[**→ Try it live**](https://ronankongala.github.io/scale-detector) &nbsp;|&nbsp; [Download full version](https://ronankongala.github.io/scale-detector/scale-detector.html) &nbsp;|&nbsp; [server.py](https://ronankongala.github.io/scale-detector/server.py)

---

## Demo

```
🎵 youtube.com/watch?v=...  →  E Major  →  94% confidence

C   C#  D   D#  E   F   F#  G   G#  A   A#  B
▂   ▅   ▂   ▄   █   ▁   ▆   ▂   ▆   ▅   ▁   ▆
        root ↑
```

---

## Try it

| What you want | How |
|---|---|
| Just detect a key | Open `scale-detector.html` in Chrome, drop any audio file |
| Analyze a YouTube song | Run `python server.py`, paste the URL |
| Pitch shift the audio | Hit **+** or **−** after analyzing — audio actually shifts |
| Use the live demo | [ronankongala.github.io/scale-detector](https://ronankongala.github.io/scale-detector) (file upload only) |

---

## Setup

```bash
git clone https://github.com/ronankongala/scale-detector
cd scale-detector
python server.py        # auto-installs yt-dlp, ffmpeg, librosa
```

Open `scale-detector.html` in Chrome. That's it.

---

## How it detects the key

```
audio file
    ↓
Goertzel algorithm  →  pitch energy per note (every 0.1s)
    ↓
chromagram  →  accumulated energy across 12 pitch classes
    ↓
Krumhansl-Schmuckler profiles  →  Pearson correlation × 24 keys
    ↓
🎯  best matching key
```

---

## Features

- 🎯 Key + scale detection with confidence score
- 📊 Live chromagram (root = pink, scale notes = purple)
- 🎹 Transpose display + actual audio pitch shifting
- ▶️ Built-in player with speed control (0.5× → 2×)
- 📥 YouTube download via yt-dlp
- ⬇️ Download the pitch-shifted audio

---

Built by [Ronan Kongala](https://ronankongala.github.io) · MS Cybersecurity @ Northeastern
