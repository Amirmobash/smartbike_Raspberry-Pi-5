# SmartBike - Raspberry Pi 5 Optimized Streamlit Version
# Author: Amir Mobasheraghdam (adapted/optimized for RPi5)
# Notes:
#  - CPU-friendly settings (lower resolution, frame skipping, smaller imgsz)
#  - Requires: ultralytics, opencv-python, pyttsx3, streamlit, numpy
#  - Optional: streamlit-geolocation
# Run:
#   streamlit run smartbike_pi5_streamlit.py --server.address 0.0.0.0 --server.port 8501

import json
import time
import threading
from collections import deque
from typing import List, Tuple, Dict

import cv2
import numpy as np
import streamlit as st
import pyttsx3
from ultralytics import YOLO

# --- Optional geolocation (won't break if missing) ---
try:
    from streamlit_geolocation import geolocation
    HAS_GEO = True
except Exception:
    HAS_GEO = False

# ---------------------- TTS (thread-safe) ----------------------
class Speaker:
    def __init__(self, rate: int = 150, volume: float = 1.0, enabled: bool = True):
        self.enabled = enabled
        self.engine = None
        self.lock = threading.Lock()
        if self.enabled:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", rate)
                self.engine.setProperty("volume", volume)
            except Exception:
                self.engine = None
                self.enabled = False

    def say_async(self, text: str):
        if not self.enabled or not self.engine or not text:
            return
        threading.Thread(target=self._speak_blocking, args=(text,), daemon=True).start()

    def _speak_blocking(self, text: str):
        with self.lock:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                pass


# ---------------------- App State ----------------------
if "hazards" not in st.session_state:
    st.session_state.hazards = []  # list of dicts: {"lat": float, "lng": float, "label": str, "ts": float}

if "object_histories" not in st.session_state:
    st.session_state.object_histories: Dict[str, deque] = {}

if "last_danger_spoken" not in st.session_state:
    st.session_state.last_danger_spoken = 0.0

if "run_flag" not in st.session_state:
    st.session_state.run_flag = False


# ---------------------- Sidebar Controls ----------------------
st.sidebar.header("⚙️ Settings (RPi5 Optimized)")

api_key = st.sidebar.text_input(
    "Google Maps API Key (JS)", type="password",
    help="Enable the Maps JavaScript API for this key."
)

st.sidebar.subheader("📍 Location")
if HAS_GEO:
    loc_btn = st.sidebar.button("Use my browser location")
else:
    st.sidebar.caption("Optional: pip install streamlit-geolocation")

default_lat, default_lng = 52.5200, 13.4050  # Berlin default

if HAS_GEO and "browser_loc" not in st.session_state:
    st.session_state.browser_loc = None
if HAS_GEO and "last_geo" not in st.session_state:
    st.session_state.last_geo = None

if HAS_GEO and loc_btn:
    st.session_state.last_geo = geolocation()
    if st.session_state.last_geo and "lat" in st.session_state.last_geo:
        st.session_state.browser_loc = (st.session_state.last_geo["lat"], st.session_state.last_geo["lon"])

lat = st.sidebar.number_input(
    "Latitude",
    value=(st.session_state.browser_loc[0] if HAS_GEO and st.session_state.browser_loc else default_lat),
    format="%.6f"
)
lng = st.sidebar.number_input(
    "Longitude",
    value=(st.session_state.browser_loc[1] if HAS_GEO and st.session_state.browser_loc else default_lng),
    format="%.6f"
)

st.sidebar.subheader("🎥 Camera & Performance")
cam_index = st.sidebar.number_input("Camera index", min_value=0, value=0, step=1)

# Pi-friendly resolution
frame_w = st.sidebar.selectbox("Capture width", [640, 800, 1280], index=0)
frame_h = st.sidebar.selectbox("Capture height", [360, 480, 720], index=0)

frame_skip = st.sidebar.slider("Frame skip (run YOLO every N frames)", 1, 5, 2, 1)
imgsz = st.sidebar.selectbox("YOLO imgsz (smaller = faster)", [320, 416, 512, 640], index=1)

conf_thresh = st.sidebar.slider("YOLO confidence", 0.1, 0.9, 0.45, 0.05)
speed_thresh = st.sidebar.slider("Speed warn (px/s)", 20, 400, 120, 5)
danger_distance_m = st.sidebar.slider("Danger distance (m)", 0.3, 5.0, 1.2, 0.1)

st.sidebar.subheader("🗣️ Audio")
tts_enabled = st.sidebar.checkbox("Enable TTS (pyttsx3)", value=True)
tts_rate = st.sidebar.slider("TTS rate", 100, 220, 150, 5)

st.sidebar.subheader("🗺️ Map Options")
map_zoom = st.sidebar.slider("Zoom", 8, 20, 15)
show_map = st.sidebar.checkbox("Show Google Map overlay", value=True)
auto_drop_hazard = st.sidebar.checkbox("Auto mark hazards when warning triggers", value=True)

max_hazards = st.sidebar.slider("Max hazard markers (keep UI fast)", 20, 300, 120, 10)

st.sidebar.divider()
if st.sidebar.button("Clear all hazard markers"):
    st.session_state.hazards = []

# ---------------------- Header ----------------------
st.title("🚴‍♂️ SmartBike - Real-Time Safety (RPi5)")
st.caption("YOLOv8 (CPU) + Speed/Distance Heuristics + Streamlit + Google Maps")

col1, col2 = st.columns([3, 2])
with col2:
    st.markdown("### Live Map & Hazard Log")


# ---------------------- Google Map Embed ----------------------
from streamlit.components.v1 import html as components_html

MAP_HTML_TMPL = """<!DOCTYPE html>
<html>
  <head>
    <meta name=viewport content="initial-scale=1, width=device-width" />
    <style>
      html, body, #map { height: 100%; margin: 0; padding: 0; }
      .label {
        background: rgba(0,0,0,0.65);
        color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 12px;
      }
    </style>
    <script src="https://maps.googleapis.com/maps/api/js?key={API_KEY}"></script>
    <script>
      function init() {
        const center = {{ lat: {CENTER_LAT}, lng: {CENTER_LNG} }};
        const map = new google.maps.Map(document.getElementById('map'), {{
          center: center,
          zoom: {ZOOM},
          mapTypeId: 'roadmap',
          clickableIcons: true
        }});

        const me = new google.maps.Marker({{
          position: center,
          map: map,
          title: 'Your position',
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            scale: 6
          }}
        }});

        const hazards = {HAZARDS_JSON};
        hazards.forEach(h => {{
          const m = new google.maps.Marker({{
            position: {{lat: h.lat, lng: h.lng}},
            map: map,
            title: h.label || 'Hazard'
          }});
          const infowindow = new google.maps.InfoWindow({{
            content: `<div class="label"><b>${{h.label || 'Hazard'}}</b><br/>${{new Date(h.ts*1000).toLocaleString()}}</div>`
          }});
          m.addListener('click', () => infowindow.open({{anchor: m, map}}));
        }});
      }
      window.onload = init;
    </script>
  </head>
  <body>
    <div id="map"></div>
  </body>
</html>"""


def render_google_map(api_key: str, center: Tuple[float, float], zoom: int, hazards: List[dict]):
    if not api_key:
        st.info("برای نمایش نقشه، API Key گوگل را در سایدبار وارد کن.")
        return
    html = MAP_HTML_TMPL.format(
        API_KEY=api_key,
        CENTER_LAT=center[0],
        CENTER_LNG=center[1],
        ZOOM=int(zoom),
        HAZARDS_JSON=json.dumps(hazards),
    )
    components_html(html, height=420)


# ---------------------- Detection Setup ----------------------
IMPORTANT_CLASSES = ["person", "car", "bicycle", "motorcycle", "bus", "traffic light"]
REAL_WIDTHS = {"person": 0.5, "car": 1.8, "bicycle": 0.7, "motorcycle": 0.8, "bus": 2.5}
FOCAL_LENGTH = 600  # approx
HISTORY_LENGTH = 8  # a bit shorter for speed

@st.cache_resource(show_spinner=False)
def load_model():
    m = YOLO("models/yolov8n.pt")
    try:
        m.fuse()  # small speed win sometimes
    except Exception:
        pass
    return m

model = load_model()


# ---------------------- UI Buttons (Streamlit-friendly) ----------------------
btn_col_a, btn_col_b = st.columns(2)
with btn_col_a:
    if st.button("▶️ Start", use_container_width=True):
        st.session_state.run_flag = True
with btn_col_b:
    if st.button("⏹ Stop", use_container_width=True):
        st.session_state.run_flag = False

FRAME = col1.empty()
LOG = col2.empty()
MAP = col2.empty()

speaker = Speaker(rate=tts_rate, enabled=tts_enabled)


# ---------------------- Camera Open ----------------------
def open_camera(index: int, w: int, h: int):
    # CAP_V4L2 works well on Linux
    cap = cv2.VideoCapture(int(index), cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


# ---------------------- Helpers ----------------------
def is_red_light(roi_bgr: np.ndarray) -> bool:
    """Simple HSV-based red detection in traffic-light ROI."""
    if roi_bgr.size == 0:
        return False
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    # red wraps hue: [0..10] and [160..180]
    lower1 = np.array([0, 80, 80]);   upper1 = np.array([10, 255, 255])
    lower2 = np.array([160, 80, 80]); upper2 = np.array([180, 255, 255])
    mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
    red_ratio = float(mask.mean()) / 255.0
    return red_ratio > 0.08  # tune if needed


# ---------------------- Main Loop ----------------------
cap = None
last_map_render = 0.0
frame_i = 0

if st.session_state.run_flag:
    cap = open_camera(cam_index, frame_w, frame_h)
    if cap is None:
        st.error("Error: Camera not available. Check permissions / index / interface.")
        st.session_state.run_flag = False

while st.session_state.run_flag:
    ok, frame = cap.read()
    if not ok:
        st.warning("No frame from camera.")
        break

    frame_i += 1
    h, w = frame.shape[:2]

    # Run YOLO only every N frames
    do_infer = (frame_i % int(frame_skip) == 0)

    speech_chunks = []
    red_light_detected = False

    if do_infer:
        # Ultralytics inference (CPU)
        results = model.predict(frame, conf=conf_thresh, imgsz=int(imgsz), verbose=False)[0]

        for box in results.boxes:
            cls_id = int(box.cls[0])
            class_name = model.names.get(cls_id, str(cls_id))
            if class_name not in IMPORTANT_CLASSES:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            bw = max(1, x2 - x1)

            position = "Left" if cx < w / 3 else ("Right" if cx > 2 * w / 3 else "Center")

            hist = st.session_state.object_histories.setdefault(class_name, deque(maxlen=HISTORY_LENGTH))
            hist.append((time.time(), cx, cy))

            speed_warn = ""
            if len(hist) >= 2:
                t0, x0, y0 = hist[0]
                t1, x1n, y1n = hist[-1]
                dt = max(1e-3, t1 - t0)
                pix_dist = float(np.hypot(x1n - x0, y1n - y0))
                speed = pix_dist / dt
                if speed > speed_thresh:
                    speed_warn = "FAST"
                    speech_chunks.append(f"Warning: {class_name} approaching fast.")

            distance_m = None
            if class_name in REAL_WIDTHS:
                distance_m = round((REAL_WIDTHS[class_name] * FOCAL_LENGTH) / bw, 2)

            danger = False
            if distance_m is not None and distance_m < danger_distance_m and position in ("Left", "Right"):
                danger = True
                side = position.lower()
                speech_chunks.append(f"Warning: {class_name} on your {side}, too close.")

            label = class_name
            if distance_m is not None:
                label += f" {distance_m}m"
            if speed_warn:
                label += " ⚠️"

            color = (0, 0, 255) if (danger or speed_warn) else (0, 200, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if class_name == "traffic light":
                roi = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                if is_red_light(roi):
                    red_light_detected = True

    if red_light_detected:
        speech_chunks.append("Red light ahead. Please stop.")

    # Speak (debounced)
    now = time.time()
    if speech_chunks and (now - st.session_state.last_danger_spoken > 1.5):
        speaker.say_async(" ".join(speech_chunks))
        st.session_state.last_danger_spoken = now

    # Auto hazard marker (keep list bounded)
    if auto_drop_hazard and (red_light_detected or any("Warning:" in s for s in speech_chunks)):
        st.session_state.hazards.append({
            "lat": float(lat),
            "lng": float(lng),
            "label": "Danger/Warning",
            "ts": now,
        })
        if len(st.session_state.hazards) > int(max_hazards):
            st.session_state.hazards = st.session_state.hazards[-int(max_hazards):]

    # Show frame
    FRAME.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), caption=f"Live ({frame_w}x{frame_h})", use_column_width=True)

    # Log
    if speech_chunks or red_light_detected:
        LOG.write("\n".join([f"• {s}" for s in speech_chunks] + (["• Red light detected."] if red_light_detected else [])))

    # Map refresh (rate-limit)
    if show_map and (now - last_map_render > 1.2):
        with MAP:
            render_google_map(api_key, (lat, lng), map_zoom, st.session_state.hazards)
        last_map_render = now

    # Give UI time to breathe (important on Pi)
    time.sleep(0.01)

# Cleanup
if cap is not None:
    cap.release()

st.info("SmartBike System is stopped.")
