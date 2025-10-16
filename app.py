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
        # Prefer outTime only if it's a real timestamp; otherwise use inTime
        "time": (record.get("outTime") if record.get("outTime") not in (None, "", "—") else record.get("inTime")),
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


# --- Exports ---
@app.get("/export/excel")
def export_excel():
    # Try to generate a real XLSX; if openpyxl is missing, fall back to CSV
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Side, Border
        import io

        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"

        # Small info box with selected class/department
        department_label = (request.args.get("department") or "").strip()
        display_class = department_label if department_label and department_label.lower() != "all" else "All Classes"
        ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=3)
        ws.cell(row=1, column=1, value=f"Class: {display_class}")
        ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=1, column=1).font = Font(bold=True)
        box_border = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
        for r in range(1, 3):
            for c in range(1, 4):
                ws.cell(row=r, column=c).border = box_border

        # Blank row and then headers (Class column removed)
        headers = [
            "Roll", "Name", "Date", "Walk-In Time", "Walk-Out Time", "Status"
        ]
        ws.append([])
        ws.append(headers)
        bold = Font(bold=True)
        header_row = 4
        for idx in range(1, len(headers) + 1):
            ws.cell(row=header_row, column=idx).font = bold

        def fetch_rows_with_filters(cur):
            clauses = []
            params = []
            department = (request.args.get("department") or "").strip()
            start_date = (request.args.get("startDate") or "").strip()
            end_date = (request.args.get("endDate") or "").strip()

            if department and department.lower() != "all":
                clauses.append("(LOWER(class) LIKE ? OR LOWER(section) LIKE ?)")
                like = f"%{department.lower()}%"
                params.extend([like, like])
            if start_date:
                clauses.append("date >= ?")
                params.append(start_date)
            if end_date:
                clauses.append("date <= ?")
                params.append(end_date)

            where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            sql = (
                "SELECT barcode, name, section, class, date, in_time, out_time, status "
                "FROM attendance" + where_sql + " ORDER BY id ASC"
            )
            cur.execute(sql, params)
            return cur.fetchall()

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            rows = fetch_rows_with_filters(cur)
            for r in rows:
                # Exclude Class column in exported table
                ws.append([
                    r[0] or "",
                    r[1] or "",
                    r[4] or "",
                    r[5] or "",
                    (r[6] or "—"),
                    r[7] or "",
                ])

        # Formatting: freeze header, wrap, auto-width (skip merged title box)
        ws.freeze_panes = "A5"  # data starts at row 5
        max_row = ws.max_row
        max_col = 6  # number of table columns
        for col_cells in ws.iter_cols(min_row=4, max_row=max_row, min_col=1, max_col=max_col):
            max_len = 0
            first_cell = col_cells[0]
            col_letter = first_cell.column_letter
            for cell in col_cells:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                value = "" if cell.value is None else str(cell.value)
                if len(value) > max_len:
                    max_len = len(value)
            ws.column_dimensions[col_letter].width = max(10, min(45, max_len + 2))

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        return send_file(
            bio,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="attendance.xlsx",
        )
    except Exception:
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        # Info line and headers (Class column removed)
        department_label = (request.args.get("department") or "").strip()
        display_class = department_label if department_label and department_label.lower() != "all" else "All Classes"
        writer.writerow([f"Class: {display_class}"])
        writer.writerow([])
        writer.writerow(["Roll", "Name", "Date", "Walk-In Time", "Walk-Out Time", "Status"])
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            # Reuse the same filtering logic as above
            clauses = []
            params = []
            department = (request.args.get("department") or "").strip()
            start_date = (request.args.get("startDate") or "").strip()
            end_date = (request.args.get("endDate") or "").strip()

            if department and department.lower() != "all":
                clauses.append("(LOWER(class) LIKE ? OR LOWER(section) LIKE ?)")
                like = f"%{department.lower()}%"
                params.extend([like, like])
            if start_date:
                clauses.append("date >= ?")
                params.append(start_date)
            if end_date:
                clauses.append("date <= ?")
                params.append(end_date)

            where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            sql = (
                "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance"
                + where_sql + " ORDER BY id ASC"
            )
            cur.execute(sql, params)
            for r in cur.fetchall():
                # Exclude Class column
                writer.writerow([
                    r[0] or "",
                    r[1] or "",
                    r[4] or "",
                    r[5] or "",
                    (r[6] or "—"),
                    r[7] or "",
                ])
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
    # Use fpdf for portability
    try:
        from fpdf import FPDF
        import io

        class PDF(FPDF):
            pass

        pdf = PDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, 'Library Attendance Report', ln=1)

        # Info box with selected class/department
        department_label = (request.args.get("department") or "").strip()
        display_class = department_label if department_label and department_label.lower() != "all" else "All Classes"
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(60, 8, f'Class: {display_class}', border=1, ln=1)
        pdf.ln(2)

        # Table header (Class removed)
        headers = ["Roll", "Name", "Date", "In", "Out", "Status"]
        col_widths = [25, 60, 25, 20, 20, 25]
        pdf.set_font('Helvetica', 'B', 10)
        for h, w in zip(headers, col_widths):
            pdf.cell(w, 7, h, border=1)
        pdf.ln()

        # Rows
        pdf.set_font('Helvetica', '', 10)
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            clauses = []
            params = []
            department = (request.args.get("department") or "").strip()
            start_date = (request.args.get("startDate") or "").strip()
            end_date = (request.args.get("endDate") or "").strip()
            if department and department.lower() != "all":
                clauses.append("(LOWER(class) LIKE ? OR LOWER(section) LIKE ?)")
                like = f"%{department.lower()}%"
                params.extend([like, like])
            if start_date:
                clauses.append("date >= ?")
                params.append(start_date)
            if end_date:
                clauses.append("date <= ?")
                params.append(end_date)
            where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            sql = (
                "SELECT barcode, name, section, class, date, in_time, out_time, status FROM attendance"
                + where_sql + " ORDER BY id ASC"
            )
            cur.execute(sql, params)
            for r in cur.fetchall():
                cells = [
                    str(r[0] or ""), str(r[1] or ""),
                    str(r[4] or ""), str(r[5] or ""), str(r[6] or "—"), str(r[7] or "")
                ]
                for text, w in zip(cells, col_widths):
                    # truncate long text
                    txt = text if len(text) <= 32 else text[:31] + '…'
                    pdf.cell(w, 6, txt, border=1)
                pdf.ln()

        return send_file(
            io.BytesIO(pdf.output(dest='S').encode('latin-1')),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='attendance.pdf',
        )
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"PDF export failed: {str(e)}",
            "hint": "Check server logs for details"
        }), 500


if __name__ == "__main__":
    _load_students()
    init_db()
    start_barcode_listener_background()
    socketio.run(app, host="0.0.0.0", port=5001)