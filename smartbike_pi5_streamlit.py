# SmartBike - Raspberry Pi 5 Vollständige Deutsche Version
# Autor: Amir Mobasheraghdam (optimiert für RPi5)
# Komplett humanisiert und benutzerfreundlich
# Lizenz: Open Source
# Letzte Aktualisierung: 2024

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

# ===================== INITIALISIERUNG =====================
st.set_page_config(
    page_title="🚴‍♂️ SmartBike - Intelligentes Fahrrad-Sicherheitssystem",
    page_icon="🚴‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== SPRACHMODUL =====================
class DeutscherSprecher:
    def __init__(self, geschwindigkeit: int = 150, lautstärke: float = 1.0, aktiv: bool = True):
        self.aktiv = aktiv
        self.engine = None
        self.sperre = threading.Lock()
        
        if self.aktiv:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", geschwindigkeit)
                self.engine.setProperty("volume", lautstärke)
                
                # Deutsche Sprache konfigurieren
                stimmen = self.engine.getProperty('voices')
                for stimme in stimmen:
                    if "german" in stimme.name.lower() or "deutsch" in stimme.name.lower():
                        self.engine.setProperty('voice', stimme.id)
                        break
            except Exception as e:
                st.warning(f"Sprachmodul konnte nicht initialisiert werden: {e}")
                self.engine = None
                self.aktiv = False

    def spreche_asynchron(self, text: str):
        if not self.aktiv or not self.engine or not text:
            return
        threading.Thread(target=self._spreche_synchron, args=(text,), daemon=True).start()

    def _spreche_synchron(self, text: str):
        with self.sperre:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                pass

# ===================== DEUTSCHE ÜBERSETZUNGEN =====================
DEUTSCHE_WÖRTERBUCH = {
    # Objekte
    "person": "Fußgänger", "pedestrian": "Fußgänger", "people": "Personen",
    "car": "Auto", "vehicle": "Fahrzeug", "cars": "Autos",
    "bicycle": "Fahrrad", "bike": "Fahrrad", "cyclist": "Radfahrer",
    "motorcycle": "Motorrad", "motorbike": "Motorrad", "rider": "Fahrer",
    "bus": "Bus", "coach": "Reisebus", "minibus": "Minibus",
    "truck": "LKW", "lorry": "LKW", "van": "Transporter",
    "traffic light": "Ampel", "traffic signal": "Verkehrssignal",
    "stop sign": "Stoppschild", "stop": "Stopp",
    "train": "Zug", "tram": "Straßenbahn",
    
    # Richtungen
    "Left": "Links", "Right": "Rechts", "Center": "Mitte",
    "Front": "Vorne", "Back": "Hinten",
    
    # Warnungen
    "Warning": "Warnung", "Danger": "Gefahr", "Alert": "Alarm",
    "Caution": "Vorsicht", "Attention": "Achtung",
    "Fast": "Schnell", "Quick": "Schnell", "Rapid": "Rasend",
    "Close": "Nah", "Near": "In der Nähe", "Approaching": "Nähert sich",
    
    # Zustände
    "Safe": "Sicher", "Normal": "Normal", "Clear": "Frei",
    "Red": "Rot", "Green": "Grün", "Yellow": "Gelb"
}

def übersetze_zu_deutsch(englischer_text: str) -> str:
    """Übersetzt englische Begriffe ins Deutsche"""
    return DEUTSCHE_WÖRTERBUCH.get(englischer_text, englischer_text)

# ===================== SESSION STATUS =====================
if "gefahren_punkte" not in st.session_state:
    st.session_state.gefahren_punkte = []

if "objekt_verläufe" not in st.session_state:
    st.session_state.objekt_verläufe = {}

if "letzte_sprach_warnung" not in st.session_state:
    st.session_state.letzte_sprach_warnung = 0.0

if "system_läuft" not in st.session_state:
    st.session_state.system_läuft = False

if "leistungs_daten" not in st.session_state:
    st.session_state.leistungs_daten = {
        "frames_pro_sekunde": 0,
        "erkennungs_dauer_ms": 0,
        "objekte_gesamt": 0,
        "warnungen_gesamt": 0,
        "start_zeitpunkt": time.time(),
        "frames_verarbeitet": 0
    }

if "letztes_foto" not in st.session_state:
    st.session_state.letztes_foto = None

# ===================== BENUTZEROBERFLÄCHE =====================
# Header mit deutschem Design
st.markdown("""
<div style="
    text-align: center; 
    padding: 25px; 
    background: linear-gradient(135deg, #2E7D32 0%, #1B5E20 100%); 
    border-radius: 15px; 
    margin-bottom: 25px; 
    box-shadow: 0 6px 15px rgba(0,0,0,0.15);
    border: 1px solid #4CAF50;
">
    <h1 style="
        color: white; 
        margin: 0; 
        font-size: 2.8rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    ">
        🚴‍♂️ SmartBike - Fahrradsicherheitssystem
    </h1>
    <p style="
        color: rgba(255,255,255,0.95); 
        margin: 15px 0 8px 0; 
        font-size: 1.3rem;
        font-weight: 300;
    ">
        Echtzeit-Objekterkennung mit KI | Raspberry Pi 5 optimiert
    </p>
    <p style="
        color: rgba(255,255,255,0.8); 
        font-size: 1rem; 
        margin: 5px 0 0 0;
        font-style: italic;
    ">
        Entwickelt von <strong>Amir Mobasheraghdam</strong> | Version 3.0
    </p>
</div>
""", unsafe_allow_html=True)

# ===================== SEITENLEISTE =====================
st.sidebar.header("⚙️ SYSTEMKONFIGURATION")

# Abschnitt 1: API und Verbindung
st.sidebar.subheader("🔗 API-EINSTELLUNGEN")
with st.sidebar.expander("Google Maps API", expanded=False):
    api_schluessel = st.text_input(
        "API-Schlüssel eingeben",
        type="password",
        help="Erforderlich für die Kartendarstellung"
    )
    st.caption("Holen Sie Ihren Schlüssel von: console.cloud.google.com")

# Abschnitt 2: Standort
st.sidebar.subheader("📍 STANDORT")
col_geo1, col_geo2 = st.sidebar.columns(2)
with col_geo1:
    latitude = st.number_input(
        "Breitengrad",
        value=52.520008,
        format="%.6f",
        min_value=-90.0,
        max_value=90.0
    )
with col_geo2:
    longitude = st.number_input(
        "Längengrad",
        value=13.404954,
        format="%.6f",
        min_value=-180.0,
        max_value=180.0
    )

# Abschnitt 3: Kamera
st.sidebar.subheader("🎥 KAMERA-EINSTELLUNGEN")
kamera_index = st.sidebar.slider("Kamera auswählen", 0, 4, 0, 1,
                                help="0 = Standardkamera, 1+ = externe Kameras")

col_res1, col_res2 = st.sidebar.columns(2)
with col_res1:
    bild_breite = st.selectbox("Breite", [320, 480, 640, 800, 1024], index=2)
with col_res2:
    bild_höhe = st.selectbox("Höhe", [240, 360, 480, 600, 720], index=2)

# Abschnitt 4: Leistung
st.sidebar.subheader("⚡ LEISTUNGSOPTIMIERUNG")
frame_überspringen = st.sidebar.slider(
    "Frame-Reduzierung", 
    1, 5, 2, 1,
    help="Höhere Werte = weniger CPU-Last"
)

yolo_größe = st.sidebar.select_slider(
    "KI-Modellgröße",
    options=[160, 224, 320, 416, 512, 640],
    value=416,
    help="Kleinere Größe = schneller, aber weniger genau"
)

# Abschnitt 5: Erkennung
st.sidebar.subheader("🎯 ERKENNUNGSPARAMETER")
konfidenz_grenze = st.sidebar.slider(
    "Mindest-Konfidenz",
    0.1, 0.95, 0.45, 0.05,
    help="Wie sicher muss die KI sein?"
)

gefahr_abstand = st.sidebar.slider(
    "Kritischer Abstand (Meter)",
    0.5, 5.0, 1.5, 0.1,
    help="Abstand, bei dem gewarnt wird"
)

geschwindigkeit_grenze = st.sidebar.slider(
    "Warn-Geschwindigkeit (px/s)",
    50, 500, 150, 10,
    help="Pixelbewegung pro Sekunde für Warnungen"
)

# Abschnitt 6: Audio
st.sidebar.subheader("🔊 AUDIO-WARNUNGEN")
audio_aktiv = st.sidebar.checkbox("Sprachwarnungen aktivieren", value=True)
if audio_aktiv:
    audio_geschwindigkeit = st.sidebar.slider("Sprachtempo", 120, 200, 150, 5)
    audio_lautstärke = st.sidebar.slider("Lautstärke", 0.1, 1.0, 0.8, 0.1)

# Abschnitt 7: Karte
st.sidebar.subheader("🗺️ KARTENANSICHT")
karte_anzeigen = st.sidebar.checkbox("Interaktive Karte zeigen", value=True)
if karte_anzeigen:
    karten_zoom = st.sidebar.slider("Zoom-Stufe", 10, 20, 15, 1)
    auto_markierungen = st.sidebar.checkbox("Automatische Gefahren-Markierung", value=True)

# Abschnitt 8: Entwickler
st.sidebar.divider()
st.sidebar.subheader("👨‍💻 ENTWICKLER-INFO")
st.sidebar.markdown("""
<div style="
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #2196F3;
">
    <p style="margin: 0 0 10px 0; font-weight: bold;">
    🛠️ SmartBike System
    </p>
    <p style="margin: 0; font-size: 12px;">
    <strong>Entwickler:</strong> Amir Mobasheraghdam<br>
    <strong>Version:</strong> 3.0 (RPi5)<br>
    <strong>Letztes Update:</strong> 2024<br>
    <strong>Lizenz:</strong> MIT Open Source
    </p>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🧹 Alle Daten zurücksetzen", type="secondary"):
    st.session_state.gefahren_punkte = []
    st.session_state.objekt_verläufe = {}
    st.session_state.leistungs_daten["warnungen_gesamt"] = 0
    st.success("✅ Systemdaten wurden zurückgesetzt!")

# ===================== HAUPTLAYOUT =====================
col_haupt, col_seite = st.columns([7, 3])

with col_haupt:
    st.markdown("### 📷 LIVE-KAMERA-ANSICHT")
    kamera_platzhalter = st.empty()
    
    # Statusanzeige
    status_cols = st.columns(4)
    with status_cols[0]:
        st.metric("FPS", f"{st.session_state.leistungs_daten['frames_pro_sekunde']:.1f}")
    with status_cols[1]:
        st.metric("Objekte", st.session_state.leistungs_daten["objekte_gesamt"])
    with status_cols[2]:
        st.metric("Warnungen", st.session_state.leistungs_daten["warnungen_gesamt"])
    with status_cols[3]:
        laufzeit = time.time() - st.session_state.leistungs_daten["start_zeitpunkt"]
        st.metric("Laufzeit", f"{laufzeit:.0f}s")

with col_seite:
    st.markdown("### 📋 SYSTEMSTATUS")
    
    # Warnungsprotokoll
    warnungs_container = st.container(height=200)
    
    st.markdown("### 🗺️ GEFAHRENKARTE")
    karten_container = st.empty()

# ===================== STEUERUNGSBUTTONS =====================
st.markdown("---")
col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

with col_btn1:
    if st.button("▶️ SYSTEM STARTEN", use_container_width=True, type="primary"):
        st.session_state.system_läuft = True
        st.session_state.leistungs_daten["start_zeitpunkt"] = time.time()
        st.rerun()

with col_btn2:
    if st.button("⏹ SYSTEM STOPPEN", use_container_width=True):
        st.session_state.system_läuft = False
        st.rerun()

with col_btn3:
    foto_btn = st.button("📸 FOTO AUFNEHMEN", use_container_width=True)

with col_btn4:
    if st.button("🔊 TESTWARNUNG", use_container_width=True):
        tester = DeutscherSprecher(aktiv=True)
        tester.spreche_asynchron("SmartBike Systemtest erfolgreich. Alle Systeme funktionieren.")

# ===================== KARTEN-FUNKTIONALITÄT =====================
from streamlit.components.v1 import html as st_html

KARTEN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SmartBike Gefahrenkarte</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body, html { height: 100%; font-family: Arial, sans-serif; }
        #map { height: 100%; width: 100%; }
        .info-window { 
            padding: 10px; 
            background: white; 
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
    </style>
    <script src="https://maps.googleapis.com/maps/api/js?key={API_KEY}&language=de&region=DE"></script>
    <script>
        let map;
        let markers = [];
        
        function initMap() {{
            const center = {{ lat: {LAT}, lng: {LNG} }};
            
            map = new google.maps.Map(document.getElementById('map'), {{
                zoom: {ZOOM},
                center: center,
                mapTypeId: 'roadmap',
                styles: [
                    {{elementType: 'geometry', stylers: [{{color: '#f5f5f5'}}]}},
                    {{elementType: 'labels.text.stroke', stylers: [{{color: '#ffffff'}}]}},
                    {{elementType: 'labels.text.fill', stylers: [{{color: '#616161'}}]}}
                ]
            }});
            
            // Eigene Position
            new google.maps.Marker({{
                position: center,
                map: map,
                title: 'Ihre Position',
                icon: {{
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 10,
                    fillColor: '#4285F4',
                    fillOpacity: 1,
                    strokeColor: '#FFFFFF',
                    strokeWeight: 3
                }}
            }});
            
            // Gefahrenpunkte
            const dangers = {GEFAHREN};
            
            dangers.forEach((danger, index) => {{
                const marker = new google.maps.Marker({{
                    position: {{ lat: danger.lat, lng: danger.lng }},
                    map: map,
                    title: danger.label || 'Gefahrenpunkt',
                    icon: {{
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 8,
                        fillColor: '#FF4444',
                        fillOpacity: 0.8,
                        strokeColor: '#FFFFFF',
                        strokeWeight: 2
                    }}
                }});
                
                const infoWindow = new google.maps.InfoWindow({{
                    content: `
                        <div class="info-window">
                            <h3>${{danger.label || 'Gefahrenpunkt'}}</h3>
                            <p>Zeit: ${{new Date(danger.ts * 1000).toLocaleString('de-DE')}}</p>
                        </div>
                    `
                }});
                
                marker.addListener('click', () => {{
                    infoWindow.open(map, marker);
                }});
                
                markers.push(marker);
            }});
        }}
        
        window.initMap = initMap;
        window.onload = initMap;
    </script>
</head>
<body>
    <div id="map"></div>
</body>
</html>
"""

def zeige_gefahren_karte(api_key: str, position: tuple, zoom: int, gefahren: list):
    """Zeigt interaktive Google Map mit Gefahrenpunkten"""
    if not api_key:
        karten_container.warning("⚠️ Bitte API-Schlüssel in der Seitenleiste eingeben")
        return
    
    html_code = KARTEN_TEMPLATE.format(
        API_KEY=api_key,
        LAT=position[0],
        LNG=position[1],
        ZOOM=zoom,
        GEFAHREN=json.dumps(gefahren)
    )
    
    karten_container.markdown(f"**Aktuelle Gefahrenpunkte:** {len(gefahren)}")
    st_html(html_code, height=400)

# ===================== KI-MODELL =====================
@st.cache_resource(show_spinner="KI-Modell wird geladen...")
def initialisiere_ki_modell():
    """Lädt und konfiguriert das YOLO-Modell"""
    try:
        st.info("🔄 Lade YOLOv8n-Modell für Raspberry Pi 5...")
        modell = YOLO('yolov8n.pt')
        
        # Modell optimieren für CPU
        modell.overrides['verbose'] = False
        modell.overrides['max_det'] = 15
        modell.overrides['agnostic_nms'] = True
        
        st.success("✅ KI-Modell erfolgreich geladen!")
        return modell
    except Exception as e:
        st.error(f"❌ Fehler beim Laden des KI-Modells: {e}")
        return None

ki_modell = initialisiere_ki_modell()

# ===================== KAMERA-FUNKTIONEN =====================
def starte_kamera(index: int, breite: int, höhe: int):
    """Startet die Kamera mit optimierten Einstellungen für RPi5"""
    # Zuerst mit V4L2 versuchen (Linux optimiert)
    kamera = cv2.VideoCapture(index, cv2.CAP_V4L2)
    
    if not kamera.isOpened():
        # Fallback auf Standardmethode
        kamera = cv2.VideoCapture(index)
    
    if not kamera.isOpened():
        return None
    
    # Optimierte Einstellungen für Raspberry Pi
    kamera.set(cv2.CAP_PROP_FRAME_WIDTH, breite)
    kamera.set(cv2.CAP_PROP_FRAME_HEIGHT, höhe)
    kamera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Kleiner Buffer für geringe Latenz
    kamera.set(cv2.CAP_PROP_FPS, 20)  # Angemessene Framerate für RPi5
    
    return kamera

# ===================== HILFSFUNKTIONEN =====================
REALE_OBJEKT_GRÖSSEN = {
    "person": 0.5, "pedestrian": 0.5,
    "car": 1.8, "vehicle": 1.8,
    "bicycle": 0.7, "bike": 0.7,
    "motorcycle": 0.8, "motorbike": 0.8,
    "bus": 2.5, "truck": 2.5,
    "traffic light": 0.3, "stop sign": 0.4
}

WICHTIGE_OBJEKTE = [
    "person", "bicycle", "car", "motorcycle", 
    "bus", "truck", "traffic light", "stop sign"
]

def berechne_entfernung(pixel_breite: float, objekt_typ: str) -> float:
    """Berechnet Entfernung basierend auf Pixelgröße"""
    if objekt_typ not in REALE_OBJEKT_GRÖSSEN:
        return None
    
    # Einfache Entfernungsberechnung (600 = Brennweite in Pixel)
    return round((REALE_OBJEKT_GRÖSSEN[objekt_typ] * 600) / pixel_breite, 2)

def erkenne_rote_ampel(bereich_bgr: np.ndarray) -> bool:
    """Erkennt rote Ampeln im gegebenen Bildbereich"""
    if bereich_bgr.size == 0:
        return False
    
    # In HSV umwandeln für bessere Farberkennung
    hsv = cv2.cvtColor(bereich_bgr, cv2.COLOR_BGR2HSV)
    
    # Rot-Bereiche definieren (Rot hat zwei Hue-Bereiche)
    rot_unten1 = np.array([0, 100, 100])
    rot_oben1 = np.array([10, 255, 255])
    rot_unten2 = np.array([160, 100, 100])
    rot_oben2 = np.array([180, 255, 255])
    
    # Masken erstellen
    maske1 = cv2.inRange(hsv, rot_unten1, rot_oben1)
    maske2 = cv2.inRange(hsv, rot_unten2, rot_oben2)
    rote_maske = maske1 | maske2
    
    # Rot-Anteil berechnen
    rot_anteil = np.sum(rote_maske > 0) / (bereich_bgr.shape[0] * bereich_bgr.shape[1])
    
    return rot_anteil > 0.08  # 8% Rot-Anteil

def erstelle_deutsche_warnung(objekt_name: str, position: str, entfernung: float, schnell: bool) -> str:
    """Erstellt eine natürliche deutsche Warnmeldung"""
    objekt_deutsch = übersetze_zu_deutsch(objekt_name)
    position_deutsch = übersetze_zu_deutsch(position)
    
    if entfernung < gefahr_abstand:
        if schnell:
            return f"⚠️ DRINGEND: {objekt_deutsch} nähert sich schnell von {position_deutsch}! Nur {entfernung:.1f} Meter entfernt!"
        else:
            return f"⚠️ ACHTUNG: {objekt_deutsch} zu nah auf {position_deutsch}! Abstand: {entfernung:.1f} Meter"
    elif schnell:
        return f"⚠️ HINWEIS: Schneller {objekt_deutsch} von {position_deutsch}"
    
    return ""

# ===================== HAUPTVERARBEITUNG =====================
def verarbeite_kamerabild():
    """Hauptverarbeitungsfunktion für Kamerabilder"""
    
    # Kamera initialisieren
    kamera = starte_kamera(kamera_index, bild_breite, bild_höhe)
    
    if kamera is None:
        st.error("""
        ❌ KAMERA NICHT VERFÜGBAR
        ---
        **Mögliche Lösungen:**
        1. Kamera anschließen und einschalten
        2. Berechtigungen prüfen: `sudo usermod -a -G video $USER`
        3. Anderen Kamera-Index versuchen
        4. Kamera-Treiber aktualisieren
        """)
        st.session_state.system_läuft = False
        return
    
    # Sprachmodul initialisieren
    if audio_aktiv:
        sprecher = DeutscherSprecher(
            geschwindigkeit=audio_geschwindigkeit,
            lautstärke=audio_lautstärke,
            aktiv=True
        )
    
    # Verarbeitungsvariablen
    frame_nummer = 0
    letzte_fps_zeit = time.time()
    frames_seit_letzter_fps = 0
    letzte_karten_aktualisierung = 0
    
    # Hauptverarbeitungsschleife
    while st.session_state.system_läuft:
        verarbeitungs_start = time.time()
        
        # Frame lesen
        erfolg, frame = kamera.read()
        
        if not erfolg:
            st.warning("⚠️ Frame konnte nicht gelesen werden")
            time.sleep(0.1)
            continue
        
        # Frame für spätere Verwendung speichern
        st.session_state.letztes_foto = frame.copy()
        
        # FPS-Berechnung
        frames_seit_letzter_fps += 1
        aktuelle_zeit = time.time()
        
        if aktuelle_zeit - letzte_fps_zeit >= 1.0:
            st.session_state.leistungs_daten["frames_pro_sekunde"] = frames_seit_letzter_fps
            frames_seit_letzter_fps = 0
            letzte_fps_zeit = aktuelle_zeit
        
        # Nur jeden N-ten Frame analysieren (Performance)
        frame_nummer += 1
        analysiere_frame = (frame_nummer % frame_überspringen == 0)
        
        warnungs_meldungen = []
        rote_ampel_gefunden = False
        
        if analysiere_frame and ki_modell is not None:
            # KI-Inferenz
            inferenz_start = time.time()
            
            ergebnisse = ki_modell(
                frame,
                conf=konfidenz_grenze,
                imgsz=yolo_größe,
                verbose=False,
                half=False,  # Wichtig: Kein Half-Precision auf RPi5 CPU
                max_det=10
            )[0]
            
            # Verarbeitungszeit speichern
            inferenz_dauer = (time.time() - inferenz_start) * 1000
            st.session_state.leistungs_daten["erkennungs_dauer_ms"] = inferenz_dauer
            
            # Frame-Dimensionen
            höhe, breite = frame.shape[:2]
            mitte_x = breite // 2
            mitte_y = höhe // 2
            
            # Objekte verarbeiten
            erkannte_objekte = 0
            
            for box in ergebnisse.boxes:
                # Box-Daten extrahieren
                klasse_id = int(box.cls[0])
                klassen_name = ki_modell.names[klasse_id]
                konfidenz = float(box.conf[0])
                
                # Nur wichtige Objekte verarbeiten
                if klassen_name not in WICHTIGE_OBJEKTE:
                    continue
                
                erkannte_objekte += 1
                
                # Koordinaten
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                box_breite = x2 - x1
                box_höhe = y2 - y1
                mitte_punkt = ((x1 + x2) // 2, (y1 + y2) // 2)
                
                # Position bestimmen
                if mitte_punkt[0] < breite * 0.33:
                    position = "Left"
                elif mitte_punkt[0] > breite * 0.66:
                    position = "Right"
                else:
                    position = "Center"
                
                # Objektverlauf speichern
                verlauf_schlüssel = f"{klassen_name}_{position}"
                if verlauf_schlüssel not in st.session_state.objekt_verläufe:
                    st.session_state.objekt_verläufe[verlauf_schlüssel] = deque(maxlen=10)
                
                st.session_state.objekt_verläufe[verlauf_schlüssel].append({
                    "zeit": time.time(),
                    "mitte": mitte_punkt,
                    "box": (x1, y1, x2, y2)
                })
                
                # Geschwindigkeit berechnen
                geschwindigkeit_warnung = False
                verlauf = st.session_state.objekt_verläufe[verlauf_schlüssel]
                
                if len(verlauf) >= 2:
                    erster = verlauf[0]
                    letzter = verlauf[-1]
                    zeit_diff = letzter["zeit"] - erster["zeit"]
                    
                    if zeit_diff > 0:
                        distanz = np.sqrt(
                            (letzter["mitte"][0] - erster["mitte"][0])**2 +
                            (letzter["mitte"][1] - erster["mitte"][1])**2
                        )
                        geschwindigkeit = distanz / zeit_diff
                        geschwindigkeit_warnung = (geschwindigkeit > geschwindigkeit_grenze)
                
                # Entfernung berechnen
                entfernung = berechne_entfernung(box_breite, klassen_name)
                
                # Warnmeldungen generieren
                if klassen_name == "traffic light":
                    ampel_bereich = frame[y1:y2, x1:x2]
                    if erkenne_rote_ampel(ampel_bereich):
                        rote_ampel_gefunden = True
                        warnung = "🚦 ROTE AMPEL - BITTE ANHALTEN!"
                        warnungs_meldungen.append(warnung)
                        
                        # Rote Ampel im Frame markieren
                        cv2.putText(frame, "ROTE AMPEL", (x1, y1-40),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
                
                elif entfernung is not None:
                    warnung = erstelle_deutsche_warnung(
                        klassen_name, position, entfernung, geschwindigkeit_warnung
                    )
                    
                    if warnung:
                        warnungs_meldungen.append(warnung)
                        st.session_state.leistungs_daten["warnungen_gesamt"] += 1
                
                # Farbe basierend auf Gefahr
                if entfernung is not None and entfernung < gefahr_abstand:
                    farbe = (0, 0, 255)  # Rot für Gefahr
                elif geschwindigkeit_warnung:
                    farbe = (0, 165, 255)  # Orange für schnelle Bewegung
                else:
                    farbe = (0, 255, 0)  # Grün für sicher
                
                # Objekt im Frame markieren
                # 1. Rechteck zeichnen
                cv2.rectangle(frame, (x1, y1), (x2, y2), farbe, 2)
                
                # 2. Beschriftungs-Hintergrund
                objekt_name_de = übersetze_zu_deutsch(klassen_name)
                beschriftung = f"{objekt_name_de}"
                
                if entfernung is not None:
                    beschriftung += f" {entfernung}m"
                if geschwindigkeit_warnung:
                    beschriftung += " ⚡"
                
                # Textgröße berechnen
                (text_breite, text_höhe), _ = cv2.getTextSize(
                    beschriftung, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                
                # Hintergrund für bessere Lesbarkeit
                cv2.rectangle(frame, (x1, y1-30), 
                            (x1 + text_breite + 10, y1), farbe, -1)
                
                # Text zeichnen
                cv2.putText(frame, beschriftung, (x1+5, y1-10),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Richtungspfeil zeichnen
                if position == "Left":
                    cv2.putText(frame, "←", (x1, y1-50), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.8, farbe, 2)
                elif position == "Right":
                    cv2.putText(frame, "→", (x1, y1-50), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.8, farbe, 2)
            
            st.session_state.leistungs_daten["objekte_gesamt"] = erkannte_objekte
        
        # Frame mit Informationen anreichern
        # 1. Zeitstempel
        aktuelle_uhrzeit = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        cv2.putText(frame, aktuelle_uhrzeit, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 2. FPS-Anzeige
        fps_text = f"FPS: {st.session_state.leistungs_daten['frames_pro_sekunde']}"
        cv2.putText(frame, fps_text, (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 3. Objektanzahl
        objekte_text = f"Objekte: {st.session_state.leistungs_daten['objekte_gesamt']}"
        cv2.putText(frame, objekte_text, (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 4. Hilfslinien für Positionen
        cv2.line(frame, (breite//3, 0), (breite//3, höhe), (255, 255, 0), 1)
        cv2.line(frame, (2*breite//3, 0), (2*breite//3, höhe), (255, 255, 0), 1)
        
        cv2.putText(frame, "LINKS", (50, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, "MITTE", (breite//2 - 30, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, "RECHTS", (breite - 100, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # 5. Systemstatus
        status_text = "SYSTEM AKTIV" if st.session_state.system_läuft else "SYSTEM GESTOPPT"
        status_farbe = (0, 255, 0) if st.session_state.system_läuft else (0, 0, 255)
        cv2.putText(frame, status_text, (breite - 200, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_farbe, 2)
        
        # Sprachausgabe für Warnungen (mit Debouncing)
        if (audio_aktiv and warnungs_meldungen and 
            (time.time() - st.session_state.letzte_sprach_warnung > 2.0)):
            
            # Wichtigste Warnung auswählen
            if rote_ampel_gefunden:
                zu_sprechen = "Achtung, rote Ampel! Bitte anhalten."
            else:
                zu_sprechen = warnungs_meldungen[0].replace("⚠️ ", "")
            
            sprecher.spreche_asynchron(zu_sprechen)
            st.session_state.letzte_sprach_warnung = time.time()
        
        # Gefahrenpunkte automatisch speichern
        if (auto_markierungen and karte_anzeigen and 
            (rote_ampel_gefunden or warnungs_meldungen)):
            
            punkt_label = "Rote Ampel" if rote_ampel_gefunden else "Gefahrenzone"
            
            st.session_state.gefahren_punkte.append({
                "lat": float(latitude),
                "lng": float(longitude),
                "label": punkt_label,
                "ts": time.time(),
                "details": warnungs_meldungen[:2]  # Erste zwei Warnungen
            })
            
            # Liste auf maximale Größe beschränken
            if len(st.session_state.gefahren_punkte) > 100:
                st.session_state.gefahren_punkte = st.session_state.gefahren_punkte[-100:]
        
        # Frame anzeigen
        kamera_platzhalter.image(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
            caption=f"Live-Ansicht • Frame {frame_nummer}",
            use_container_width=True
        )
        
        # Warnungen im Log anzeigen
        if warnungs_meldungen or rote_ampel_gefunden:
            log_text = "### 🔔 AKTUELLE WARNUNGEN:\n"
            
            if rote_ampel_gefunden:
                log_text += "• 🚦 **ROTE AMPEL** - Bitte anhalten!\n"
            
            for meldung in warnungs_meldungen[:3]:  # Nur erste 3 anzeigen
                log_text += f"• {meldung}\n"
            
            warnungs_container.markdown(log_text)
        
        # Karte regelmäßig aktualisieren
        if karte_anzeigen and (time.time() - letzte_karten_aktualisierung > 2.0):
            with karten_container:
                zeige_gefahren_karte(
                    api_schluessel,
                    (latitude, longitude),
                    karten_zoom,
                    st.session_state.gefahren_punkte[-20:]  # Nur letzte 20 Punkte
                )
            letzte_karten_aktualisierung = time.time()
        
        # Verarbeitungsstatistik aktualisieren
        st.session_state.leistungs_daten["frames_verarbeitet"] = frame_nummer
        
        # Kurze Pause für UI-Responsiveness
        verarbeitungs_dauer = time.time() - verarbeitungs_start
        sleep_dauer = max(0.01, 0.033 - verarbeitungs_dauer)  # Ziel: ~30 FPS
        time.sleep(sleep_dauer)
    
    # Aufräumen
    kamera.release()
    cv2.destroyAllWindows()

# ===================== FOTO-FUNKTIONALITÄT =====================
if foto_btn and st.session_state.letztes_foto is not None:
    zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"smartbike_foto_{zeitstempel}.jpg"
    
    # Foto speichern
    cv2.imwrite(dateiname, st.session_state.letztes_foto)
    
    # Miniaturansicht zeigen
    foto_klein = cv2.resize(st.session_state.letztes_foto, (320, 240))
    
    col_foto1, col_foto2 = st.columns([1, 2])
    with col_foto1:
        st.image(cv2.cvtColor(foto_klein, cv2.COLOR_BGR2RGB), 
                caption="Aufgenommenes Foto")
    with col_foto2:
        st.success(f"✅ Foto gespeichert als: **{dateiname}**")
        st.download_button(
            "📥 Foto herunterladen",
            data=cv2.imencode('.jpg', st.session_state.letztes_foto)[1].tobytes(),
            file_name=dateiname,
            mime="image/jpeg"
        )

# ===================== HAUPTVERARBEITUNG STARTEN =====================
if st.session_state.system_läuft:
    # Verarbeitung in eigenem Thread starten
    verarbeitungs_thread = threading.Thread(target=verarbeite_kamerabild, daemon=True)
    verarbeitungs_thread.start()
    
    # Ladeanzeige während der Initialisierung
    with st.spinner("🔄 System wird gestartet... Kamera initialisiert"):
        time.sleep(1)
    
    st.toast("✅ SmartBike System ist jetzt aktiv!", icon="🚴‍♂️")
else:
    # System-Statusseite wenn gestoppt
    st.info("""
    ## 🛑 SYSTEM GESTOPPT
    
    **Bereit für den Start:** Das SmartBike-System wartet auf Ihre Anweisung.
    
    **Nächste Schritte:**
    1. Überprüfen Sie die Einstellungen in der Seitenleiste
    2. Stellen Sie sicher, dass die Kamera angeschlossen ist
    3. Klicken Sie auf **"SYSTEM STARTEN"** um zu beginnen
    
    **Schnellstart-Empfehlungen für RPi5:**
    - Auflösung: 640x480
    - Frame-Skip: 2
    - Modellgröße: 416
    - API-Schlüssel für Kartenfunktion
    """)

# ===================== SYSTEM-STATISTIK =====================
if not st.session_state.system_läuft and st.session_state.leistungs_daten["frames_verarbeitet"] > 0:
    st.markdown("---")
    st.markdown("### 📊 LEISTUNGSBERICHT")
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    with col_stat1:
        st.metric("Gesamte Frames", st.session_state.leistungs_daten["frames_verarbeitet"])
    with col_stat2:
        avg_fps = st.session_state.leistungs_daten["frames_verarbeitet"] / max(
            1, time.time() - st.session_state.leistungs_daten["start_zeitpunkt"]
        )
        st.metric("Durchschnittliche FPS", f"{avg_fps:.1f}")
    with col_stat3:
        st.metric("Gefahrenpunkte gesammelt", len(st.session_state.gefahren_punkte))
    
    # Warnungs-Statistik
    if st.session_state.leistungs_daten["warnungen_gesamt"] > 0:
        st.success(f"""
        ## ⚠️ SICHERHEITSBERICHT
        
        Während der letzten Sitzung wurden **{st.session_state.leistungs_daten['warnungen_gesamt']}** 
        Sicherheitswarnungen ausgegeben. Das System hat aktiv zur Sicherheit beigetragen!
        """)

# ===================== HILFE UND DOKUMENTATION =====================
with st.expander("📚 HILFE & DOKUMENTATION", expanded=False):
    st.markdown("""
    ## 🤔 SMARTBIKE BEDIENUNGSANLEITUNG
    
    ### **📋 SCHNELLSTART**
    1. **Kamera anschließen** - USB-Webcam oder Raspberry Pi Kamera
    2. **API-Schlüssel eingeben** - Für Kartenfunktion (optional)
    3. **Standort setzen** - Manuell oder automatisch
    4. **System starten** - Mit dem grünen Start-Button
    
    ### **🎯 FUNKTIONEN IM ÜBERBLICK**
    
    **🔄 Echtzeit-Erkennung:**
    - Fußgänger, Fahrzeuge, Ampeln
    - Entfernungsberechnung
    - Geschwindigkeitserkennung
    
    **⚠️ Sicherheitswarnungen:**
    - Sprachausgabe bei Gefahren
    - Visuelle Markierungen
    - Automatische Gefahrenprotokollierung
    
    **🗺️ Kartendarstellung:**
    - Interaktive Google Maps
    - Gefahrenpunkt-Markierung
    - Routenverlauf
    
    ### **⚡ RPi5 OPTIMIERUNGEN**
    
    **Empfohlene Einstellungen:**
    ```
    Auflösung: 640x480
    Frame-Skip: 2-3
    Modellgröße: 416
    CPU-Temperatur: < 80°C
    ```
    
    **Leistungstipps:**
    - Vermeiden Sie 1280x720 bei Echtzeit-Verarbeitung
    - Frame-Skip reduziert CPU-Last erheblich
    - Kleinere Modellgröße = schnellere Erkennung
    
    ### **🔧 PROBLEMLÖSUNG**
    
    **❌ Kein Kamerabild:**
    ```
    sudo usermod -a -G video $USER
    sudo reboot
    ```
    
    **🐌 Langsame Erkennung:**
    - Reduzieren Sie die Auflösung
    - Erhöhen Sie Frame-Skip
    - Verwenden Sie kleineres Modell
    
    **🗺️ Keine Karte:**
    - API-Schlüssel überprüfen
    - Internetverbindung prüfen
    - Browser-Konsole öffnen (F12)
    
    ### **📞 SUPPORT & KONTAKT**
    
    **Entwickler:** Amir Mobasheraghdam  
    **Version:** 3.0 (RPi5 optimiert)  
    **Lizenz:** MIT Open Source  
    **GitHub:** github.com/amirmobasher  
    
    ### **⚠️ SICHERHEITSHINWEISE**
    
    1. Dieses System ist eine **Unterstützung**, kein Ersatz für Aufmerksamkeit
    2. Immer Verkehrsregeln beachten
    3. Regelmäßig System und Kamera prüfen
    4. Bei Problemen sofort anhalten und prüfen
    
    ### **🔄 SYSTEMVORAUSSETZUNGEN**
    
    - Raspberry Pi 5 (4GB+ RAM empfohlen)
    - Raspberry Pi OS 64-bit
    - USB-Webcam oder RPi Kamera
    - Internet für Kartenfunktion
    - Python 3.9+
    """)

# ===================== TASTATURKÜRZEL =====================
st.markdown("""
<script>
// Tastatursteuerung für SmartBike
document.addEventListener('keydown', function(event) {
    // Nur wenn nicht in einem Eingabefeld
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
        return;
    }
    
    switch(event.key.toLowerCase()) {
        case 's':
            // Start/Stop Toggle
            console.log('S-Taste: Systemsteuerung');
            break;
        case 'f':
            // Foto aufnehmen
            console.log('F-Taste: Foto');
            break;
        case 'm':
            // Karte ein-/ausblenden
            console.log('M-Taste: Karte');
            break;
        case 'c':
            // Konfiguration öffnen
            console.log('C-Taste: Konfiguration');
            break;
        case 'h':
            // Hilfe öffnen
            console.log('H-Taste: Hilfe');
            break;
    }
});
</script>
""", unsafe_allow_html=True)

# ===================== FOOTER =====================
st.markdown("---")
st.markdown("""
<div style="
    text-align: center; 
    padding: 20px; 
    background-color: #f8f9fa; 
    border-radius: 10px; 
    margin-top: 30px;
    border-top: 3px solid #4CAF50;
">
    <p style="margin: 0 0 10px 0; color: #555; font-size: 14px;">
        <strong>🚴‍♂️ SmartBike Fahrradsicherheitssystem</strong><br>
        Entwickelt mit ❤️ für mehr Sicherheit im Straßenverkehr
    </p>
    <p style="margin: 0; color: #777; font-size: 12px;">
        © 2024 Amir Mobasheraghdam | Raspberry Pi 5 optimiert | Open Source Projekt
    </p>
</div>
""", unsafe_allow_html=True)

# ===================== STARTNACHRICHT =====================
if 'initialisiert' not in st.session_state:
    st.session_state.initialisiert = True
    st.toast("🚴‍♂️ SmartBike System bereit! Bitte Konfiguration prüfen.", icon="✅")
