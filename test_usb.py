import usb.core
import usb.util

def test_usb_devices():
    try:
        devices = list(usb.core.find(find_all=True))
        print(f'Found {len(devices)} USB devices:')
        
        for i, dev in enumerate(devices[:10]):  # Show first 10 devices
            try:
                vendor_id = f'0x{dev.idVendor:04X}'
                product_id = f'0x{dev.idProduct:04X}'
                
                # Try to get manufacturer and product strings
                try:
                    manufacturer = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "N/A"
                except:
                    manufacturer = "N/A"
                    
                try:
                    product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "N/A"
                except:
                    product = "N/A"
                
                print(f'  {i+1}. Vendor: {vendor_id}, Product: {product_id}')
                print(f'     Manufacturer: {manufacturer}')
                print(f'     Product: {product}')
                print()
                
            except Exception as e:
                print(f'  {i+1}. Error reading device info: {e}')
                print()
                
    except Exception as e:
        print(f'Error detecting USB devices: {e}')

if __name__ == "__main__":
    test_usb_devices()
