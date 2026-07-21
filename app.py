import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MiniMap, Draw, Fullscreen
import numpy as np
import pandas as pd
import asyncio
import json
import websockets
import threading

from src.fire_physics import PhysicalFireSimulator
from src.db_gis import GISDatabaseManager
from src.optimization import optimize_aircraft_dispatch

# --- CONFIGURATION UI TACTIQUE (CSS PERSONNALISÉ) ---
st.markdown("""
<style>
    /* Thème Militaire C4ISR */
    .main {
        background-color: #0a0f1a;
        color: #e0e6ed;
    }
    .stSidebar {
        background-color: #0d1321;
        border-right: 2px solid #1e3a5f;
    }
    h1, h2, h3 {
        color: #00d4ff !important;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-family: 'Courier New', monospace;
    }
    .stButton>button {
        background-color: #1e3a5f;
        color: white;
        border: 1px solid #00d4ff;
        font-weight: bold;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #00d4ff;
        color: #0a0f1a;
        box-shadow: 0 0 15px #00d4ff;
    }
    div[data-testid="stMetricValue"] {
        color: #ff4d4d;
        font-size: 24px;
        font-weight: bold;
    }
    /* Cacher le menu hamburger et le footer pour un vrai écran de commande */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="CODIS ALGERIE - C4ISR", layout="wide", initial_sidebar_state="expanded")

# Session state init
if 'fire_grid' not in st.session_state:
    st.session_state.fire_grid = None
if 'iot_tracks' not in st.session_state:
    st.session_state.iot_tracks = []
if 'elevation' not in st.session_state:
    st.session_state.elevation = None

st.title("🇩🇿 CODIS ALGÉRIE : Système de Commandement Tactique")

# --- SIDEBAR ---
st.sidebar.header("⚙️ ENVIORNEMENT & METEO")
# Conditions typiques de l'été algérien pour les feux de forêt
wind_speed = st.sidebar.slider("VENT (km/h) - Sirocco/Marin", 0, 120, 65)
wind_dir = st.sidebar.slider("DIRECTION VENT (°)", 0, 360, 210)
moisture = st.sidebar.slider("HUMIDITE RELATIVE (%)", 5, 80, 15) # Très sec
available_aircrafts = st.sidebar.slider("FLotte AERIENNE (CANADAIR/BE200)", 1, 20, 8)

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 INITIALISATION THEATRE")
# Coordonnées par défaut : Vue globale du Nord de l'Algérie (Tell)
base_lat = st.sidebar.number_input("Latitude Centre", value=36.3500, format="%.4f")
base_lon = st.sidebar.number_input("Longitude Centre", value=3.0500, format="%.4f")

if st.sidebar.button("🔥 DECLANCHER SIMULATION LOCALE", use_container_width=True):
    sim = PhysicalFireSimulator(base_lat, base_lon, rows=50, cols=50, cell_size_m=150)
    st.session_state.fire_grid = np.zeros((50, 50))
    st.session_state.fire_grid[25, 25] = 2 # Point d'ignition
    # Topographie aléatoire pour simuler les reliefs de l'Atlas Tellien
    st.session_state.elevation = np.random.uniform(200, 1200, (50, 50)) 
    st.sidebar.success("Théâtre d'opération activé (Grille 7.5km x 7.5km).")

# --- LAYOUT PRINCIPAL ---
col_map, col_cmd = st.columns([3.5, 1.5])

with col_map:
    st.subheader("👁️ COMMON OPERATING PICTURE (COP)")
    
    # Initialisation de la carte avec fond sombre par défaut
    m = folium.Map(location=[base_lat, base_lon], zoom_start=7, control_scale=True, tiles="CartoDB darkmatter")
    
    # 1. AJOUT DE COUCHES CARTOGRAPHIQUES AVANCEES
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri Satellite',
        name='🛰️ Imagerie Satellite (IR)',
        overlay=False,
        control=True
    ).add_to(m)
    
    # 2. OUTILS DE DESSIN TACTIQUE (Tracer des zones d'exclusion, périmètres)
    Draw(export=True, draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False}).add_to(m)
    
    # 3. MINIMAP (Vue d'ensemble en bas à droite)
    MiniMap(toggle_display=True, position="bottomright").add_to(m)
    
    # 4. MODE PLEIN ECRAN
    Fullscreen(position="topleft").add_to(m)

    # 5. DONNEES SIG (DEPLACEMENT VERS L'ALGERIE DANS LE MOCK DB)
    db = GISDatabaseManager()
    for zone in db.fetch_active_sectors():
        color = "darkred" if zone['priority'] == 'Critique' else "orange"
        folium.Marker(
            [zone['lat'], zone['lon']],
            popup=f"<b>{zone['name']}</b><br>Propagation: {zone['spread_rate']} km/h<br>Statut: {zone['priority']}",
            icon=folium.Icon(color=color, icon="fire", prefix="fa")
        ).add_to(m)

    # 6. TELEMETRIE IoT (Drones/CCF)
    for track in st.session_state.iot_tracks:
        icon = "truck" if track['type'] == 'truck' else "helicopter"
        color = "blue" if track['type'] == 'truck' else "cyan"
        folium.Marker(
            [track['lat'], track['lon']],
            popup=f"<b>{track['id']}</b><br>Vitesse: {np.random.randint(40,120)} km/h",
            icon=folium.Icon(color=color, icon=icon, prefix="fa")
        ).add_to(m)

    # 7. JUMEAU NUMERIQUE : HEATMAP (Vue Thermique du feu)
    if st.session_state.fire_grid is not None:
        sim = PhysicalFireSimulator(base_lat, base_lon, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
        fire_coords = sim.get_fire_geojson(st.session_state.fire_grid)
        
        if fire_coords:
            # Affichage Heatmap (Nécessite des poids, on met 1.0 pour une intensité maximale uniforme)
            HeatMap(fire_coords, radius=18, blur=15, gradient={0.2: '#0a0f1a', 0.4: '#ff9900', 0.6: '#ff3300', 1.0: '#ff0000'}, name='🔥 Front Thermique').add_to(m)
            
            # Affichage ponctuel du coeur du feu
            for coords in fire_coords:
                folium.CircleMarker(
                    location=coords, radius=5, color='#ff0000', fill=True, fill_opacity=0.9, weight=0
                ).add_to(m)

    # Ajout du contrôle des couches pour switcher entre Satellite/Nuit/Thermique
    folium.LayerControl().add_to(m)

    # Rendu final de la carte
    st_data = st_folium(m, width="100%", height=650)

with col_cmd:
    st.subheader("🧠 OPTIMISATION ILP")
    if st.button("⚡ CALCULER DISPATCHING", use_container_width=True):
        with st.spinner("Résolution matricielle en cours..."):
            zones = db.fetch_active_sectors()
            allocation = optimize_aircraft_dispatch(zones, available_aircrafts)
            
            st.success("PLAN DE VOL GENERE")
            df_alloc = pd.DataFrame(allocation)
            st.dataframe(df_alloc, use_container_width=True, hide_index=True)
            
            if not df_alloc.empty and df_alloc['risque_residuel'].max() > 10:
                st.error("🚨 RISQUE CRITIQUE : Demande de renfort BE200/EC225 urgente.")

    st.markdown("---")
    st.subheader("🔬 PROPAGATION CELL2FIRE")
    if st.button("⏩ SIMULER +1 HEURE", use_container_width=True):
        if st.session_state.fire_grid is not None:
            with st.spinner("Calcul Rothermel modifié..."):
                sim = PhysicalFireSimulator(
                    base_lat=base_lat, base_lon=base_lon, 
                    rows=st.session_state.fire_grid.shape[0], 
                    cols=st.session_state.fire_grid.shape[1]
                )
                
                new_grid = sim.step_propagation(
                    st.session_state.fire_grid, 
                    st.session_state.elevation, 
                    wind_speed, wind_dir, moisture
                )
                
                st.session_state.fire_grid = new_grid
                fire_coords = sim.get_fire_geojson(new_grid)
                nb_foyers = len(fire_coords)
                
                # Calcul de la surface brûlée estimée (nombre de cellules * surface cellule)
                cells_burned = np.sum(new_grid == 1) + np.sum(new_grid == 2)
                surface_hectares = (cells_burned * (0.150 * 0.150)) * 100  # cellule 150m -> ha
                
                col1, col2 = st.columns(2)
                col1.metric(label="FOYERS ACTIFS", value=nb_foyers)
                col2.metric(label="SURFACE BRÛLÉE", value=f"{surface_hectares:.1f} Ha")
        else:
            st.warning("Initialisez la grille dans le menu de gauche.")

# --- THREAD DE TÉLÉMÉTRIE ---
async def fetch_iot_data():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("type") == "GPS_UPDATE":
                    tracks = st.session_state.iot_tracks
                    updated = False
                    for i, t in enumerate(tracks):
                        if t['id'] == data['payload']['id']:
                            tracks[i] = data['payload']
                            updated = True
                            break
                    if not updated:
                        tracks.append(data['payload'])
                    st.session_state.iot_tracks = tracks
    except Exception:
        pass

def run_websocket_listener():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_iot_data())

if 'ws_thread_started' not in st.session_state:
    st.session_state.ws_thread_started = True
    threading.Thread(target=run_websocket_listener, daemon=True).start()
