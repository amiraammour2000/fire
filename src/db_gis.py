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
        if not conn or not coordinates_list: return
        try:
            # Création d'un polygone simplifié à partir des points de feu
            if len(coordinates_list) < 3: return
            coords_str = ", ".join([f"{lon} {lat}" for lat, lon in coordinates_list])
            poly_str = f"POLYGON(({coords_str}, {coordinates_list[0][1]} {coordinates_list[0][0]}))"
            
            cursor = conn.cursor()
            query = sql.SQL("INSERT INTO fire_perimeters (geom) VALUES (ST_GeomFromText(%s, 4326))")
            cursor.execute(query, (poly_str,))
            conn.commit()
        except Exception as e:
            print(f"Erreur PostGIS: {e}")
        finally:
            if conn: conn.close()

    def fetch_active_sectors(self):
        # (Identique à la version précédente, retourne le mock si pas de DB)
        ...