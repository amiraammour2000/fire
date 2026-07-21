import asyncio
import json
import websockets
import random
import time

CONNECTED_CLIENTS = set()

async def simulate_iot_devices(websocket):
    """ Simule des déplacements de camions (CCF) et de drones """
    vehicles = [
        {"id": "CCF_01", "type": "truck", "lat": 43.6045, "lon": 7.0542},
        {"id": "DRONE_RECON_1", "type": "drone", "lat": 43.5900, "lon": 7.0600}
    ]
    while True:
        for v in vehicles:
            # Déplacement aléatoire réaliste
            v["lat"] += random.uniform(-0.0005, 0.0005)
            v["lon"] += random.uniform(-0.0005, 0.0005)
            payload = json.dumps({"type": "GPS_UPDATE", "payload": v})
            if CONNECTED_CLIENTS:
                await asyncio.wait([client.send(payload) for client in CONNECTED_CLIENTS])
        await asyncio.sleep(2) # Fréquence de télémétrie : 0.5 Hz

async def telemetry_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    try:
        # Lance la simulation en parallèle de l'écoute
        sim_task = asyncio.create_task(simulate_iot_devices(websocket))
        async for message in websocket:
            pass # Les messages entrants des vrais appareils seraient traités ici
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.remove(websocket)

async def main():
    async with websockets.serve(telemetry_handler, "0.0.0.0", 8765):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())