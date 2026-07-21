import os
import psycopg2
from psycopg2 import sql

class GISDatabaseManager:
    def __init__(self):
        self.conn_str = os.getenv("DATABASE_URL", "dbname=codis_geo_db user=codis_admin password=secure_password host=localhost port=5432")

    def get_connection(self):
        try:
            conn = psycopg2.connect(self.conn_str)
            self._init_db(conn)
            return conn
        except Exception:
            # Fallback en mode simulation mémoire si la DB n'est pas instanciée
            return None

    def _init_db(self, conn):
        """ Crée les tables spatiales si elles n'existent pas """
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fire_perimeters (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                geom GEOMETRY(POLYGON, 4326)
            );
        """)
        conn.commit()
        cursor.close()

    def save_fire_perimeter(self, coordinates_list):
        """ Sauvegarde un front de feu sous forme de polygone PostGIS """
        conn = self.get_connection()
        if not conn or not coordinates_list: 
            return
        try:
            # Création d'un polygone simplifié à partir des points de feu
            if len(coordinates_list) < 3: 
                return
            coords_str = ", ".join([f"{lon} {lat}" for lat, lon in coordinates_list])
            # Fermeture du polygone en reliant le dernier point au premier
            poly_str = f"POLYGON(({coords_str}, {coordinates_list[0][1]} {coordinates_list[0][0]}))"
            
            cursor = conn.cursor()
            query = sql.SQL("INSERT INTO fire_perimeters (geom) VALUES (ST_GeomFromText(%s, 4326))")
            cursor.execute(query, (poly_str,))
            conn.commit()
        except Exception as e:
            print(f"Erreur PostGIS: {e}")
        finally:
            if conn: 
                conn.close()

    def fetch_active_sectors(self):
        """ Récupère les secteurs d'intervention depuis PostGIS ou retourne un Mock """
        conn = self.get_connection()
        
        # Si pas de connexion DB, on retourne les données de simulation (Mock)
        if not conn:
            return [
                {"id": 1, "name": "Secteur Massif Est", "lat": 43.6100, "lon": 7.0600, "priority": "Critique", "spread_rate": 8.5},
                {"id": 2, "name": "Vallée Sud-Ouest", "lat": 43.5950, "lon": 7.0450, "priority": "Moyenne", "spread_rate": 4.2},
                {"id": 3, "name": "Crête Nord", "lat": 43.6150, "lon": 7.0500, "priority": "Haute", "spread_rate": 6.8}
            ]
            
        # Si la DB est connectée, on fait la vraie requête spatiale
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, ST_Y(geom) as lat, ST_X(geom) as lon, priority, spread_rate FROM sectors;")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return [{"id": r[0], "name": r[1], "lat": r[2], "lon": r[3], "priority": r[4], "spread_rate": r[5]} for r in rows]
        except Exception as e:
            # En cas d'erreur de requête (ex: table inexistante), on retourne le Mock
            print(f"Erreur de requête SQL: {e}")
            return [
                {"id": 1, "name": "Secteur Massif Est", "lat": 43.6100, "lon": 7.0600, "priority": "Critique", "spread_rate": 8.5},
                {"id": 2, "name": "Vallée Sud-Ouest", "lat": 43.5950, "lon": 7.0450, "priority": "Moyenne", "spread_rate": 4.2}
            ]
