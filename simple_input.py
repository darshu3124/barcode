import urllib.request
import urllib.parse
import json

def send_barcode(barcode):
    """Send barcode to the server using built-in libraries"""
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
    print("🎯 Simple Barcode Input")
    print("📱 Type student IDs and press Enter to add them to the attendance system")
    print("⚠️  Make sure the server is running at http://localhost:5050")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            try:
                # Get input from user
                barcode = input("Enter student ID: ").strip()
                
                if barcode:
                    print(f"📱 Sending barcode: {barcode}")
                    if send_barcode(barcode):
                        print("✅ Record added to attendance table!")
                    print()
                else:
                    print("Please enter a valid student ID")
                    
            except KeyboardInterrupt:
                print("\n🛑 Scanner stopped")
                break
            except EOFError:
                break
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
