import os
import sqlite3
import threading
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, render_template, jsonify, request, send_file, session, redirect, url_for, render_template_string
import json
from flask_socketio import SocketIO

app = Flask(__name__)
app.secret_key = "replace_with_your_secret"

# --- Session behaviour ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=1)
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = 0

socketio = SocketIO(app, cors_allowed_origins="*")

# SQLite database path
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

# --- Load students ---
all_students = {}

def _normalize_student(raw: dict) -> dict:
    name = (
        raw.get("name")
        or raw.get("student_name")
        or raw.get("fullName")
        or raw.get("studentName")
        or ""
    )
    section = raw.get("section") or raw.get("class") or raw.get("dept") or ""
    clazz = raw.get("section") or raw.get("class") or raw.get("dept") or "—"
    return {"name": name, "section": section, "class": clazz}


def _load_students():
    global all_students
    all_students = {}
    candidates = []
    student_dir = os.path.join(BASE_DIR, "student_data")
    if os.path.isdir(student_dir):
        for fname in os.listdir(student_dir):
            if fname.lower().endswith(".json"):
                candidates.append(os.path.join(student_dir, fname))

    for legacy in ("final_year.json", "second_year.json"):
        legacy_path = os.path.join(BASE_DIR, legacy)
        if os.path.exists(legacy_path):
            candidates.append(legacy_path)

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "students" in data and isinstance(data["students"], list):
                for s in data["students"]:
                    roll = str(s.get("roll") or s.get("roll_no") or s.get("id") or "").strip()
                    if not roll:
                        continue
                    all_students[roll.upper()] = _normalize_student(s)
            elif isinstance(data, dict):
                for k, v in data.items():
                    roll = str(k).strip()
                    if not roll:
                        continue
                    v = v if isinstance(v, dict) else {}
                    all_students[roll.upper()] = _normalize_student(v)
        except Exception as e:
            print(f"Failed to load students from {path}: {e}")


# --- Database Setup ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
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
        """)
        conn.commit()
        try:
            cur.execute("ALTER TABLE attendance ADD COLUMN section TEXT")
            conn.commit()
        except Exception:
            pass


# --- Determine In/Out ---
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
        (barcode, student_name or f"Student {barcode}", section or "—", (section or "—"), date_str, time_str, "In Library"),
    )
    conn.commit()
    return {
        "roll": barcode,
        "barcode": barcode,
        "name": student_name or f"Student {barcode}",
        "class": section or "—",
        "section": section or "—",
        "date": date_str,
        "inTime": time_str,
        "outTime": "—",
        "status": "In Library",
        "action": "Walk-In",
    }


# --- Real-time Summary Update Function ---
def emit_summary_update():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")

        cur.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (today,))
        total_walkins = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='Completed'", (today,))
        total_walkouts = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='In Library'", (today,))
        active_students = cur.fetchone()[0] or 0

    socketio.emit("update_summary", {
        "walkins": total_walkins,
        "walkouts": total_walkouts,
        "active": active_students
    })


# --- Routes ---
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


@app.route('/api/clear_attendance', methods=['DELETE'])
def clear_attendance():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM attendance")
        conn.commit()
        conn.close()
        emit_summary_update()  # 🔄 refresh after clearing
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# --- Barcode Callback ---
def on_barcode(barcode_value: str):
    barcode_value = (barcode_value or "").strip()
    if not barcode_value:
        return
    with sqlite3.connect(DB_PATH) as conn:
        student = all_students.get(barcode_value.upper()) or {}
        student_name = (student.get("name") or "").strip() or None
        section = (student.get("section") or "").strip() or None
        record = determine_in_out(conn, barcode_value, student_name, section)
    payload = {
        "roll_no": barcode_value,
        "student_name": record.get("name") if student_name else "Student not found",
        "section": section or "—",
        "action": record.get("action"),
        "time": record.get("outTime") or record.get("inTime"),
    }
    socketio.emit("barcode_scanned", payload)
    emit_summary_update()  # 🔄 emit live summary update


# --- Background Scanner ---
_scanner_thread = None

def start_barcode_listener_background():
    global _scanner_thread
    if _scanner_thread and _scanner_thread.is_alive():
        return False

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


# --- Admin Login ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid credentials")
    return render_template_string(LOGIN_TEMPLATE, error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def require_login():
    open_routes = (
        "login",
        "static",
        "api_start_scanner",
        "get_attendance",
        "export_excel",
        "export_pdf",
        "clear_attendance",
    )
    if request.endpoint in open_routes or request.endpoint is None:
        return
    if not session.get("logged_in"):
        return redirect(url_for("login"))


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Admin Login</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 flex items-center justify-center h-screen">
  <div class="bg-white p-8 rounded-2xl shadow-md w-80">
    <h1 class="text-xl font-bold text-slate-800 mb-4 text-center">Admin Login</h1>
    {% if error %}
    <p class="text-red-600 text-sm mb-3 text-center">{{ error }}</p>
    {% endif %}
    <form method="POST">
      <label class="block text-sm text-slate-600 mb-1">Username</label>
      <input type="text" name="username" class="w-full border border-slate-300 rounded-lg p-2 mb-3 focus:outline-none focus:ring-2 focus:ring-emerald-500">
      <label class="block text-sm text-slate-600 mb-1">Password</label>
      <input type="password" name="password" class="w-full border border-slate-300 rounded-lg p-2 mb-4 focus:outline-none focus:ring-2 focus:ring-emerald-500">
      <button class="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-2 rounded-lg font-semibold">Login</button>
    </form>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    _load_students()
    init_db()
    start_barcode_listener_background()
    socketio.run(app, host="0.0.0.0", port=5001)

# --- Exports ---
@app.get("/export/excel")
def export_excel():
    import io, csv
    # Build CSV in-memory (Excel opens CSV nicely). We name it .csv for correctness.
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Roll", "Name", "Section", "Class", "Date", "Walk-In Time", "Walk-Out Time", "Status"])
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance ORDER BY id ASC"
        )
        for r in cur.fetchall():
            writer.writerow([
                r[0] or "",
                r[1] or "",
                r[2] or "",
                r[3] or "",
                r[4] or "",
                r[5] or "",
                (r[6] or "—"),
                r[7] or "",
            ])
    # Encode with BOM so Excel recognizes UTF-8
    data = output.getvalue().encode("utf-8-sig")
    mem = io.BytesIO(data)
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name="attendance.csv",
    )


@app.get("/export/pdf")
def export_pdf():
    # Optional dependency: reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except Exception:
        return jsonify({
            "success": False,
            "error": "PDF export not configured. Install reportlab or use CSV export.",
            "hint": "pip install reportlab"
        }), 501

    import io
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 2*cm, "Library Attendance Report")
    c.setFont("Helvetica", 9)
    y = height - 3*cm

    headers = ["Roll", "Name", "Section", "Class", "Date", "In", "Out", "Status"]
    c.drawString(2*cm, y, " | ".join(headers))
    y -= 0.6*cm

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance ORDER BY id ASC"
        )
        for r in cur.fetchall():
            row = [
                str(r[0] or ""), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""),
                str(r[4] or ""), str(r[5] or ""), str(r[6] or "—"), str(r[7] or "")
            ]
            c.drawString(2*cm, y, " | ".join(row)[:110])
            y -= 0.5*cm
            if y < 2*cm:
                c.showPage()
                c.setFont("Helvetica", 9)
                y = height - 2*cm

    c.showPage()
    c.save()

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="attendance.pdf",
    )