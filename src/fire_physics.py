import numpy as np

class PhysicalFireSimulator:
    def __init__(self, base_lat, base_lon, cell_size_m=100, rows=50, cols=50):
        self.rows = rows
        self.cols = cols
        self.cell_size = cell_size_m
        self.base_lat = base_lat
        self.base_lon = base_lon
        # Approximation métrique pour conversion Lat/Lon (1 degré ~ 111km)
        self.lat_step = (cell_size_m / 111000.0)
        self.lon_step = (cell_size_m / (111000.0 * np.cos(np.radians(base_lat))))

    def step_propagation(self, grid, elevation_grid, wind_speed, wind_dir_deg, moisture):
        new_grid = grid.copy()
        rad = np.radians(wind_dir_deg)
        wx = np.cos(rad)
        wy = np.sin(rad)
        
        # Facteur de séchage (plus le vent est fort, plus l'humidité effective baisse)
        effective_moisture = max(5, moisture - (wind_speed * 0.2))

        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if grid[r, c] == 2: 
                    new_grid[r, c] = 1  
                    for dr in [-1, 0, 1]:
                        for dc in [-1, 0, 1]:
                            if dr == 0 and dc == 0: continue
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < self.rows and 0 <= nc < self.cols and grid[nr, nc] == 0:
                                # Pente
                                delta_h = elevation_grid[nr, nc] - elevation_grid[r, c]
                                slope_factor = delta_h / 10.0 
                                
                                # Vent (produit scalaire pour l'alignement)
                                dist = np.sqrt(dr**2 + dc**2)
                                alignment = (dr * wx + dc * wy) / (dist + 1e-5)
                                
                                # Modèle probabiliste de propagation
                                prob = (wind_speed / 80.0) * 0.5
                                prob += max(0, slope_factor) * 0.3
                                prob += max(0, alignment) * 0.4
                                prob *= (1.0 - (effective_moisture / 100.0))
                                
                                if np.random.rand() < max(0.01, prob):
                                    new_grid[nr, nc] = 2
        return new_grid

    def get_fire_geojson(self, grid):
        """ Convertit la grille en liste de coordonnées pour Folium """
        fire_coords = []
        for r in range(self.rows):
            for c in range(self.cols):
                if grid[r, c] == 2: # Feu actif
                    lat = self.base_lat - (r * self.lat_step)
                    lon = self.base_lon + (c * self.lon_step)
                    fire_coords.append([lat, lon])
        return fire_coords