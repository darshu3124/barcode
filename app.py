import os
import sqlite3
from datetime import datetime
from threading import Thread

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

# Flask + SocketIO
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
socketio = SocketIO(app, cors_allowed_origins="*")

# SQLite database path (attendance.db as requested)
DB_PATH = os.path.join(os.path.dirname(__file__), "attendance.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT,
                name TEXT,
                class TEXT,
                date TEXT,
                in_time TEXT,
                out_time TEXT,
                status TEXT
            )
            """
        )
        conn.commit()


def determine_in_out(conn: sqlite3.Connection, barcode: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM attendance WHERE barcode=? AND status=? ORDER BY id DESC LIMIT 1",
        (barcode, "In Library"),
    )
    row = cur.fetchone()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if row:  # Walk-Out
        record_id = row[0]
        cur.execute(
            "UPDATE attendance SET out_time=?, status=? WHERE id=?",
            (time_str, "Completed", record_id),
        )
        conn.commit()
        return {
            "roll": barcode,
            "barcode": barcode,
            "name": f"Student {barcode}",
            "class": "BCA",
            "date": date_str,
            "inTime": "",
            "outTime": time_str,
            "status": "Completed",
            "action": "Walk-Out",
        }

    # Walk-In
    cur.execute(
        "INSERT INTO attendance (barcode, name, class, date, in_time, status) VALUES (?,?,?,?,?,?)",
        (barcode, f"Student {barcode}", "BCA", date_str, time_str, "In Library"),
    )
    conn.commit()
    return {
        "roll": barcode,
        "barcode": barcode,
        "name": f"Student {barcode}",
        "class": "BCA",
        "date": date_str,
        "inTime": time_str,
        "outTime": "—",
        "status": "In Library",
        "action": "Walk-In",
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/attendance")
def get_attendance():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT barcode, name, class, date, in_time, out_time, status FROM attendance ORDER BY id DESC LIMIT 1000"
        )
        rows = cur.fetchall()
        data = [
            {
                "roll": r[0],  # keep compatibility with UI
                "barcode": r[0],
                "name": r[1],
                "class": r[2],
                "date": r[3],
                "inTime": r[4],
                "outTime": r[5] if r[5] else "—",
                "status": r[6],
            }
            for r in rows
        ]
        return jsonify({"attendance": list(reversed(data))})


# Callback used by scanner thread
def on_barcode(barcode_value: str):
    barcode_value = (barcode_value or "").strip()
    if not barcode_value:
        return
    with sqlite3.connect(DB_PATH) as conn:
        record = determine_in_out(conn, barcode_value)
    socketio.emit("barcode_scanned", {"barcode": barcode_value, "record": record})


# Background scanner control
_scanner_thread = None


def start_barcode_listener_background():
    global _scanner_thread
    if _scanner_thread and _scanner_thread.is_alive():
        return False

    # Delay import to avoid side effects at module import time
    from both_test import main_listener

    def run():
        try:
            main_listener(on_barcode)
        except Exception as e:
            print(f"Scanner listener exited: {e}")

    _scanner_thread = Thread(target=run, daemon=True)
    _scanner_thread.start()
    return True


@app.post("/api/start_scanner")
def api_start_scanner():
    started = start_barcode_listener_background()
    return jsonify({"success": True, "started": started})


if __name__ == "__main__":
    init_db()
    # Start scanner automatically
    start_barcode_listener_background()
    # Run Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=5000)


