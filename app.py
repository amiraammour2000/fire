import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import pandas as pd
import asyncio
import json
import websockets
import threading

# On importe directement les fonctions de calcul (sans passer par Celery)
from src.fire_physics import PhysicalFireSimulator
from src.db_gis import GISDatabaseManager
from src.optimization import optimize_aircraft_dispatch

st.set_page_config(page_title="CODIS - C4ISR", layout="wide", initial_sidebar_state="expanded")

# Session state init
if 'fire_grid' not in st.session_state:
    st.session_state.fire_grid = None
if 'iot_tracks' not in st.session_state:
    st.session_state.iot_tracks = []
if 'elevation' not in st.session_state:
    st.session_state.elevation = None

st.title("🛡️ CODIS Next-Gen : Commandement et Optimisation Tactique")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Paramètres Environnementaux")
wind_speed = st.sidebar.slider("Vent (km/h)", 0, 120, 45)
wind_dir = st.sidebar.slider("Direction Vent (°)", 0, 360, 180)
moisture = st.sidebar.slider("Humidité (%)", 5, 80, 25)
available_aircrafts = st.sidebar.slider("Flotte aérienne disponible", 1, 20, 6)

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Initialisation Zone")
base_lat = st.sidebar.number_input("Latitude Centre", value=43.6045)
base_lon = st.sidebar.number_input("Longitude Centre", value=7.0542)

if st.sidebar.button("Initialiser la Grille Cellulaire"):
    sim = PhysicalFireSimulator(base_lat, base_lon, rows=40, cols=40)
    st.session_state.fire_grid = np.zeros((40, 40))
    st.session_state.fire_grid[20, 20] = 2 # Déclenchement du feu
    st.session_state.elevation = np.random.uniform(100, 600, (40, 40))
    st.sidebar.success("Grille 40x40 initialisée (1 cellule = 100m).")

# --- LAYOUT PRINCIPAL ---
col_map, col_cmd = st.columns([3, 2])

with col_map:
    st.subheader("🗺️ Common Operating Picture (COP)")
    m = folium.Map(location=[base_lat, base_lon], zoom_start=12, tiles="CartoDB positron")
    
    db = GISDatabaseManager()
    for zone in db.fetch_active_sectors():
        color = "darkred" if zone['priority'] == 'Critique' else "orange"
        folium.Marker(
            [zone['lat'], zone['lon']],
            popup=f"<b>{zone['name']}</b><br>Propag: {zone['spread_rate']} km/h",
            icon=folium.Icon(color=color, icon="fire", prefix="fa")
        ).add_to(m)

    for track in st.session_state.iot_tracks:
        icon = "truck" if track['type'] == 'truck' else "helicopter"
        color = "blue" if track['type'] == 'truck' else "purple"
        folium.Marker(
            [track['lat'], track['lon']],
            popup=f"<b>{track['id']}</b>",
            icon=folium.Icon(color=color, icon=icon, prefix="fa")
        ).add_to(m)

    if st.session_state.fire_grid is not None:
        sim = PhysicalFireSimulator(base_lat, base_lon, rows=st.session_state.fire_grid.shape[0], cols=st.session_state.fire_grid.shape[1])
        fire_coords = sim.get_fire_geojson(st.session_state.fire_grid)
        for coords in fire_coords:
            folium.CircleMarker(
                location=coords, radius=40, color='red', fill=True, fill_opacity=0.7
            ).add_to(m)

    st_data = st_folium(m, width="100%", height=500)

with col_cmd:
    st.subheader("🧠 Optimisation Mathématique (ILP)")
    if st.button("Calculer le Dispatching Tactique"):
        with st.spinner("Solveur OR-Tools en cours de calcul..."):
            zones = db.fetch_active_sectors()
            # EXÉCUTION SYNCHRONE DIRECTE (Compatible Streamlit Cloud)
            allocation = optimize_aircraft_dispatch(zones, available_aircrafts)
            
            st.success("Plan d'engagement validé !")
            df_alloc = pd.DataFrame(allocation)
            st.dataframe(df_alloc, use_container_width=True, hide_index=True)
            
            if not df_alloc.empty and df_alloc['risque_residuel'].max() > 10:
                st.error("⚠️ ALERTE : Risque résiduel critique sur un secteur. Demande de renfort conseillée.")

    st.markdown("---")
    st.subheader("🔬 Jumeau Numérique (Cell2Fire)")
    if st.button("Simuler Propagation +1h"):
        if st.session_state.fire_grid is not None:
            with st.spinner("Calcul physique de propagation..."):
                # EXÉCUTION SYNCHRONE DIRECTE (Compatible Streamlit Cloud)
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
                st.metric(label="Nouveaux Foyers Actifs", value=nb_foyers)
        else:
            st.warning("Veuillez initialiser la grille dans la barre latérale.")

# --- THREAD DE TÉLÉMÉTRIE EN ARRIÈRE-PLAN ---
async def fetch_iot_data():
    # On utilise un try/except silencieux car le serveur WebSocket n'est pas lancé sur Streamlit Cloud
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
        pass # Échec silencieux de la connexion IoT si le serveur externe est absent

def run_websocket_listener():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_iot_data())

if 'ws_thread_started' not in st.session_state:
    st.session_state.ws_thread_started = True
    threading.Thread(target=run_websocket_listener, daemon=True).start()

st_autorefresh = st.empty()
st_autorefresh.button("Actualiser le COP", key="refresh_cop")
