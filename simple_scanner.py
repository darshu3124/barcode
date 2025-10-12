import sys
import threading
import time

class SimpleBarcodeScanner:
    def __init__(self, callback):
        self.callback = callback
        self.running = False
        self.barcode_buffer = ""
        self.last_input_time = time.time()
        
    def start_listening(self):
        """Start listening for barcode input"""
        self.running = True
        print("🎯 Simple barcode scanner started")
        print("📱 Scan barcodes with your scanner - they will be captured automatically")
        print("⚠️  Make sure this terminal window is focused when scanning")
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while self.running:
                try:
                    # Read input from stdin
                    user_input = input()
                    
                    if user_input.strip():
                        # This is likely a barcode scan
                        barcode = user_input.strip()
                        print(f"📱 Barcode scanned: {barcode}")
                        self.callback(barcode)
                        
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print("\n🛑 Scanner stopped")
                    break
                    
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Stop the scanner"""
        self.running = False

def test_callback(barcode):
    print(f"✅ Received barcode: {barcode}")

if __name__ == "__main__":
    scanner = SimpleBarcodeScanner(test_callback)
    scanner.start_listening()
