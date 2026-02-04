# SmartBike - Raspberry Pi 5 Optimized Streamlit Version
# Author: Amir Mobasheraghdam (adapted/optimized for RPi5)
# Human-Friendly Version with Persian UI Enhancements
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
from datetime import datetime
import cv2
import numpy as np
import streamlit as st
import pyttsx3
from ultralytics import YOLO

# تنظیمات اولیه برای نمایش فارسی بهتر
st.set_page_config(
    page_title="🚴‍♂️ SmartBike - سیستم هوشمند ایمنی دوچرخه",
    page_icon="🚴‍♂️",
    layout="wide"
)

# --- Optional geolocation (won't break if missing) ---
try:
    from streamlit_geolocation import geolocation
    HAS_GEO = True
except Exception:
    HAS_GEO = False

# ---------------------- TTS (thread-safe) ----------------------
class Speaker:
    def __init__(self, rate: int = 150, volume: float = 1.0, enabled: bool = True, lang: str = "en"):
        self.enabled = enabled
        self.lang = lang
        self.engine = None
        self.lock = threading.Lock()
        if self.enabled:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", rate)
                self.engine.setProperty("volume", volume)
                # Try to set language if available
                voices = self.engine.getProperty('voices')
                if lang == "fa" and len(voices) > 1:
                    try:
                        self.engine.setProperty('voice', voices[1].id)  # Try different voice
                    except:
                        pass
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

# ---------------------- Persian Translations ----------------------
PERSIAN_TRANSLATIONS = {
    "person": "عابر پیاده",
    "car": "خودرو",
    "bicycle": "دوچرخه",
    "motorcycle": "موتورسیکلت",
    "bus": "اتوبوس",
    "truck": "کامیون",
    "traffic light": "چراغ راهنمایی",
    "stop sign": "علامت توقف",
    "Left": "سمت چپ",
    "Right": "سمت راست",
    "Center": "مستقیم",
    "FAST": "سریع",
    "Warning": "هشدار",
    "Danger": "خطر",
    "Safe": "ایمن"
}

def translate_to_persian(text: str) -> str:
    """Translate common terms to Persian for better UX"""
    return PERSIAN_TRANSLATIONS.get(text, text)

# ---------------------- App State ----------------------
if "hazards" not in st.session_state:
    st.session_state.hazards = []  # list of dicts: {"lat": float, "lng": float, "label": str, "ts": float}

if "object_histories" not in st.session_state:
    st.session_state.object_histories: Dict[str, deque] = {}

if "last_danger_spoken" not in st.session_state:
    st.session_state.last_danger_spoken = 0.0

if "run_flag" not in st.session_state:
    st.session_state.run_flag = False

if "performance_stats" not in st.session_state:
    st.session_state.performance_stats = {
        "fps": 0,
        "detection_time": 0,
        "objects_detected": 0,
        "warnings_issued": 0
    }

# ---------------------- UI Header ----------------------
st.markdown("""
<div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; margin-bottom: 20px;">
    <h1 style="color: white; margin: 0;">🚴‍♂️ SmartBike - سیستم هوشمند ایمنی دوچرخه</h1>
    <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">
    نسخه بهینه‌سازی شده برای Raspberry Pi 5 | توسعه‌دهنده: <strong>امیر مبشراغ‌دم</strong>
    </p>
    <p style="color: rgba(255,255,255,0.7); font-size: 14px; margin: 5px 0 0 0;">
    YOLOv8 + هوش مصنوعی + هشدار‌های صوتی + نقشه تعاملی
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------------- Sidebar Controls (Persian UI) ----------------------
st.sidebar.header("⚙️ تنظیمات سیستم (بهینه‌سازی شده برای RPi5)")

# Section 1: API Keys
st.sidebar.subheader("🔑 کلیدهای API")
api_key = st.sidebar.text_input(
    "کلید Google Maps API",
    type="password",
    help="برای نمایش نقشه، کلید Google Maps JavaScript API را وارد کنید"
)

# Section 2: Location
st.sidebar.subheader("📍 موقعیت مکانی")
if HAS_GEO:
    loc_btn = st.sidebar.button("📍 استفاده از موقعیت مکانی من", use_container_width=True)
else:
    st.sidebar.caption("برای این قابلیت: pip install streamlit-geolocation")

default_lat, default_lng = 35.715298, 51.404343  # Tehran default

if HAS_GEO and "browser_loc" not in st.session_state:
    st.session_state.browser_loc = None
if HAS_GEO and "last_geo" not in st.session_state:
    st.session_state.last_geo = None

if HAS_GEO and loc_btn:
    st.session_state.last_geo = geolocation()
    if st.session_state.last_geo and "lat" in st.session_state.last_geo:
        st.session_state.browser_loc = (st.session_state.last_geo["lat"], st.session_state.last_geo["lon"])

lat = st.sidebar.number_input(
    "عرض جغرافیایی",
    value=(st.session_state.browser_loc[0] if HAS_GEO and st.session_state.browser_loc else default_lat),
    format="%.6f",
    help="Latitude"
)

lng = st.sidebar.number_input(
    "طول جغرافیایی",
    value=(st.session_state.browser_loc[1] if HAS_GEO and st.session_state.browser_loc else default_lng),
    format="%.6f",
    help="Longitude"
)

# Section 3: Camera Settings
st.sidebar.subheader("🎥 تنظیمات دوربین")
cam_index = st.sidebar.number_input("شماره دوربین", min_value=0, value=0, step=1, help="معمولاً 0 برای دوربین اصلی")

# Pi-friendly resolution
col_res1, col_res2 = st.sidebar.columns(2)
with col_res1:
    frame_w = st.selectbox("عرض فریم", [640, 800, 1280], index=0)
with col_res2:
    frame_h = st.selectbox("ارتفاع فریم", [360, 480, 720], index=0)

frame_skip = st.sidebar.slider("پرش فریم (اجرای YOLO در هر N فریم)", 1, 5, 2, 1,
                               help="کاهش پردازش با رد کردن بعضی فریم‌ها")
imgsz = st.sidebar.selectbox("اندازه تصویر YOLO (کوچکتر = سریع‌تر)", [320, 416, 512, 640], index=1)

# Section 4: Detection Parameters
st.sidebar.subheader("🎯 پارامترهای تشخیص")
conf_thresh = st.sidebar.slider("حداقل اطمینان تشخیص", 0.1, 0.9, 0.45, 0.05,
                               help="اعتماد مدل به تشخیص شیء")
speed_thresh = st.sidebar.slider("حداقل سرعت هشدار (پیکسل/ثانیه)", 20, 400, 120, 5,
                               help="سرعت حرکت شیء برای هشدار")
danger_distance_m = st.sidebar.slider("فاصله خطرناک (متر)", 0.3, 5.0, 1.2, 0.1,
                                     help="فاصله‌ای که شیء خطرناک محسوب می‌شود")

# Section 5: Audio Settings
st.sidebar.subheader("🗣️ تنظیمات صوتی")
tts_enabled = st.sidebar.checkbox("فعال کردن هشدارهای صوتی", value=True)
tts_rate = st.sidebar.slider("سرعت گفتار", 100, 220, 150, 5)
tts_lang = st.sidebar.selectbox("زبان گفتار", ["انگلیسی", "فارسی"], index=0)

# Section 6: Map Settings
st.sidebar.subheader("🗺️ تنظیمات نقشه")
map_zoom = st.sidebar.slider("بزرگنمایی نقشه", 8, 20, 15)
show_map = st.sidebar.checkbox("نمایش نقشه گوگل", value=True)
auto_drop_hazard = st.sidebar.checkbox("علامت‌گذاری خودکار نقاط خطر", value=True,
                                      help="ثبت خودکار موقعیت هنگام دریافت هشدار")

max_hazards = st.sidebar.slider("حداکثر نقاط خطر روی نقشه", 20, 300, 120, 10,
                               help="برای حفظ سرعت رابط کاربری")

# Section 7: Developer Info
st.sidebar.divider()
st.sidebar.markdown("""
<div style="background: #f0f2f6; padding: 15px; border-radius: 10px; border-right: 5px solid #4CAF50;">
    <p style="margin: 0; font-size: 14px;"><strong>🛠️ اطلاعات توسعه‌دهنده</strong></p>
    <p style="margin: 5px 0 0 0; font-size: 12px; color: #555;">
    توسعه‌دهنده: <strong>امیر مبشراغ‌دم</strong><br>
    نسخه: ۲.۰ (RPi5 بهینه)<br>
    آخرین بروزرسانی: ۱۴۰۳
    </p>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🧹 پاک کردن همه نقاط خطر", use_container_width=True):
    st.session_state.hazards = []
    st.success("✅ همه نقاط خطر پاک شدند")

# ---------------------- Main Layout ----------------------
col1, col2 = st.columns([3, 2])

with col1:
    st.markdown("### 📷 نمایش زنده دوربین")
    st.caption(f"رزولوشن: {frame_w}×{frame_h} | فریم‌اسکیپ: {frame_skip} | اندازه مدل: {imgsz}")

with col2:
    st.markdown("### 🗺️ نقشه تعاملی و گزارش‌ها")
    # Performance metrics
    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("FPS", f"{st.session_state.performance_stats['fps']:.1f}")
    with metric_cols[1]:
        st.metric("تشخیص‌ها", st.session_state.performance_stats['objects_detected'])
    with metric_cols[2]:
        st.metric("هشدارها", st.session_state.performance_stats['warnings_issued'])
    with metric_cols[3]:
        st.metric("زمان پردازش", f"{st.session_state.performance_stats['detection_time']:.1f}ms")

# ---------------------- Google Map Embed ----------------------
from streamlit.components.v1 import html as components_html

MAP_HTML_TMPL = """<!DOCTYPE html>
<html>
  <head>
    <meta name=viewport content="initial-scale=1, width=device-width" />
    <style>
      html, body, #map { height: 100%; margin: 0; padding: 0; }
      .label {
        background: rgba(0,0,0,0.75);
        color: #fff; padding: 5px 10px; border-radius: 6px; font-size: 12px;
        font-family: 'Tahoma', sans-serif;
      }
      .hazard-dot {
        background: #ff4444;
        width: 12px; height: 12px;
        border-radius: 50%;
        border: 2px solid white;
        box-shadow: 0 0 5px rgba(0,0,0,0.5);
      }
    </style>
    <script src="https://maps.googleapis.com/maps/api/js?key={API_KEY}&language=fa&region=IR"></script>
    <script>
      function init() {{
        const center = {{ lat: {CENTER_LAT}, lng: {CENTER_LNG} }};
        const map = new google.maps.Map(document.getElementById('map'), {{
          center: center,
          zoom: {ZOOM},
          mapTypeId: 'roadmap',
          streetViewControl: false,
          mapTypeControl: true,
          fullscreenControl: true,
          zoomControl: true
        }});

        // Current position marker (blue)
        const me = new google.maps.Marker({{
          position: center,
          map: map,
          title: 'موقعیت شما',
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: '#4285F4',
            fillOpacity: 1,
            strokeColor: '#FFFFFF',
            strokeWeight: 2
          }}
        }});

        const hazards = {HAZARDS_JSON};
        hazards.forEach(h => {{
          const m = new google.maps.Marker({{
            position: {{lat: h.lat, lng: h.lng}},
            map: map,
            title: h.label || 'نقطه خطر',
            icon: {{
              path: google.maps.SymbolPath.CIRCLE,
              scale: 6,
              fillColor: '#FF4444',
              fillOpacity: 0.8,
              strokeColor: '#FFFFFF',
              strokeWeight: 2
            }}
          }});
          const persianDate = new Date(h.ts*1000).toLocaleDateString('fa-IR');
          const timeStr = new Date(h.ts*1000).toLocaleTimeString('fa-IR');
          const infowindow = new google.maps.InfoWindow({{
            content: `<div class="label">
                      <strong>${h.label || 'نقطه خطر'}</strong><br/>
                      تاریخ: ${persianDate}<br/>
                      ساعت: ${timeStr}
                      </div>`
          }});
          m.addListener('click', () => infowindow.open({{anchor: m, map}}));
        }});
      }}
      window.onload = init;
    </script>
  </head>
  <body>
    <div id="map"></div>
  </body>
</html>"""

def render_google_map(api_key: str, center: Tuple[float, float], zoom: int, hazards: List[dict]):
    if not api_key:
        st.info("🔑 لطفاً کلید Google Maps API را در سایدبار وارد کنید")
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
IMPORTANT_CLASSES = ["person", "car", "bicycle", "motorcycle", "bus", "traffic light", "truck", "stop sign"]
REAL_WIDTHS = {
    "person": 0.5, "car": 1.8, "bicycle": 0.7, 
    "motorcycle": 0.8, "bus": 2.5, "truck": 2.5
}
FOCAL_LENGTH = 600  # approx
HISTORY_LENGTH = 8

@st.cache_resource(show_spinner=False)
def load_model():
    st.info("📦 در حال بارگیری مدل YOLOv8... لطفاً منتظر بمانید")
    m = YOLO("yolov8n.pt")  # Using nano model for RPi5
    try:
        m.fuse()
        st.success("✅ مدل با موفقیت بارگیری شد!")
    except Exception as e:
        st.warning(f"⚠️ بهینه‌سازی مدل کامل نبود: {e}")
    return m

model = load_model()

# ---------------------- Control Buttons ----------------------
st.markdown("---")
control_col1, control_col2, control_col3, control_col4 = st.columns(4)

with control_col1:
    if st.button("▶️ شروع سیستم", use_container_width=True, type="primary"):
        st.session_state.run_flag = True
        st.session_state.performance_stats['warnings_issued'] = 0
        st.rerun()

with control_col2:
    if st.button("⏹ توقف سیستم", use_container_width=True):
        st.session_state.run_flag = False
        st.rerun()

with control_col3:
    if st.button("📸 گرفتن عکس", use_container_width=True):
        if 'last_frame' in st.session_state:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"smartbike_capture_{timestamp}.jpg"
            cv2.imwrite(filename, st.session_state.last_frame)
            st.success(f"✅ عکس ذخیره شد: {filename}")

with control_col4:
    test_warning = st.button("🔊 تست هشدار صوتی", use_container_width=True)
    if test_warning:
        test_speaker = Speaker(enabled=True)
        test_speaker.say_async("سیستم SmartBike آماده کار است. توسعه‌دهنده: امیر مبشراغ‌دم")

# Placeholders for dynamic content
FRAME_PLACEHOLDER = col1.empty()
LOG_PLACEHOLDER = col2.empty()
MAP_PLACEHOLDER = col2.empty()

speaker = Speaker(rate=tts_rate, enabled=tts_enabled, lang="fa" if tts_lang == "فارسی" else "en")

# ---------------------- Camera Open Function ----------------------
def open_camera(index: int, w: int, h: int):
    cap = cv2.VideoCapture(int(index), cv2.CAP_V4L2)
    if not cap.isOpened():
        # Try without V4L2 as fallback
        cap = cv2.VideoCapture(int(index))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 15)  # Limit FPS for RPi5
    return cap

# ---------------------- Helper Functions ----------------------
def is_red_light(roi_bgr: np.ndarray) -> bool:
    """تشخیص چراغ قرمز با استفاده از پردازش تصویر"""
    if roi_bgr.size == 0:
        return False
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 120, 120])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([160, 120, 120])
    upper2 = np.array([180, 255, 255])
    mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
    red_ratio = float(mask.mean()) / 255.0
    return red_ratio > 0.1

def get_warning_message(persian_name: str, position: str, distance: float, speed_warn: bool) -> str:
    """ایجاد پیام هشدار به زبان فارسی"""
    position_fa = translate_to_persian(position)
    
    if distance < danger_distance_m:
        if speed_warn:
            return f"⚠️ هشدار! {persian_name} سریع از {position_fa} نزدیک می‌شود! فاصله: {distance:.1f} متر"
        else:
            return f"⚠️ هشدار! {persian_name} در {position_fa} خیلی نزدیک است! فاصله: {distance:.1f} متر"
    elif speed_warn:
        return f"⚠️ توجه! {persian_name} سریع از {position_fa} در حال حرکت است"
    
    return ""

# ---------------------- Main Processing Loop ----------------------
cap = None
last_map_render = 0.0
frame_i = 0
last_fps_time = time.time()
frame_count = 0

if st.session_state.run_flag:
    cap = open_camera(cam_index, frame_w, frame_h)
    if cap is None:
        st.error("❌ دوربین در دسترس نیست! لطفاً بررسی کنید:")
        st.error("1. دوربین به رزبری پای متصل است")
        st.error("2. شماره دوربین صحیح است")
        st.error("3. دسترسی‌ها تنظیم شده‌اند (sudo usermod -a -G video $USER)")
        st.session_state.run_flag = False

while st.session_state.run_flag:
    start_time = time.time()
    ok, frame = cap.read()
    
    if not ok:
        st.warning("⚠️ دریافت فریم از دوربین ناموفق بود")
        time.sleep(0.1)
        continue
    
    # Store last frame for capture functionality
    st.session_state.last_frame = frame.copy()
    
    frame_i += 1
    frame_count += 1
    h, w = frame.shape[:2]
    
    # Calculate FPS
    current_time = time.time()
    if current_time - last_fps_time >= 1.0:
        st.session_state.performance_stats['fps'] = frame_count
        frame_count = 0
        last_fps_time = current_time
    
    # Run YOLO only every N frames for performance
    do_infer = (frame_i % int(frame_skip) == 0)
    
    speech_chunks = []
    red_light_detected = False
    warning_detected = False
    
    if do_infer:
        infer_start = time.time()
        
        # YOLO inference with optimized settings for RPi5
        results = model.predict(
            frame, 
            conf=conf_thresh, 
            imgsz=int(imgsz), 
            verbose=False,
            half=False,  # Don't use half precision on CPU
            max_det=10,  # Limit detections
            agnostic_nms=True
        )[0]
        
        infer_time = (time.time() - infer_start) * 1000
        st.session_state.performance_stats['detection_time'] = infer_time
        
        detected_objects = 0
        
        for box in results.boxes:
            cls_id = int(box.cls[0])
            class_name = model.names.get(cls_id, str(cls_id))
            
            if class_name not in IMPORTANT_CLASSES:
                continue
            
            detected_objects += 1
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            bw = max(1, x2 - x1)
            
            # Determine position (Left/Center/Right)
            if cx < w / 3:
                position = "Left"
            elif cx > 2 * w / 3:
                position = "Right"
            else:
                position = "Center"
            
            # Track object history for speed calculation
            hist_key = f"{class_name}_{position}"
            hist = st.session_state.object_histories.setdefault(
                hist_key, 
                deque(maxlen=HISTORY_LENGTH)
            )
            hist.append((time.time(), cx, cy))
            
            # Calculate speed if we have history
            speed_warn = False
            if len(hist) >= 2:
                t0, x0, y0 = hist[0]
                t1, x1n, y1n = hist[-1]
                dt = max(1e-3, t1 - t0)
                pix_dist = float(np.hypot(x1n - x0, y1n - y0))
                speed = pix_dist / dt
                if speed > speed_thresh:
                    speed_warn = True
            
            # Estimate distance (if we know real width)
            distance_m = None
            if class_name in REAL_WIDTHS:
                distance_m = round((REAL_WIDTHS[class_name] * FOCAL_LENGTH) / bw, 2)
            
            # Generate warning messages
            persian_name = translate_to_persian(class_name)
            warning_msg = ""
            
            if class_name == "traffic light":
                roi = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                if is_red_light(roi):
                    red_light_detected = True
                    warning_msg = "🚦 چراغ قرمز شناسایی شد! توقف کنید."
                    cv2.putText(frame, "🚦 چراغ قرمز", (x1, y1-40), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            elif distance_m is not None:
                warning_msg = get_warning_message(persian_name, position, distance_m, speed_warn)
                if warning_msg:
                    warning_detected = True
            
            # Add to speech queue
            if warning_msg:
                speech_chunks.append(warning_msg)
                st.session_state.performance_stats['warnings_issued'] += 1
            
            # Draw on frame (with Persian labels)
            color = (0, 0, 255) if warning_msg else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Create label with Persian text
            label_parts = [persian_name]
            if distance_m is not None:
                label_parts.append(f"{distance_m}m")
            if speed_warn:
                label_parts.append("سریع")
            
            label = " | ".join(label_parts)
            
            # Draw background for better text visibility
            text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(frame, (x1, y1-25), (x1+text_size[0]+10, y1), color, -1)
            cv2.putText(frame, label, (x1+5, y1-8), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Draw small direction indicator
            if position == "Left":
                cv2.putText(frame, "←", (x1, y1-50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            elif position == "Right":
                cv2.putText(frame, "→", (x1, y1-50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
        st.session_state.performance_stats['objects_detected'] = detected_objects
    
    # Add timestamp and stats to frame
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    fps_text = f"FPS: {st.session_state.performance_stats['fps']}"
    cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, fps_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"تشخیص‌ها: {st.session_state.performance_stats['objects_detected']}", 
               (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Draw center guidelines
    cv2.line(frame, (w//3, 0), (w//3, h), (255, 255, 0), 1)
    cv2.line(frame, (2*w//3, 0), (2*w//3, h), (255, 255, 0), 1)
    cv2.putText(frame, "چپ", (w//6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, "وسط", (w//2, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, "راست", (5*w//6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    # Speak warnings (debounced)
    now = time.time()
    if speech_chunks and (now - st.session_state.last_danger_spoken > 2.0):
        # Speak only the most important warning
        if red_light_detected:
            warning_to_speak = "چراغ قرمز شناسایی شد! توقف کنید."
        else:
            warning_to_speak = speech_chunks[0]
        
        speaker.say_async(warning_to_speak)
        st.session_state.last_danger_spoken = now
    
    # Auto hazard marker (keep list bounded)
    if auto_drop_hazard and (red_light_detected or warning_detected):
        hazard_label = "چراغ قرمز" if red_light_detected else "خطر نزدیکی"
        st.session_state.hazards.append({
            "lat": float(lat),
            "lng": float(lng),
            "label": hazard_label,
            "ts": now,
        })
        # Keep only recent hazards
        if len(st.session_state.hazards) > int(max_hazards):
            st.session_state.hazards = st.session_state.hazards[-int(max_hazards):]
    
    # Display frame
    FRAME_PLACEHOLDER.image(
        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), 
        caption=f"نمایش زنده - فریم {frame_i}", 
        use_column_width=True
    )
    
    # Display warnings log
    if speech_chunks or red_light_detected:
        log_content = "### 🔔 هشدارهای اخیر:\n"
        for msg in speech_chunks:
            log_content += f"• {msg}\n"
        if red_light_detected:
            log_content += "• 🚦 چراغ قرمز شناسایی شد!\n"
        
        LOG_PLACEHOLDER.markdown(log_content)
    
    # Update map (rate-limited)
    if show_map and (now - last_map_render > 2.0):
        with MAP_PLACEHOLDER:
            render_google_map(api_key, (lat, lng), map_zoom, st.session_state.hazards)
        last_map_render = now
    
    # Small delay for UI responsiveness
    time.sleep(0.01)

# ---------------------- Cleanup ----------------------
if cap is not None:
    cap.release()
    cv2.destroyAllWindows()

# Final message when stopped
if not st.session_state.run_flag and 'cap' in locals():
    st.success("✅ سیستم متوقف شد. برای شروع مجدد دکمه 'شروع سیستم' را بزنید.")
    
    # Show summary
    st.markdown("### 📊 خلاصه عملکرد")
    col_sum1, col_sum2, col_sum3 = st.columns(3)
    with col_sum1:
        st.metric("کل فریم‌ها", frame_i)
    with col_sum2:
        st.metric("میانگین FPS", f"{st.session_state.performance_stats['fps']:.1f}")
    with col_sum3:
        st.metric("نقاط خطر ثبت شده", len(st.session_state.hazards))
