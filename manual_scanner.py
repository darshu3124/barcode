import threading
import time

class ManualScanner:
    def __init__(self, callback):
        self.callback = callback
        self.running = True
        
    def start_listening(self):
        print("🎯 Manual barcode scanner started")
        print("📱 Type barcode data and press Enter to simulate scanning")
        print("⚠️  This terminal window must be focused")
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while self.running:
                try:
                    # Get input from user
                    barcode = input("Scan barcode (or type manually): ").strip()
                    
                    if barcode:
                        print(f"📱 Barcode scanned: {barcode}")
                        self.callback(barcode)
                        print("✅ Record added to attendance table")
                        print()
                        
                except KeyboardInterrupt:
                    print("\n🛑 Scanner stopped")
                    break
                except EOFError:
                    break
                    
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            self.running = False
    
    def stop(self):
        self.running = False

def test_callback(barcode):
    print(f"✅ Received barcode: {barcode}")

if __name__ == "__main__":
    scanner = ManualScanner(test_callback)
    scanner.start_listening()
