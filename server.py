# server.py
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import threading
import both_test
import manual_scanner
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def barcode_listener(barcode):
    print("📡 Barcode received:", barcode)
    socketio.emit('barcode_scanned', {'barcode': barcode})

def run_scanner():
    print("🎯 Starting barcode scanner...")
    print("📱 The system will listen for barcode input from:")
    print("   1. Physical barcode scanner (if connected)")
    print("   2. Manual keyboard input")
    print("   3. Test interface in web browser")
    print()
    
    # Start manual scanner (works reliably)
    try:
        print("🎯 Starting manual barcode scanner...")
        scanner = manual_scanner.ManualScanner(barcode_listener)
        scanner.start_listening()
    except Exception as e:
        print("❌ Manual scanner error:", e)
        print("🔄 Falling back to USB scanner...")
        try:
            both_test.main_listener(barcode_listener)
        except Exception as e2:
            print("❌ USB scanner also failed:", e2)
            print("💡 You can still use the test interface in the web browser")

@app.route("/api/start_scanner", methods=["POST"])
def start_scanner():
    t = threading.Thread(target=run_scanner, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Scanner started"})

@app.route("/api/test_scan", methods=["POST"])
def test_scan():
    """Test endpoint to simulate a barcode scan"""
    data = request.get_json()
    test_barcode = data.get('barcode', 'TEST123')
    
    # Simulate receiving a barcode
    barcode_listener(test_barcode)
    
    return jsonify({"success": True, "message": f"Test barcode '{test_barcode}' sent"})

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route("/attendance_data.json")
def serve_attendance_data():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'attendance_data.json')

@app.route("/logo.jpg")
def serve_logo():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'logo.jpg')

@socketio.on('connect')
def handle_connect():
    print("✅ Frontend connected")

if __name__ == "__main__":
    print("🚀 Starting Flask SocketIO server on http://localhost:5050")
    socketio.run(app, host="0.0.0.0", port=5050)
