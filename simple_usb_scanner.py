import usb.core
import usb.util
import threading
import time

class SimpleUSBScanner:
    def __init__(self, callback):
        self.callback = callback
        self.scanner_device = None
        self.running = False
        
    def find_scanner(self):
        """Find the barcode scanner device"""
        print("🔍 Looking for USB barcode scanner...")
        
        try:
            # Get all USB devices
            devices = list(usb.core.find(find_all=True))
            print(f"Found {len(devices)} USB devices")
            
            # Look for devices that might be scanners
            for dev in devices:
                try:
                    vendor_id = dev.idVendor
                    product_id = dev.idProduct
                    
                    print(f"Checking device: Vendor=0x{vendor_id:04X}, Product=0x{product_id:04X}")
                    
                    # Try to access the device to see if it's our scanner
                    try:
                        # Set configuration
                        dev.set_configuration()
                        cfg = dev.get_active_configuration()
                        intf = cfg[(0, 0)]
                        
                        # Find IN endpoint
                        ep = usb.util.find_descriptor(
                            intf,
                            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                        )
                        
                        if ep:
                            print(f"✅ Found potential scanner: Vendor=0x{vendor_id:04X}, Product=0x{product_id:04X}")
                            self.scanner_device = dev
                            return True
                            
                    except Exception as e:
                        print(f"  Not a scanner: {e}")
                        continue
                        
                except Exception as e:
                    print(f"  Error checking device: {e}")
                    continue
                    
            print("❌ No suitable scanner found")
            return False
            
        except Exception as e:
            print(f"❌ Error finding devices: {e}")
            return False
    
    def read_scanner(self):
        """Read data from the scanner"""
        if not self.scanner_device:
            return
            
        try:
            dev = self.scanner_device
            dev.set_configuration()
            cfg = dev.get_active_configuration()
            intf = cfg[(0, 0)]
            
            ep = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )
            
            print(f"🎯 Scanner ready on endpoint {hex(ep.bEndpointAddress)}")
            
            barcode_buffer = ""
            last_char_time = time.time()
            
            while self.running:
                try:
                    data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout=1000)
                    
                    # Convert USB data to characters (simplified)
                    if data and len(data) > 2:
                        char_code = data[2]  # HID keycode
                        
                        # Simple keycode to character mapping
                        if char_code == 40:  # Enter
                            if barcode_buffer:
                                print(f"📱 Barcode scanned: {barcode_buffer}")
                                self.callback(barcode_buffer)
                                barcode_buffer = ""
                        elif char_code != 0:
                            # Map keycode to character (simplified)
                            char_map = {
                                4: 'a', 5: 'b', 6: 'c', 7: 'd', 8: 'e', 9: 'f', 10: 'g', 11: 'h',
                                12: 'i', 13: 'j', 14: 'k', 15: 'l', 16: 'm', 17: 'n', 18: 'o', 19: 'p',
                                20: 'q', 21: 'r', 22: 's', 23: 't', 24: 'u', 25: 'v', 26: 'w', 27: 'x',
                                28: 'y', 29: 'z',
                                30: '1', 31: '2', 32: '3', 33: '4', 34: '5', 35: '6', 36: '7', 37: '8',
                                38: '9', 39: '0'
                            }
                            
                            char = char_map.get(char_code, '')
                            if char:
                                barcode_buffer += char
                                last_char_time = time.time()
                    
                except usb.core.USBError as e:
                    if e.errno in (110, 10060):  # timeout
                        # Check if we have a partial barcode
                        if barcode_buffer and (time.time() - last_char_time > 0.5):
                            print(f"📱 Barcode scanned: {barcode_buffer}")
                            self.callback(barcode_buffer)
                            barcode_buffer = ""
                        continue
                    elif e.errno == 19:  # device disconnected
                        print("📱 Scanner disconnected")
                        break
                    else:
                        print(f"USB Error: {e}")
                        break
                        
        except Exception as e:
            print(f"❌ Error reading scanner: {e}")
    
    def start(self):
        """Start the scanner"""
        if self.find_scanner():
            self.running = True
            print("🚀 Starting USB barcode scanner...")
            thread = threading.Thread(target=self.read_scanner, daemon=True)
            thread.start()
            return True
        return False
    
    def stop(self):
        """Stop the scanner"""
        self.running = False

def test_callback(barcode):
    print(f"✅ Received barcode: {barcode}")

if __name__ == "__main__":
    scanner = SimpleUSBScanner(test_callback)
    
    if scanner.start():
        try:
            print("Scanner running... Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping scanner...")
            scanner.stop()
    else:
        print("❌ Failed to start scanner")
