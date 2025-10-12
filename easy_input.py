import urllib.request
import urllib.parse
import json

def send_barcode(barcode):
    """Send barcode to the server"""
    try:
        url = 'http://localhost:5050/api/test_scan'
        data = json.dumps({'barcode': barcode}).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        
        if response.status == 200:
            print(f"✅ Barcode '{barcode}' sent successfully!")
            return True
        else:
            print(f"❌ Failed to send barcode: {response.status}")
            return False
    except Exception as e:
        print(f"❌ Error sending barcode: {e}")
        return False

def main():
    print("=" * 50)
    print("🎯 EASY BARCODE INPUT")
    print("=" * 50)
    print("📱 Type student IDs and press Enter")
    print("⚠️  Make sure server is running at http://localhost:5050")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    print()
    
    try:
        while True:
            print("Enter student ID: ", end="", flush=True)
            barcode = input()
            
            if barcode.strip():
                print(f"📱 Sending: {barcode}")
                if send_barcode(barcode):
                    print("✅ Record added to attendance table!")
                print("-" * 30)
            else:
                print("❌ Please enter a valid student ID")
                print("-" * 30)
                
    except KeyboardInterrupt:
        print("\n🛑 Scanner stopped")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
