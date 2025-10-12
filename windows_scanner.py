import subprocess
import re
import time
import threading

class WindowsUSBScanner:
    def __init__(self, callback):
        self.callback = callback
        self.running = False
        
    def get_usb_devices(self):
        """Get USB devices using Windows Device Manager"""
        try:
            # Use PowerShell to get USB devices
            cmd = ['powershell', '-Command', 
                   'Get-PnpDevice -Class USB | Select-Object FriendlyName, InstanceId | Format-Table -AutoSize']
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                devices = []
                
                for line in lines:
                    if 'VID_' in line and 'PID_' in line:
                        # Extract vendor and product IDs
                        vid_match = re.search(r'VID_([0-9A-F]{4})', line)
                        pid_match = re.search(r'PID_([0-9A-F]{4})', line)
                        
                        if vid_match and pid_match:
                            vendor_id = int(vid_match.group(1), 16)
                            product_id = int(pid_match.group(1), 16)
                            
                            devices.append({
                                'vendor_id': vendor_id,
                                'product_id': product_id,
                                'name': line.strip()
                            })
                
                return devices
            else:
                print(f"Error getting devices: {result.stderr}")
                return []
                
        except Exception as e:
            print(f"Error: {e}")
            return []
    
    def find_scanner(self):
        """Find barcode scanner in USB devices"""
        print("🔍 Looking for USB barcode scanner using Windows Device Manager...")
        
        devices = self.get_usb_devices()
        
        if not devices:
            print("❌ No USB devices found")
            return None
            
        print(f"Found {len(devices)} USB devices:")
        
        for i, device in enumerate(devices):
            vendor_hex = f"0x{device['vendor_id']:04X}"
            product_hex = f"0x{device['product_id']:04X}"
            
            print(f"  {i+1}. {device['name']}")
            print(f"     Vendor: {vendor_hex}, Product: {product_hex}")
            
            # Check if this looks like a barcode scanner
            if any(keyword in device['name'].lower() 
                   for keyword in ['scanner', 'barcode', 'qr', 'symbol', 'honeywell', 'zebra', 'winusb']):
                print(f"     🎯 This looks like a barcode scanner!")
                return device
        
        print("❌ No barcode scanner found in USB devices")
        print("\nIf you see your scanner listed above, note the Vendor and Product IDs")
        return None
    
    def start(self):
        """Start the scanner detection"""
        scanner = self.find_scanner()
        
        if scanner:
            print(f"\n✅ Found scanner: {scanner['name']}")
            print(f"   Vendor ID: 0x{scanner['vendor_id']:04X}")
            print(f"   Product ID: 0x{scanner['product_id']:04X}")
            print("\n📝 To use this scanner, update your both_test.py file:")
            print(f"   {{\"vendor\": {scanner['vendor_id']}, \"product\": {scanner['product_id']}, \"prefix\": \"scan1\"}}")
            return True
        else:
            print("\n💡 Tips:")
            print("1. Make sure your scanner is connected")
            print("2. Verify WinUSB driver is installed via Zadig")
            print("3. Run this script as Administrator if needed")
            return False

def test_callback(barcode):
    print(f"✅ Received barcode: {barcode}")

if __name__ == "__main__":
    scanner = WindowsUSBScanner(test_callback)
    scanner.start()
