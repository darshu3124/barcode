import usb.core
import usb.util

def find_scanner():
    """Find USB devices that might be barcode scanners"""
    print("🔍 Searching for USB barcode scanners...")
    print("Make sure your scanner is connected and WinUSB driver is installed via Zadig")
    print()
    
    try:
        # Try different backend configurations
        backends = [
            None,  # Default backend
            usb.backend.libusb1.get_backend(),
            usb.backend.libusb0.get_backend()
        ]
        
        devices_found = False
        
        for i, backend in enumerate(backends):
            print(f"Trying backend {i+1}...")
            try:
                devices = list(usb.core.find(find_all=True, backend=backend))
                if devices:
                    devices_found = True
                    print(f"✅ Found {len(devices)} USB devices with backend {i+1}")
                    
                    for j, dev in enumerate(devices):
                        try:
                            vendor_id = f'0x{dev.idVendor:04X}'
                            product_id = f'0x{dev.idProduct:04X}'
                            
                            # Try to get device info
                            try:
                                manufacturer = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "Unknown"
                            except:
                                manufacturer = "Unknown"
                                
                            try:
                                product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "Unknown"
                            except:
                                product = "Unknown"
                            
                            print(f"  Device {j+1}:")
                            print(f"    Vendor ID: {vendor_id}")
                            print(f"    Product ID: {product_id}")
                            print(f"    Manufacturer: {manufacturer}")
                            print(f"    Product: {product}")
                            
                            # Check if this looks like a barcode scanner
                            if any(keyword in manufacturer.lower() or keyword in product.lower() 
                                   for keyword in ['scanner', 'barcode', 'qr', 'symbol', 'honeywell', 'zebra']):
                                print(f"    🎯 This looks like a barcode scanner!")
                                print(f"    📝 Add this to your scanner config:")
                                print(f"    {{\"vendor\": {dev.idVendor}, \"product\": {dev.idProduct}, \"prefix\": \"scan{len(devices)}\"}}")
                            print()
                            
                        except Exception as e:
                            print(f"    Error reading device {j+1}: {e}")
                    
                    break  # Found devices, no need to try other backends
                else:
                    print(f"❌ No devices found with backend {i+1}")
                    
            except Exception as e:
                print(f"❌ Backend {i+1} failed: {e}")
        
        if not devices_found:
            print("❌ No USB devices found. Make sure:")
            print("   1. Your scanner is connected")
            print("   2. WinUSB driver is installed via Zadig")
            print("   3. You have admin privileges")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure libusb is properly installed")

if __name__ == "__main__":
    find_scanner()
