import threading
import time
import sys
from pynput import keyboard
import queue

class KeyboardScanner:
    def __init__(self, callback):
        self.callback = callback
        self.barcode_buffer = ""
        self.last_char_time = time.time()
        self.barcode_timeout = 0.5  # 500ms timeout between characters
        self.scanner_active = True
        
    def on_key_press(self, key):
        try:
            # Handle special keys
            if key == keyboard.Key.enter:
                if self.barcode_buffer.strip():
                    print(f"📱 Barcode scanned: {self.barcode_buffer}")
                    self.callback(self.barcode_buffer.strip())
                self.barcode_buffer = ""
                return
            
            # Get character from key
            char = key.char if hasattr(key, 'char') and key.char else None
            
            if char:
                current_time = time.time()
                
                # If too much time has passed since last character, clear buffer
                if current_time - self.last_char_time > self.barcode_timeout:
                    self.barcode_buffer = ""
                
                self.barcode_buffer += char
                self.last_char_time = current_time
                
        except AttributeError:
            pass
    
    def start_listening(self):
        print("🎯 Keyboard barcode scanner started")
        print("📱 Scan barcodes with your scanner - they will be captured automatically")
        print("⚠️  Make sure to focus on the terminal window when scanning")
        print("Press Ctrl+C to stop")
        
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n🛑 Scanner stopped")
                self.scanner_active = False

def test_callback(barcode):
    print(f"✅ Received barcode: {barcode}")

if __name__ == "__main__":
    scanner = KeyboardScanner(test_callback)
    scanner.start_listening()
