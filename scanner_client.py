import requests
import time

def send_barcode(barcode):
    """Send barcode to the server"""
    try:
        response = requests.post('http://localhost:5050/api/test_scan', 
                               json={'barcode': barcode})
        if response.status_code == 200:
            print(f"✅ Barcode '{barcode}' sent successfully!")
            return True
        else:
            print(f"❌ Failed to send barcode: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error sending barcode: {e}")
        return False

def main():
    print("🎯 Barcode Scanner Client")
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
