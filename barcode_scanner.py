import sys
import threading
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory storage for attendance data
attendance_data = []

def barcode_listener(barcode):
    """Handle barcode input"""
    print(f"📡 Barcode received: {barcode}")
    
    # Add to attendance data
    from datetime import datetime
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_date = now.strftime("%m/%d/%Y")
    
    # Check if student already has an active session
    existing_record = None
    for record in attendance_data:
        if record['roll'] == barcode and record['status'] == 'In Library':
            existing_record = record
            break
    
    if existing_record:
        # Student is walking out
        existing_record['outTime'] = current_time
        existing_record['status'] = 'Completed'
        action = 'Walk-Out'
    else:
        # Student is walking in
        new_record = {
            'roll': barcode,
            'name': f'Student {barcode}',
            'class': 'BCA',
            'date': current_date,
            'inTime': current_time,
            'outTime': '—',
            'status': 'In Library'
        }
        attendance_data.append(new_record)
        action = 'Walk-In'
    
    # Send to frontend
    socketio.emit('barcode_scanned', {'barcode': barcode, 'action': action})
    print(f"✅ {action}: {barcode}")

def read_barcode_input():
    """Read barcode input from stdin"""
    print("🎯 Barcode Scanner Ready")
    print("📱 Scan barcodes with your scanner - they will be captured automatically")
    print("⚠️  Make sure this terminal window is focused when scanning")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            try:
                # Read input from stdin
                barcode = input().strip()
                
                if barcode:
                    barcode_listener(barcode)
                    
            except KeyboardInterrupt:
                print("\n🛑 Scanner stopped")
                break
            except EOFError:
                break
                
    except Exception as e:
        print(f"❌ Error: {e}")

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route("/api/attendance")
def get_attendance():
    return jsonify({"attendance": attendance_data})

@app.route("/api/test_scan", methods=["POST"])
def test_scan():
    """Test endpoint to simulate a barcode scan"""
    data = request.get_json()
    test_barcode = data.get('barcode', 'TEST123')
    barcode_listener(test_barcode)
    return jsonify({"success": True, "message": f"Test barcode '{test_barcode}' sent"})

if __name__ == "__main__":
    print("🚀 Starting Barcode Scanner System...")
    print("📱 Server will run on http://localhost:5050")
    print()
    
    # Start barcode input reader in a separate thread
    scanner_thread = threading.Thread(target=read_barcode_input, daemon=True)
    scanner_thread.start()
    
    # Start the web server
    socketio.run(app, host="0.0.0.0", port=5050)
