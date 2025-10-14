import os
import sqlite3
from datetime import datetime
from threading import Thread


from flask import Flask, render_template, jsonify, request, send_file
import json
from flask_socketio import SocketIO
from flask import Flask, session, redirect, url_for, render_template, request
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "replace_with_your_secret"

# --- session behaviour ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=1)
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"


# Make sessions temporary and short-lived
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = 0

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


@app.get("/export/excel")
@app.get("/export/excel")
@app.get("/export/excel")
def export_excel():
    """
    Export attendance to a single Excel file and open it automatically in Excel.
    """
    try:
        import pandas as pd
        from openpyxl import load_workbook
    except Exception as e:
        return jsonify({"error": f"Required libraries missing: {e}"}), 500

    file_path = os.path.join(BASE_DIR, "attendance.xlsx")

    # Get all attendance records
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                barcode AS Roll_Number,
                name AS Name,
                section AS Section,
                class AS Class,
                date AS Date,
                in_time AS Walk_In_Time,
                out_time AS Walk_Out_Time,
                status AS Status
            FROM attendance
            ORDER BY id ASC
            """,
            conn,
        )

    # Write / update Excel file
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Attendance")

    # ✅ Try to open Excel automatically (Windows only)
    try:
        os.startfile(file_path)
    except Exception as e:
        print(f"⚠️ Could not open Excel automatically: {e}")

    # Also return the file as a download (optional)
    return send_file(
        file_path,
        as_attachment=True,
        download_name="attendance.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/export/pdf")
def export_pdf():
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
    except Exception as e:
        return jsonify({"error": f"reportlab not available: {e}"}), 500

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance ORDER BY id ASC"
        )
        rows = cur.fetchall()

    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    elements = []

    data = [[
        "Roll",
        "Name",
        "Section",
        "Class",
        "Date",
        "In Time",
        "Out Time",
        "Status",
    ]]

    for r in rows:
        data.append([
            r[0] or "",
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            r[6] or "",
            r[7] or "",
        ])

    table = Table(data, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype="application/pdf",
    )


@app.post("/clear_data")
def clear_data():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM attendance")
        conn.commit()
    # Let clients know data was cleared (optional UI refresh hook)
    socketio.emit("data_cleared", {"success": True})
    return jsonify({"success": True})


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

from flask import session, redirect, url_for, render_template_string

# ===== Simple Admin Login System =====

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"  # 🔒 change this to your password

@app.route("/login", methods=["GET", "POST"])
def login():
    from flask import request
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


# Protect the dashboard route
@app.before_request
def require_login():
    open_routes = (
        "login",
        "static",
        "api_start_scanner",
        "get_attendance",
        "export_excel",
        "export_pdf",
    )
    if request.endpoint in open_routes or request.endpoint is None:
        return

    # Force login every new window by re-checking cookie
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
    # Start scanner automatically
    start_barcode_listener_background()
    # Run Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=5000)


