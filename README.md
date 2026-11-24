# FOCUS-SENSE
### Posture & Eye-Strain Prevention Tool

Ultra-minimalist desktop app that uses your webcam + MediaPipe Face Mesh
to monitor screen distance and posture in real time.

---

## Project Structure

```
focus_sense/
├── main.py            ← GUI (CustomTkinter) + threading logic
├── vision_engine.py   ← OpenCV + MediaPipe detection engine
├── requirements.txt   ← Python dependencies
└── README.md
```

---

## Setup & Run

### 1 — Prerequisites
- Python 3.10 or 3.11 recommended  
- A working webcam  

### 2 — Create a virtual environment (recommended)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3 — Install dependencies
```bash
pip install -r requirements.txt
```

> **Note for macOS (Apple Silicon):** If `mediapipe` fails to install, try:
> ```bash
> pip install mediapipe --extra-index-url https://google-ml-packages.appspot.com
> ```

### 4 — Run the app
```bash
python main.py
```

---

## How to Use

| Step | Action |
|------|--------|
| 1 | Click **START** — the camera opens and "LIVE" appears |
| 2 | Sit in your ideal upright posture at a comfortable distance |
| 3 | Click **CALIBRATE** — hold still for ~2 seconds |
| 4 | The app now monitors deviations from your baseline |
| 5 | Adjust **SENSITIVITY** slider to make alerts stricter / more lenient |
| 6 | Click **STOP** to close the camera when done |

---

## Status Meanings

| Status | Meaning |
|--------|---------|
| **OPTIMAL** | Posture and distance are within your calibrated range |
| **WARNING** | Minor deviation — a gentle reminder to readjust |
| **CRITICAL** | Significant issue — system notification fired |
| **NO FACE** | Camera can't see your face; check lighting / angle |
| **INACTIVE** | Camera is off |

---

## Technical Notes

- **Distance** is measured by the pixel gap between inner-eye landmarks (33 & 263). A smaller gap means you are sitting closer to the screen.
- **Posture** is tracked by the Y-coordinate of nose landmark 1. Downward drift indicates slouching.
- **Focus Score** is a rolling average over the last 60 seconds (100 = perfect, 0 = worst).
- The camera loop runs on a **daemon thread**; the GUI thread never blocks.
- System notifications (via `plyer`) are throttled to once every 30 seconds.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not open webcam" | Close any other app using the camera (Zoom, Teams, etc.) |
| App freezes on START | Ensure `plyer` is installed; run `pip install plyer` |
| MediaPipe import error | Upgrade: `pip install --upgrade mediapipe` |
| Notifications not appearing | Check OS notification permissions for Python / Terminal |
| False positives on posture | Lower the Sensitivity slider |

---

*Built with OpenCV · MediaPipe · CustomTkinter · Python 3*
