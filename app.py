import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MiniMap, Draw, Fullscreen
import numpy as np
import pandas as pd
import datetime
import threading
import asyncio
import json
import websockets

from src.fire_physics import PhysicalFireSimulator
from src.db_gis import GISDatabaseManager
from src.optimization import optimize_aircraft_dispatch

# ==========================================================
# 1. CONFIGURATION CSS : THEME C4ISR ULTRA-PROFESSIONNEL
# ==========================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@500;700&display=swap');

    /* Fond et typographie globale */
    .main, .stSidebar { background-color: #050a14; color: #cfd8dc; font-family: 'Rajdhani', sans-serif; }
    h1, h2, h3, h4 { font-family: 'Share Tech Mono', monospace; color: #00e5ff !important; text-shadow: 0 0 10px rgba(0, 229, 255, 0.5); }
    
    /* Masquer les éléments par défaut de Streamlit */
    #MainMenu, footer, header { visibility: hidden; }
    
    /* Barres de défilement personnalisées */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #0d1b2a; }
    ::-webkit-scrollbar-thumb { background: #1b263b; border-radius: 3px; }

    /* KPI Cards en haut */
    .kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-card {
        background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 100%);
        border: 1px solid #00e5ff; border-radius: 5px; padding: 15px; text-align: center;
        box-shadow: 0 0 15px rgba(0, 229, 255, 0.1); transition: all 0.3s;
    }
    .kpi-card:hover { box-shadow: 0 0 25px rgba(0, 229, 255, 0.4); transform: translateY(-2px); }
    .kpi-value { font-size: 28px; font-weight: 700; color: #ffffff; font-family: 'Share Tech Mono', monospace; }
    .kpi-label { font-size: 12px; color: #90a4ae; text-transform: uppercase; letter-spacing: 1px; }
    .alert-red .kpi-value { color: #ff1744; text-shadow: 0 0 10px rgba(255, 23, 68, 0.7); }
    .alert-orange .kpi-value { color: #ff9100; text-shadow: 0 0 10px rgba(255, 145, 0, 0.7); }
    .alert-green .kpi-value { color: #00e676; text-shadow: 0 0 10px rgba(0, 230, 118, 0.7); }

    /* Terminal de Logs */
    .tactical-log {
        background-color: #000000; border: 1px solid #263238; border-radius: 5px;
        height: 200px; overflow-y: auto; padding: 10px; font-family: 'Share Tech Mono', monospace; font-size: 12px;
    }
    .log-entry { margin-bottom: 4px; border-left: 2px solid #455a64; padding-left: 8px; }
    .log-time { color: #546e7a; }
    .log-system { color: #00e5ff; }
    .log-alert { color: #ff1744; }
    .log-success { color: #00e676; }

    /* Widgets */
    .stButton>button { border: 1px solid #00e5ff; background-color: rgba(0, 229, 255, 0.1); color: #00e5ff; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; }
    .stButton>button:hover { background-color: #00e5ff; color: #000000; box-shadow: 0 0 20px #00e5ff; }
    div[data-testid="stMetricValue"] { font-family: 'Share Tech Mono'; font-size: 20px; color: #ffffff; background-color: #0d1b2a; padding: 10px; border-radius: 5px; border-left: 4px solid #00e5ff; }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="CODIS ALGÉRIE - C4ISR", layout="wide", initial_sidebar_state="expanded")

# ==========================================================
# 2. INITIALISATION DES ÉTATS & VARIABLES
# ==========================================================
if 'fire_grid' not in st.session_state: st.session_state.fire_grid = None
if 'elevation' not in st.session_state: st.session_state.elevation = None
if 'iot_tracks' not in st.session_state: st.session_state.iot_tracks = []
if 'tactical_logs' not in st.session_state: st.session_state.tactical_logs = ["[SYSTEM] Initialisation du poste de commandement CODIS...", "[SYSTEM] Connexion au réseau SIG sécurisée."]

def add_log(message, log_type="SYSTEM"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.tactical_logs.append(f"<div class='log-entry'><span class='log-time'>[{timestamp}]</span> <span class='log-{log_type.lower()}'>{message}</span></div>")
    if len(st.session_state.tactical_logs) > 50: st.session_state.tactical_logs.pop(0)

# Flotte mockée ultra-réaliste
FLEET_DATA = [
    {"id": "CN-301", "type": "CL-415", "status": "Disponible", "capacity": "6137 L"},
    {"id": "CN-302", "type": "CL-415", "status": "En Transit", "capacity": "6137 L"},
    {"id": "RU-12", "type": "BE-200", "status": "Disponible", "capacity": "12000 L"},
    {"id": "EC-01", "type": "EC-225", "status": "Maintenance", "capacity": "3000 L"},
    {"id": "AS-05", "type": "AS350 Fennec", "status": "Disponible", "capacity": "680 L"}
]

# ==========================================================
# 3. INTERFACE UTILISATEUR
# ==========================================================
st.markdown("<h1 style='margin-bottom:0px;'>🇩🇿 CENTRE OPERATIONNEL DE DEFENSE DES FORETS</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#546e7a; margin-top:-10px; font-size:14px;'>SYSTEME DE COMMANDMENT C4ISR | ARCHITECTURE DISTRIBUEE | NIVEAU CLASSIFICATION: CONFIDENTIEL</p>", unsafe_allow_html=True)

# --- BARRE DE KPIs TACTIQUES ---
db = GISDatabaseManager()
zones = db.fetch_active_sectors()
active_fires = len([z for z in zones if z['priority'] == 'Critique'])
available_planes = len([f for f in FLEET_DATA if f['status'] == 'Disponible'])

kpi_html = f"""
<div class="kpi-grid">
    <div class="kpi-card alert-red"><div class="kpi-value">{active_fires}</div><div class="kpi-label">Foyers Critiques Actifs</div></div>
    <div class="kpi-card alert-green"><div class="kpi-value">{available_planes}</div><div class="kpi-label">Vecteurs Aériens Disponibles</div></div>
    <div class="kpi-card alert-orange"><div class="kpi-value">{np.random.randint(35, 65)} km/h</div><div class="kpi-label">Rafales de Vent Maximales</div></div>
    <div class="kpi-card"><div class="kpi-value">12.5°C</div><div class="kpi-label">Température Ambiante</div></div>
    <div class="kpi-card alert-red"><div class="kpi-value">EXTREME</div><div class="kpi-label">Indice de Risque Meteo</div></div>
</div>
"""
st.markdown(kpi_html, unsafe_allow_html=True)

# --- LAYOUT PRINCIPAL (CARTE + COMMANDE) ---
col_map, col_cmd = st.columns([3.5, 1.5])

with col_map:
    # --- CARTE FOLIUM AVANCÉE ---
    m = folium.Map(location=[36.35, 3.05], zoom_start=7, control_scale=True, tiles="CartoDB dark_all")
    
    # Couches
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri Satellite', name='Satellite IR', overlay=False, control=True).add_to(m)
    Draw(export=True, draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False}).add_to(m)
    MiniMap(toggle_display=True, position="bottomright").add_to(m)
    Fullscreen(position="topleft").add_to(m)

    # Flèche de Vent Dynamique (Centrée sur le théâtre)
    wind_icon = folium.DivIcon(html=f"""
        <div style="font-size: 40px; color: #00e5ff; transform: rotate({st.session_state.get('wind_dir', 180)}deg); text-shadow: 0 0 10px cyan;">
            ➤
        </div>
    """, icon_size=(40, 40), icon_anchor=(20, 20))
    folium.Marker([36.35, 3.05], icon=wind_icon, popup="Direction du Vent").add_to(m)

    # Données SIG
    for zone in zones:
        color = "darkred" if zone['priority'] == 'Critique' else "orange"
        popup_html = f"""
        <div style='background:#1b263b; color:white; padding:10px; border-radius:5px; font-family:sans-serif;'>
            <b style='color:#ff1744; font-size:16px;'>{zone['name']}</b><br>
            <span style='color:#90a4ae;'>Propagation:</span> <b>{zone['spread_rate']} km/h</b><br>
            <span style='color:#90a4ae;'>Statut:</span> <span style='color:{color};'>{zone['priority'].upper()}</span>
        </div>
        """
        folium.Marker([zone['lat'], zone['lon']], popup=folium.Popup(popup_html, max_width=300), icon=folium.Icon(color=color, icon="fire", prefix="fa")).add_to(m)

    # Jumeau Numérique (Heatmap Scénarios)
    if st.session_state.fire_grid is not None:
        sim = PhysicalFireSimulator(36.35, 3.05, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
        
        # Scénario Réel
        fire_coords = sim.get_fire_geojson(st.session_state.fire_grid)
        if fire_coords:
            HeatMap(fire_coords, radius=15, blur=10, gradient={0.4: '#ff9100', 0.7: '#ff1744', 1.0: '#d50000'}, name='🔥 Scénario Réel', overlay=True).add_to(m)
            
            # Scénario Pessimiste (Vent +30%, Humidité -20%) - Affiché en Violet
            pessimist_grid = sim.step_propagation(st.session_state.fire_grid, st.session_state.elevation, wind_speed*1.3, wind_dir, max(5, moisture*0.8))
            pessimist_coords = sim.get_fire_geojson(pessimist_grid)
            HeatMap(pessimist_coords, radius=20, blur=15, gradient={0.4: '#aa00ff', 1.0: '#6200ea'}, name='⚠️ Scénario Pessimiste', overlay=True).add_to(m)

    folium.LayerControl().add_to(m)
    st_data = st_folium(m, width="100%", height=550)

with col_cmd:
    st.subheader("🛩 ÉTAT DE LA FLOTTE AÉRIENNE")
    for aircraft in FLEET_DATA:
        status_color = "#00e676" if aircraft['status'] == "Disponible" else "#ff9100" if aircraft['status'] == "En Transit" else "#ff1744"
        st.markdown(f"""
        <div style='display:flex; justify-content:space-between; background:#0d1b2a; padding:8px; border-radius:4px; margin-bottom:5px; border-left: 3px solid {status_color};'>
            <span style='color:white; font-weight:bold;'>{aircraft['id']} ({aircraft['type']})</span>
            <span style='color:{status_color}; font-size:12px;'>{aircraft['status']}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("🧠 OPTIMISATION ILP")
    wind_speed = st.number_input("Vent (km/h)", min_value=0, max_value=120, value=65, key='wind_speed_input')
    st.session_state['wind_dir'] = st.number_input("Direction (°)", min_value=0, max_value=360, value=210)
    moisture = st.number_input("Humidité (%)", min_value=5, max_value=80, value=15)

    if st.button("⚡ CALCULER PLAN D'ENGAGEMENT", use_container_width=True):
        add_log("Exécution de l'algorithme d'optimisation stochastique (OR-Tools)...", "SYSTEM")
        with st.spinner("Résolution matricielle..."):
            allocation = optimize_aircraft_dispatch(zones, available_planes)
            st.success("PLAN GENERE")
            df_alloc = pd.DataFrame(allocation)
            st.dataframe(df_alloc, use_container_width=True, hide_index=True)
            for _, row in df_alloc.iterrows():
                if row['avions_assignes'] > 0:
                    add_log(f"AFFECTATION : {row['avions_assignes']} vecteur(s) engagé(s) sur {row['zone']}", "SUCCESS")

    st.markdown("---")
    st.subheader("🔬 SIMULATION JUMEAU")
    base_lat = 36.35; base_lon = 3.05
    if st.button("🔥 INITIALISER THEATRE", use_container_width=True):
        sim = PhysicalFireSimulator(base_lat, base_lon, rows=50, cols=50, cell_size_m=150)
        st.session_state.fire_grid = np.zeros((50, 50))
        st.session_state.fire_grid[25, 25] = 2
        st.session_state.elevation = np.random.uniform(200, 1200, (50, 50))
        add_log("Grille cellulaire 7.5km² initialisée. Point d'ignition détecté.", "ALERT")

    if st.button("⏩ PROPOSER +1 HEURE", use_container_width=True):
        if st.session_state.fire_grid is not None:
            add_log("Calcul de propagation Rothermel modifié (Vent, Pente, Humidité)...", "SYSTEM")
            sim = PhysicalFireSimulator(base_lat, base_lon, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
            new_grid = sim.step_propagation(st.session_state.fire_grid, st.session_state.elevation, wind_speed, st.session_state['wind_dir'], moisture)
            st.session_state.fire_grid = new_grid
            
            nb_foyers = len(sim.get_fire_geojson(new_grid))
            cells_burned = np.sum(new_grid == 1) + np.sum(new_grid == 2)
            surface_hectares = (cells_burned * (0.150 * 0.150)) * 100 
            add_log(f"PROJECTION : +{nb_foyers} foyers actifs. Surface totale estimée : {surface_hectares:.1f} Ha", "ALERT")
            st.metric("Surface Brûlée Projetée", f"{surface_hectares:.1f} Ha")

# --- TERMINAL DE LOGS TACTIQUES ---
st.markdown("<h4 style='margin-bottom:5px;'>📡 JOURNAL DES ÉVÉNEMENTS TACTIQUES (SYSLOG)</h4>", unsafe_allow_html=True)
log_html = f"<div class='tactical-log'>{''.join(st.session_state.tactical_logs)}</div>"
st.markdown(log_html, unsafe_allow_html=True)

# --- THREAD WEBSOCKET (Silencieux en arrière-plan) ---
async def fetch_iot_data():
    try:
        async with websockets.connect("ws://localhost:8765") as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("type") == "GPS_UPDATE":
                    tracks = st.session_state.iot_tracks
                    updated = False
                    for i, t in enumerate(tracks):
                        if t['id'] == data['payload']['id']: tracks[i] = data['payload']; updated = True; break
                    if not updated: tracks.append(data['payload'])
                    st.session_state.iot_tracks = tracks
    except Exception: pass

def run_ws(): 
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(fetch_iot_data())

if 'ws_thread_started' not in st.session_state:
    st.session_state.ws_thread_started = True
    threading.Thread(target=run_ws, daemon=True).start()
