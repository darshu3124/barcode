import os
import sqlite3
from datetime import datetime
from threading import Thread

from flask import Flask, render_template, jsonify, request
import json
from flask_socketio import SocketIO

# Flask + SocketIO
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
socketio = SocketIO(app, cors_allowed_origins="*")

# SQLite database path (attendance.db as requested)
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

# Load student JSONs at startup and merge
all_students = {}
def _load_students():
    global all_students
    all_students = {}
    candidates = [
        os.path.join(BASE_DIR, "c2f1a953-67a8-4504-8f16-7cb9a8dc6ed2.json"),
        os.path.join(BASE_DIR, "3a4c0fa1-1768-4eb9-826e-0d8a953dc60f.json"),
    ]
    for path in candidates:
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Accept either {roll: {...}} or {"students": [{roll:..., name:...}]}
            if isinstance(data, dict) and "students" in data and isinstance(data["students"], list):
                for s in data["students"]:
                    roll = str(s.get("roll") or s.get("roll_no") or s.get("id") or "").strip()
                    if not roll:
                        continue
                    all_students[roll.upper()] = s
            elif isinstance(data, dict):
                for k, v in data.items():
                    all_students[str(k).upper()] = v
        except Exception as e:
            print(f"Failed to load students from {path}: {e}")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT,
                name TEXT,
                section TEXT,
                class TEXT,
                date TEXT,
                in_time TEXT,
                out_time TEXT,
                status TEXT
            )
            """
        )
        conn.commit()
        # Ensure 'section' column exists if DB was created earlier without it
        try:
            cur.execute("ALTER TABLE attendance ADD COLUMN section TEXT")
            conn.commit()
        except Exception:
            pass


def determine_in_out(conn: sqlite3.Connection, barcode: str, student_name: str | None, section: str | None):
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
            "name": student_name or f"Student {barcode}",
            "class": "BCA",
            "section": section or "—",
            "date": date_str,
            "inTime": "",
            "outTime": time_str,
            "status": "Completed",
            "action": "Walk-Out",
        }

    # Walk-In
    cur.execute(
        "INSERT INTO attendance (barcode, name, section, class, date, in_time, status) VALUES (?,?,?,?,?,?,?)",
        (barcode, student_name or f"Student {barcode}", section or "—", "BCA", date_str, time_str, "In Library"),
    )
    conn.commit()
    return {
        "roll": barcode,
        "barcode": barcode,
        "name": student_name or f"Student {barcode}",
        "class": "BCA",
        "section": section or "—",
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
            "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance ORDER BY id DESC LIMIT 1000"
        )
        rows = cur.fetchall()
        data = [
            {
                "roll": r[0],
                "barcode": r[0],
                "name": r[1],
                "section": r[2],
                "class": r[3],
                "date": r[4],
                "inTime": r[5],
                "outTime": r[6] if r[6] else "—",
                "status": r[7],
            }
            for r in rows
        ]
        return jsonify({"attendance": list(reversed(data))})


@app.get("/api/student/<roll_no>")
def get_student(roll_no: str):
    if not roll_no:
        return jsonify({"error": "roll_no required"}), 400
    rec = all_students.get(str(roll_no).upper())
    if not rec:
        return jsonify({"error": "Student not found"}), 404
    return jsonify(rec)


# Callback used by scanner thread
def on_barcode(barcode_value: str):
    barcode_value = (barcode_value or "").strip()
    if not barcode_value:
        return
    with sqlite3.connect(DB_PATH) as conn:
        student = all_students.get(barcode_value.upper()) or {}
        student_name = student.get("name") or student.get("student_name") or student.get("fullName")
        section = student.get("section") or student.get("class") or student.get("dept")
        record = determine_in_out(conn, barcode_value, student_name, section)
    payload = {
        "roll_no": barcode_value,
        "student_name": record.get("name") if student_name else "Student not found",
        "section": section or "—",
        "action": record.get("action"),
        "time": record.get("outTime") or record.get("inTime"),
    }
    socketio.emit("barcode_scanned", payload)


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
    _load_students()
    init_db()
    # Start scanner automatically
    start_barcode_listener_background()
    # Run Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=5000)


