import os
from celery import Celery
from src.optimization import optimize_aircraft_dispatch
from src.fire_physics import PhysicalFireSimulator
import numpy as np

redis_host = os.getenv("REDIS_HOST", "localhost")
celery_app = Celery('codis_tasks', broker=f'redis://{redis_host}:6379/0', backend=f'redis://{redis_host}:6379/0')

@celery_app.task(name='tasks.run_heavy_optimization')
def run_heavy_optimization(zones_data, available_aircrafts):
    allocation = optimize_aircraft_dispatch(zones_data, available_aircrafts)
    return {"status": "SUCCESS", "allocation": allocation}

@celery_app.task(name='tasks.run_fire_simulation')
def run_fire_simulation(grid_state, elevation, wind_speed, wind_dir, moisture, base_lat, base_lon):
    sim = PhysicalFireSimulator(base_lat=base_lat, base_lon=base_lon, rows=grid_state.shape[0], cols=grid_state.shape[1])
    grid_array = np.array(grid_state)
    new_grid = sim.step_propagation(grid_array, np.array(elevation), wind_speed, wind_dir, moisture)
    
    # Retourne la grille et les coordonnées GPS des nouveaux foyers
    fire_coords = sim.get_fire_geojson(new_grid)
    return {"grid": new_grid.tolist(), "geo_coords": fire_coords}