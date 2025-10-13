import os
import sqlite3
from datetime import datetime
from threading import Thread

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO

# Flask setup
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll TEXT NOT NULL,
                name TEXT,
                class TEXT,
                date TEXT NOT NULL,
                in_time TEXT NOT NULL,
                out_time TEXT,
                status TEXT NOT NULL
            )
            """
        )
        conn.commit()


def determine_in_out(conn, roll):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, status FROM attendance WHERE roll=? AND status=? ORDER BY id DESC LIMIT 1",
        (roll, "In Library"),
    )
    row = cur.fetchone()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if row:
        record_id = row[0]
        cur.execute(
            "UPDATE attendance SET out_time=?, status=? WHERE id=?",
            (time_str, "Completed", record_id),
        )
        conn.commit()
        return {
            "roll": roll,
            "name": f"Student {roll}",
            "class": "BCA",
            "date": date_str,
            "inTime": "",
            "outTime": time_str,
            "status": "Completed",
            "action": "Walk-Out",
        }
    else:
        cur.execute(
            "INSERT INTO attendance (roll, name, class, date, in_time, status) VALUES (?,?,?,?,?,?)",
            (roll, f"Student {roll}", "BCA", date_str, time_str, "In Library"),
        )
        conn.commit()
        return {
            "roll": roll,
            "name": f"Student {roll}",
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
            "SELECT roll, name, class, date, in_time, out_time, status FROM attendance ORDER BY id DESC LIMIT 1000"
        )
        rows = cur.fetchall()
        data = [
            {
                "roll": r[0],
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


def on_barcode(barcode_value: str):
    barcode_value = (barcode_value or "").strip()
    if not barcode_value:
        return
    with sqlite3.connect(DB_PATH) as conn:
        record = determine_in_out(conn, barcode_value)
    socketio.emit("barcode_scanned", {"barcode": barcode_value, "record": record})


def start_barcode_listener():
    # Import late to avoid circular import when SocketIO forks
    import barcode_reader

    barcode_reader.start_listener(on_barcode)


if __name__ == "__main__":
    init_db()

    # Start barcode listener in a background thread
    listener_thread = Thread(target=start_barcode_listener, daemon=True)
    listener_thread.start()

    socketio.run(app, host="0.0.0.0", port=5000)


