import asyncio
import torch
import websockets
import json
import cv2
import numpy as np
import mss
import time
from ultralytics import YOLO
import threading
import sqlite3
import datetime


def init_db(db_path="parking_lot.db"):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spot_name TEXT NOT NULL,
            occupied BOOLEAN NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_occupied_duration REAL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spot_name TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

db_conn = init_db()

def get_current_pricing(conn, parking_spots):
    cursor = conn.cursor()
    pricing = {}
    for spot in parking_spots:
        cursor.execute("SELECT price FROM pricing WHERE spot_name = ? ORDER BY timestamp DESC LIMIT 1", (spot["name"],))
        result = cursor.fetchone()
        pricing[spot["name"]] = result[0] if result else 1.5
    return pricing



# YOLO Modell laden
model = YOLO('finetuned11x.pt')  


# Bildschirmbereich für die Aufnahme definieren (ggf. anpassen)
with mss.mss() as sct:
    monitor = sct.monitors[1]

# Manuell definierte Parkplatzflächen 
parking_spots = [
    {"coords": ((100, 1000), (120, 1020)), "name": "Slot1"},
    {"coords": ((200, 1030), (220, 1050)), "name": "Slot2"},
    {"coords": ((500, 1020), (520, 1040)), "name": "Slot3"},
    {"coords": ((410, 1100), (430, 1120)), "name": "Slot4"},
    {"coords": ((580, 1180), (600, 1200)), "name": "Slot5"},
    {"coords": ((770, 1220), (790, 1240)), "name": "Slot6"},
    {"coords": ((290, 1080), (310, 1100)), "name": "Slot7"},
    {"coords": ((1040, 1290), (1060, 1310)), "name": "Slot8"},
    {"coords": ((1220, 1350), (1240, 1370)), "name": "Slot9"},
    {"coords": ((1490, 1420), (1510, 1440)), "name": "Slot10"},
    {"coords": ((1720, 1450), (1740, 1460)), "name": "Slot11"},
    {"coords": ((1860, 1500), (1880, 1520)), "name": "Slot12"},
    {"coords": ((2250, 1580), (2270, 1600)), "name": "Slot13"},
    {"coords": ((2820, 1610), (2840, 1630)), "name": "Slot14"},
    {"coords": ((900, 910), (920, 930)), "name": "Slot15"},
    {"coords": ((1010, 930), (1030, 950)), "name": "Slot16"},
    {"coords": ((1110, 935), (1130, 955)), "name": "Slot17"},
    {"coords": ((1200, 935), (1220, 955)), "name": "Slot18"},
    {"coords": ((1350, 945), (1370, 965)), "name": "Slot19"},
    {"coords": ((1485, 955), (1505, 975)), "name": "Slot20"},
    {"coords": ((1620, 970), (1640, 990)), "name": "Slot21"},
    {"coords": ((1770, 990), (1790, 1010)), "name": "Slot22"},
    {"coords": ((1925, 990), (1945, 1010)), "name": "Slot23"},
    {"coords": ((2075, 1025), (2095, 1045)), "name": "Slot24"},
    {"coords": ((2200, 1040), (2220, 1060)), "name": "Slot25"},
    {"coords": ((2320, 1040), (2350, 1060)), "name": "Slot26"}
  
]

# Status der Parkplätze (wird zur WebSocket-Übertragung verwendet)
occupied_spots = [False] * len(parking_spots)

# Funktion zum Starten des WebSocket-Servers
async def websocket_server(websocket, path):
    global occupied_spots
    while True:
        current_pricing = get_current_pricing(db_conn, parking_spots)
        # Sende aktuelle Belegung der Parkplätze als JSON
        data = json.dumps({
            "occupied_spots": occupied_spots,
            "pricing": current_pricing
        })
        await websocket.send(data)
        await asyncio.sleep(1)  # Aktualisierungsintervall

# Funktion zum Starten des WebSocket-Servers
def start_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = websockets.serve(websocket_server, "localhost", 8765)
    loop.run_until_complete(server)
    loop.run_forever()

def update_parking_status_db(conn, parking_spots, occupied_spots):
    cursor = conn.cursor()
    
    for spot, occupied in zip(parking_spots, occupied_spots):
        # Letzten Status abrufen
        cursor.execute("""
            SELECT occupied, timestamp, total_occupied_duration 
            FROM parking_status WHERE spot_name = ? 
            ORDER BY timestamp DESC LIMIT 1
        """, (spot["name"],))
        result = cursor.fetchone()

        if result:
            last_occupied, last_timestamp, total_duration = result
            last_timestamp = datetime.datetime.strptime(last_timestamp, "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            duration = (now - last_timestamp).total_seconds() / 3600  # in Stunden

            # Wenn der Parkplatz vorher belegt war und immer noch belegt ist, kumuliert sich nichts
            if last_occupied and occupied:
                new_total_duration = total_duration
            # Wenn er vorher belegt war und jetzt frei wird, wird die Dauer hinzugefügt
            elif last_occupied and not occupied:
                new_total_duration = total_duration + duration
            else:
                new_total_duration = total_duration  # Keine Änderung wenn vorher frei und immer noch frei

        else:
            new_total_duration = 0  # Falls noch kein Eintrag existiert

        # Neuen Status einfügen
        cursor.execute("""
            INSERT INTO parking_status (spot_name, occupied, total_occupied_duration)
            VALUES (?, ?, ?)
        """, (spot["name"], occupied, new_total_duration))

    conn.commit()


def calculate_dynamic_pricing(conn, parking_spots, occupied_spots):
    cursor = conn.cursor()
    
    # Gesamtbelegungsgrad berechnen
    total_spots = len(parking_spots)
    occupied_count = sum(occupied_spots)
    total_occupied_ratio = occupied_count / total_spots  # Anteil belegter Parkplätze

    # Historische Belegungsdauer abrufen
    parking_durations = {}
    for spot in parking_spots:
        cursor.execute("""
            SELECT total_occupied_duration FROM parking_status WHERE spot_name = ? 
            ORDER BY timestamp DESC LIMIT 1
        """, (spot["name"],))
        result = cursor.fetchone()
        parking_durations[spot["name"]] = result[0] if result else 0

    max_duration = max(parking_durations.values(), default=1)  # Vermeidung von 0-Division

    # Preise für jeden Parkplatz berechnen
    for spot, occupied in zip(parking_spots, occupied_spots):
        cursor.execute("SELECT price FROM pricing WHERE spot_name = ? ORDER BY timestamp DESC LIMIT 1", (spot["name"],))
        result = cursor.fetchone()
        last_price = result[0] if result else 1.5  # Standardpreis 1.5€

        # Belegungsdauer relativ zum längsten belegten Parkplatz
        parking_duration_factor = parking_durations[spot["name"]] / max_duration if max_duration > 0 else 0

        if occupied:
            # Preiserhöhung: abhängig vom Gesamtbelegungsgrad & individueller Belegungsdauer
            new_price = last_price * (1.05 + (0.3 * total_occupied_ratio) + (0.15 * parking_duration_factor))
            new_price = min(new_price, 3.0)  # Maximal 3€
        else:
            # Preisreduktion: langsamere Senkung, aber nicht unter 1.5€
            new_price = max(last_price * 0.95, 1.5)
        new_price = round(new_price, 2)

        cursor.execute(
            "INSERT INTO pricing (spot_name, price) VALUES (?, ?)",
            (spot["name"], new_price)
        )

    conn.commit()

# Funktion, um zu prüfen, ob eine Bounding Box in einem Parkplatz liegt
def is_vehicle_in_parking_spot(vehicle_box, spot):
    (vx1, vy1, vx2, vy2) = vehicle_box
    (sx1, sy1), (sx2, sy2) = spot
    # Berechne die Überlappung zwischen Fahrzeug und Parkplatz
    overlap_x = max(0, min(vx2, sx2) - max(vx1, sx1))
    overlap_y = max(0, min(vy2, sy2) - max(vy1, sy1))
    overlap_area = overlap_x * overlap_y
    parking_spot_area = (sx2 - sx1) * (sy2 - sy1)
    # Prüfen, ob mindestens 10% des Parkplatzes durch das Fahrzeug überlappt werden
    return overlap_area > 0.1 * parking_spot_area

# Funktion für YOLO-Erkennung und Bildschirmaufnahme
def yolo_detection():
    global occupied_spots

    with mss.mss() as sct:
        while True:
            start_time = time.time()

            # Bildschirmbereich aufnehmen
            screenshot = np.array(sct.grab(monitor))
            frame = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

            # YOLO Modell anwenden
            results = model(frame)

            # Belegung der Parkplätze zurücksetzen
            occupied_spots = [False] * len(parking_spots)

            # Zeichnen der Erkennungsergebnisse
            for result in results:
                boxes = result.boxes  # Alle erkannten Boxen
                for box in boxes:
                    # Extrahiere Box-Koordinaten und Klasse
                    x1, y1, x2, y2 = map(int, box.xyxy[0])  # Box-Koordinaten
                    confidence = box.conf[0]  # Zuverlässigkeit
                    class_id = int(box.cls[0])  # Klassen-ID

                    # Filtern nach Fahrzeugklassen anhand der IDs 0 und 1
                    if class_id in [0, 1] and confidence > 0.5:
                        # Zeichne die Box und das Label
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        label = f"Class {class_id} {int(confidence * 100)}%"
                        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                        # Prüfe, ob das Fahrzeug in einem der Parkplätze ist
                        for i, spot in enumerate(parking_spots):
                            if is_vehicle_in_parking_spot((x1, y1, x2, y2), spot["coords"]):
                                occupied_spots[i] = True

            # Zeichne die Parkplätze und fülle belegte und freie Plätze
            for i, spot in enumerate(parking_spots):
                (sx1, sy1), (sx2, sy2) = spot["coords"]
                color = (0, 0, 255) if occupied_spots[i] else (0, 255, 0)  # Rot für belegt, Grün für frei
                # Fülle das Rechteck mit der entsprechenden Farbe
                cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), color, -1)
                # Text "Besetzt" oder "Frei" und Parkplatzname hinzufügen
                status = f"{spot['name']} - {'Besetzt' if occupied_spots[i] else 'Frei'}"
                text_color = (255, 255, 255)  # Weißer Text für bessere Lesbarkeit
                cv2.putText(frame, status, (sx1, sy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 2)

            update_parking_status_db(db_conn, parking_spots, occupied_spots)
            calculate_dynamic_pricing(db_conn, parking_spots, occupied_spots)

            # Zeige das Ergebnis im Fenster an
            cv2.imshow("Parkplatz-Detektion", frame)

            # Beenden, wenn 'q' gedrückt wird
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # Ressourcen freigeben
    cv2.destroyAllWindows()

# Hauptfunktion für den WebSocket-Server und YOLO
if __name__ == "__main__":
    # Startet den WebSocket-Server in einem separaten Thread
    websocket_thread = threading.Thread(target=start_websocket_server)
    websocket_thread.start()

    # Startet YOLO-Erkennung im Hauptthread
    yolo_detection()

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")