import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MiniMap, Draw, Fullscreen
import numpy as np
import pandas as pd
import datetime
import math
import threading
import asyncio
import json
import websockets

from src.fire_physics import PhysicalFireSimulator
from src.db_gis import GISDatabaseManager
from src.optimization import optimize_aircraft_dispatch

# ==========================================================
# 1. CSS ULTRA-MILITAIRE (Palantir / Lockheed Martin Style)
# ==========================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@500;700&display=swap');

    /* Global */
    .main, .stSidebar { background-color: #020408; color: #cfd8dc; font-family: 'Rajdhani', sans-serif; }
    h1, h2, h3, h4 { font-family: 'Share Tech Mono', monospace; color: #00e5ff !important; text-shadow: 0 0 10px rgba(0, 229, 255, 0.5); letter-spacing: 1px; }
    #MainMenu, footer, header { visibility: hidden; }
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: #000; }
    ::-webkit-scrollbar-thumb { background: #1b263b; border-radius: 2px; }

    /* TOP BAR */
    .top-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: linear-gradient(90deg, #0d1b2a 0%, #1b263b 100%);
        border-bottom: 2px solid #00e5ff; padding: 10px 20px; margin-bottom: 10px;
        border-radius: 0 0 5px 5px;
    }
    .top-bar-left { display: flex; align-items: center; gap: 15px; }
    .pulse-dot { width: 10px; height: 10px; background-color: #00e676; border-radius: 50%; box-shadow: 0 0 10px #00e676; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(0, 230, 118, 0); } 100% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0); } }
    .sys-text { color: #00e676; font-family: 'Share Tech Mono'; font-size: 14px; text-transform: uppercase; }
    .op-text { color: #90a4ae; font-family: 'Share Tech Mono'; font-size: 14px; }
    .time-text { color: #ffffff; font-family: 'Share Tech Mono'; font-size: 18px; font-weight: bold; }

    /* KPIs */
    .kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 15px; }
    .kpi-card {
        background: #0a0f1a; border: 1px solid #1b263b; border-radius: 4px; padding: 10px; text-align: center;
        transition: all 0.3s; border-top: 3px solid #455a64;
    }
    .kpi-card:hover { border-top-color: #00e5ff; box-shadow: 0 4px 15px rgba(0, 229, 255, 0.1); }
    .kpi-value { font-size: 24px; font-weight: 700; color: #ffffff; font-family: 'Share Tech Mono'; }
    .kpi-label { font-size: 10px; color: #546e7a; text-transform: uppercase; letter-spacing: 1px; margin-top: -5px; }
    .status-red { border-top-color: #ff1744 !important; } .status-red .kpi-value { color: #ff1744; text-shadow: 0 0 10px rgba(255,23,68,0.5); }
    .status-green { border-top-color: #00e676 !important; } .status-green .kpi-value { color: #00e676; }
    .status-orange { border-top-color: #ff9100 !important; } .status-orange .kpi-value { color: #ff9100; }

    /* Onglets (Forcer le style sombre) */
    .stTabs [data-baseweb="tab-list"] { gap: 2px; background-color: #0a0f1a; border-bottom: 1px solid #1b263b; }
    .stTabs [data-baseweb="tab"] { border-radius: 4px 4px 0px 0px; padding: 10px 20px; background-color: #000; color: #546e7a; font-family: 'Share Tech Mono'; border: 1px solid #1b263b; }
    .stTabs [aria-selected="true"] { background-color: #0d1b2a !important; color: #00e5ff !important; border-bottom: 2px solid #00e5ff; }

    /* Terminal Log */
    .tactical-log { background-color: #000000; border: 1px solid #263238; height: 150px; overflow-y: auto; padding: 8px; font-family: 'Share Tech Mono'; font-size: 11px; border-radius: 4px; }
    .log-entry { margin-bottom: 2px; border-left: 2px solid #37474f; padding-left: 8px; }
    .log-time { color: #455a64; } .log-system { color: #00e5ff; } .log-alert { color: #ff1744; } .log-success { color: #00e676; }

    /* Divers */
    .stButton>button { border: 1px solid #00e5ff; background-color: rgba(0, 229, 255, 0.05); color: #00e5ff; font-weight: bold; text-transform: uppercase; font-family: 'Share Tech Mono'; letter-spacing: 1px; font-size: 12px;}
    .stButton>button:hover { background-color: #00e5ff; color: #000; box-shadow: 0 0 20px #00e5ff; }
    .target-box { background: #000; border: 1px dashed #ff1744; padding: 10px; border-radius: 4px; font-family: 'Share Tech Mono'; font-size: 12px; color: #ff1744; }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="CODIS ALGÉRIE - C4ISR", layout="wide", initial_sidebar_state="collapsed")

# ==========================================================
# 2. VARIABLES D'ÉTAT
# ==========================================================
if 'fire_grid' not in st.session_state: st.session_state.fire_grid = None
if 'elevation' not in st.session_state: st.session_state.elevation = None
if 'tactical_logs' not in st.session_state: st.session_state.tactical_logs = ["[BOOT] Initialisation du noyau tactique...", "[NET] Connexion au réseau SIG sécurisée."]
if 'wind_dir' not in st.session_state: st.session_state.wind_dir = 210
if 'spread_vector' not in st.session_state: st.session_state.spread_vector = None

def add_log(msg, t="SYSTEM"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.tactical_logs.append(f"<div class='log-entry'><span class='log-time'>[{ts}]</span> <span class='log-{t.lower()}'>{msg}</span></div>")
    if len(st.session_state.tactical_logs) > 100: st.session_state.tactical_logs.pop(0)

# Mock Flotte avancée
FLEET_DATA = [
    {"id": "CN-301", "type": "CL-415", "status": "STANDBY", "water": 6137, "alt": "0 ft", "speed": "0 kts"},
    {"id": "CN-302", "type": "CL-415", "status": "TRANSIT", "water": 0, "alt": "1500 ft", "speed": "140 kts"},
    {"id": "RU-12", "type": "BE-200", "status": "ECOPAGE", "water": 0, "alt": "50 ft", "speed": "180 kts"},
    {"id": "EC-01", "type": "EC-225", "status": "HORS SERVICE", "water": 0, "alt": "N/A", "speed": "N/A"}
]

# ==========================================================
# 3. INTERFACE PRINCIPALE
# ==========================================================

# --- TOP BAR ---
dz_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1))).strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"""
<div class="top-bar">
    <div class="top-bar-left">
        <div class="pulse-dot"></div>
        <span class="sys-text">SYSTEM ARMED</span>
        <span class="op-text">| OPÉRATEUR : CODIS_CMD_01</span>
    </div>
    <div style="text-align: right;">
        <span class="op-text">HEURE LOCALE DZ </span>
        <span class="time-text">{dz_time}</span>
    </div>
</div>
""", unsafe_allow_html=True)

db = GISDatabaseManager()
zones = db.fetch_active_sectors()
active_fires = len([z for z in zones if z['priority'] == 'Critique'])
available_planes = len([f for f in FLEET_DATA if f['status'] == 'STANDBY'])

# --- KPIs ---
kpi_html = f"""
<div class="kpi-grid">
    <div class="kpi-card status-red"><div class="kpi-value">{active_fires}</div><div class="kpi-label">Foyers Actifs</div></div>
    <div class="kpi-card status-green"><div class="kpi-value">{available_planes}</div><div class="kpi-label">Vecteurs Prêts</div></div>
    <div class="kpi-card status-orange"><div class="kpi-value">LEVEL 3</div><div class="kpi-label">Alerte Départementale</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:#29b6f6">35.2°C</div><div class="kpi-label">Temp. Ambiante</div></div>
    <div class="kpi-card status-red"><div class="kpi-value">92%</div><div class="kpi-label">Indice Risque Météo</div></div>
</div>
"""
st.markdown(kpi_html, unsafe_allow_html=True)

col_map, col_cmd = st.columns([3.5, 1.5])

# ================= CARTE =================
with col_map:
    m = folium.Map(location=[36.35, 3.05], zoom_start=7, control_scale=True, tiles=None, zoom_control=False)
    
    folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', attr='© OSM © CARTO', name='Commandement Nuit', overlay=False, control=True).add_to(m)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='© Esri', name='Satellite IR', overlay=False, control=True).add_to(m)
        Draw(export=True, draw_options={'polyline': False, 'circle': False, 'marker': True, 'circlemarker': False}).add_to(m)
    
    # Création d'un objet Tuile explicite pour la MiniMap afin de respecter la règle d'attribution de Folium
    minimap_tile_layer = folium.TileLayer(
        tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        name='MiniMap Dark'
    )
    MiniMap(toggle_display=True, position="bottomright", tile_layer=minimap_tile_layer).add_to(m)
    
    Fullscreen(position="topleft").add_to(m)

    # Flèche de vent
    wind_icon = folium.DivIcon(html=f"<div style='font-size: 40px; color: #00e5ff; transform: rotate({st.session_state.get('wind_dir', 180)}deg); text-shadow: 0 0 10px cyan;'>➤</div>", icon_size=(40, 40), icon_anchor=(20, 20))
    folium.Marker([36.35, 3.05], icon=wind_icon).add_to(m)

    # Zones SIG
    for zone in zones:
        color = "darkred" if zone['priority'] == 'Critique' else "orange"
        folium.Marker([zone['lat'], zone['lon']], popup=f"<b>{zone['name']}</b><br>Propagation: {zone['spread_rate']} km/h", icon=folium.Icon(color=color, icon="fire", prefix="fa")).add_to(m)

    # Vecteur de propagation et Heatmap
    if st.session_state.fire_grid is not None and st.session_state.spread_vector:
        vec = st.session_state.spread_vector
        # Ligne principale de propagation
        folium.PolyLine(locations=[vec['start'], vec['end']], color='#ff1744', weight=6, opacity=0.8, popup="Axe de propagation principal").add_to(m)
        # Marqueur de Tête de front
        folium.Marker(location=vec['end'], icon=folium.DivIcon(html="<div style='background:red; width:10px; height:10px; border-radius:50%; box-shadow: 0 0 10px red;'></div>", icon_size=(10,10), icon_anchor=(5,5))).add_to(m)
        
        sim = PhysicalFireSimulator(36.35, 3.05, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
        fire_coords = sim.get_fire_geojson(st.session_state.fire_grid)
        if fire_coords:
            HeatMap(fire_coords, radius=15, blur=10, gradient={0.4: '#ff9100', 0.7: '#ff1744', 1.0: '#d50000'}, name='🔥 Front Actif', overlay=True).add_to(m)

    folium.LayerControl().add_to(m)
    
    # Récupération des interactions carte (Clics de l'opérateur)
    map_data = st_folium(m, width="100%", height=580)

# ================= PANNEAU DE COMMANDE =================
with col_cmd:
    tab_ops, tab_intel = st.tabs(["⚙️ OPÉRATIONS", "📡 INTELLIGENCE"])
    
    with tab_ops:
        st.subheader("🛩 FLÔTE AÉRIENNE")
        for ac in FLEET_DATA:
            sc = "#00e676" if ac['status']=="STANDBY" else "#ff9100" if ac['status'] in ["TRANSIT", "ECOPAGE"] else "#ff1744"
            water_bar_color = "#29b6f6" if ac['water'] > 0 else "#455a64"
            st.markdown(f"""
            <div style='background:#0a0f1a; padding:8px; border-radius:4px; margin-bottom:5px; border-left: 3px solid {sc}; font-size:12px; font-family: Share Tech Mono;'>
                <div style="display:flex; justify-content:space-between; color:white;"><b>{ac['id']}</b> <span style='color:{sc}'>{ac['status']}</span></div>
                <div style="display:flex; justify-content:space-between; color:#546e7a; font-size:10px; margin-top:4px;">
                    <span>{ac['type']}</span> <span>ALT: {ac['alt']}</span> <span>SPD: {ac['speed']}</span>
                </div>
                <div style="background:#000; height:4px; border-radius:2px; margin-top:4px; overflow:hidden;">
                    <div style="background:{water_bar_color}; width:{(ac['water']/6137)*100}%; height:100%;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("🧠 OPTIMISATION ILP")
        if st.button("⚡ ENGAGER PLAN DE VOL", use_container_width=True):
            add_log("Résolution matricielle OR-Tools en cours...", "SYSTEM")
            allocation = optimize_aircraft_dispatch(zones, available_planes)
            for _, row in pd.DataFrame(allocation).iterrows():
                if row['avions_assignes'] > 0: add_log(f"ORDRE : {row['avions_assignes']} vecteur(s) -> {row['zone']}", "SUCCESS")
            st.success("Plans de vol générés")

        st.markdown("---")
        st.subheader("🔬 SIMULATION JUMEAU")
        wind_speed = st.number_input("Vent (km/h)", 0, 120, 65, key='w_spd')
        st.session_state['wind_dir'] = st.number_input("Direction (°)", 0, 360, 210)
        moisture = st.number_input("Humidité (%)", 5, 80, 15)
        
        if st.button("🔥 INIT THEATRE (Kabylie)", use_container_width=True):
            sim = PhysicalFireSimulator(36.35, 3.05, rows=50, cols=50, cell_size_m=150)
            st.session_state.fire_grid = np.zeros((50, 50))
            st.session_state.fire_grid[25, 25] = 2
            st.session_state.elevation = np.random.uniform(200, 1200, (50, 50))
            st.session_state.spread_vector = None
            add_log("Grille 7.5km² activée. Ignition confirmée.", "ALERT")

        if st.button("⏩ PROJECTION +1 HEURE", use_container_width=True):
            if st.session_state.fire_grid is not None:
                sim = PhysicalFireSimulator(36.35, 3.05, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
                
                # Calcul du vecteur AVANT propagation
                old_coords = sim.get_fire_geojson(st.session_state.fire_grid)
                old_centroid = [np.mean([c[0] for c in old_coords]), np.mean([c[1] for c in old_coords])] if old_coords else [36.35, 3.05]
                
                # Propagation
                new_grid = sim.step_propagation(st.session_state.fire_grid, st.session_state.elevation, wind_speed, st.session_state['wind_dir'], moisture)
                st.session_state.fire_grid = new_grid
                
                # Calcul du vecteur APRÈS propagation
                new_coords = sim.get_fire_geojson(new_grid)
                if new_coords:
                    new_centroid = [np.mean([c[0] for c in new_coords]), np.mean([c[1] for c in new_coords])]
                    st.session_state.spread_vector = {'start': old_centroid, 'end': new_centroid}
                
                cells_burned = np.sum(new_grid == 1) + np.sum(new_grid == 2)
                surface = (cells_burned * 0.0225) * 100 
                add_log(f"PROJECTION : +{len(new_coords)} foyers. Front avance. Surface: {surface:.1f} Ha", "ALERT")
                st.metric("Surface Projetée", f"{surface:.1f} Ha")

    with tab_intel:
        st.subheader("🎯 CIBLAGE CARTOGRAPHIQUE")
        st.caption("Cliquez sur la carte pour obtenir les coordonnées de précision.")
        
        # Extraction des données de clic de la carte
        if map_data and map_data.get('last_clicked'):
            lat = map_data['last_clicked']['lat']
            lon = map_data['last_clicked']['lng']
            
            # Conversion DMS (Degrés, Minutes, Secondes)
            lat_deg, lat_min, lat_sec = int(lat), int((lat % 1) * 60), ((lat % 1) * 60 - int((lat % 1) * 60)) * 60
            lon_deg, lon_min, lon_sec = int(lon), int((lon % 1) * 60), ((lon % 1) * 60 - int((lon % 1) * 60)) * 60
            dms = f"{lat_deg}°{lat_min:02d}'{lat_sec:05.2f}\"N  {lon_deg}°{lon_min:02d}'{lon_sec:05.2f}\"E"
            
            st.markdown(f"""
            <div class="target-box">
                <div style="font-size:10px; color:#546e7a; margin-bottom:5px;">DERNIERE CIBLE DESIGNÉE PAR L'OPÉRATEUR</div>
                <div style="font-size:16px; margin-bottom:5px;">{lat:.5f}, {lon:.5f}</div>
                <div style="font-size:14px; color:#ff9100;">{dms}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("📤 ENVOYER AU POSTE DE COMMANDAGE", use_container_width=True):
                add_log(f"CIBLE DESIGNÉE : [{lat:.5f}, {lon:.5f}] transmise au CODIS.", "ALERT")
        else:
            st.markdown("<div class='target-box' style='color:#455a74; border-color:#455a74;'>En attente de sélection sur le COP...</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("🌦 ANALYSE MICRO-CLIMAT")
        st.markdown("""
        <div style='background:#0a0f1a; padding:10px; border-radius:4px; font-family: Share Tech Mono; font-size:12px; color:#90a4ae;'>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #1b263b; padding-bottom:4px;">
                <span>TEMPÉRATURE SOL</span><span style="color:#ff9100">48.2°C</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #1b263b; padding-bottom:4px;">
                <span>HUMIDITÉ FOLIAGE</span><span style="color:#29b6f6">12%</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #1b263b; padding-bottom:4px;">
                <span>VENT (RAFALES)</span><span style="color:#ff1744">+25 km/h</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span>RISQUE SAUTE DE FEU</span><span style="color:#ff1744; font-weight:bold;">CONFIRMÉ</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ================= TERMINAL SYSLOG =================
st.markdown("<h4 style='margin-bottom:5px; margin-top:10px;'>📡 JOURNAL SYSTÈME (SYSLOG)</h4>", unsafe_allow_html=True)
log_html = f"<div class='tactical-log'>{''.join(st.session_state.tactical_logs)}</div>"
st.markdown(log_html, unsafe_allow_html=True)

# ================= BACKGROUND TASKS =================
async def fetch_iot_data():
    try:
        async with websockets.connect("ws://localhost:8765") as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("type") == "GPS_UPDATE": pass # Prêt à recevoir la vraie télémétrie
    except Exception: pass

def run_ws(): 
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(fetch_iot_data())

if 'ws_thread_started' not in st.session_state:
    st.session_state.ws_thread_started = True
    threading.Thread(target=run_ws, daemon=True).start()
