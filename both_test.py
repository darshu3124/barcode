import usb.core
import usb.util
import usb.backend.libusb1
import threading
import sys
import time

# ✅ Load backend explicitly
backend = usb.backend.libusb1.get_backend(
    find_library=lambda x: "C:/libusb/libusb-1.0.dll"
)

# ✅ Scanner configurations
SCANNERS = [
    {"vendor": 0x2DD6, "product": 0x2701, "prefix": "scan1"},  # main scanner
    {"vendor": 0xFFFF, "product": 0x0035, "prefix": "scan2"},  # secondary scanner
]

stop_flag = False
active_scanner = None  # which scanner is currently active

# ✅ HID keycode maps
KEYMAP = {
    4: "a", 5: "b", 6: "c", 7: "d", 8: "e", 9: "f", 10: "g", 11: "h",
    12: "i", 13: "j", 14: "k", 15: "l", 16: "m", 17: "n", 18: "o", 19: "p",
    20: "q", 21: "r", 22: "s", 23: "t", 24: "u", 25: "v", 26: "w", 27: "x",
    28: "y", 29: "z",
    30: "1", 31: "2", 32: "3", 33: "4", 34: "5", 35: "6", 36: "7", 37: "8",
    38: "9", 39: "0",
    40: "\n", 44: " ", 45: "-", 46: "=", 47: "[", 48: "]", 49: "\\",
    51: ";", 52: "'", 53: "`", 54: ",", 55: ".", 56: "/",
}

SHIFT_KEYMAP = {
    4: "A", 5: "B", 6: "C", 7: "D", 8: "E", 9: "F", 10: "G", 11: "H",
    12: "I", 13: "J", 14: "K", 15: "L", 16: "M", 17: "N", 18: "O", 19: "P",
    20: "Q", 21: "R", 22: "S", 23: "T", 24: "U", 25: "V", 26: "W", 27: "X",
    28: "Y", 29: "Z",
    30: "!", 31: "@", 32: "#", 33: "$", 34: "%", 35: "^", 36: "&", 37: "*",
    38: "(", 39: ")",
    45: "_", 46: "+", 47: "{", 48: "}", 49: "|",
    51: ":", 52: '"', 53: "~", 54: "<", 55: ">", 56: "?",
}


def decode_hid(data):
    """Decode HID report"""
    if not data or data[2] == 0:
        return None
    keycode = data[2]
    shift = data[0] in (2, 32)
    return SHIFT_KEYMAP.get(keycode) if shift else KEYMAP.get(keycode)


def read_scanner(vendor_id, product_id, prefix):
    """Read data from the USB barcode scanner."""
    global stop_flag, active_scanner
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id, backend=backend)
    if dev is None:
        print(f"{prefix}: Device not found")
        return

    try:
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
    except Exception as e:
        print(f"{prefix}: Could not set configuration ({e})")
        return

    ep = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
        == usb.util.ENDPOINT_IN,
    )
    if ep is None:
        print(f"{prefix}: No IN endpoint found")
        return

    print(f"{prefix}: Ready on endpoint {hex(ep.bEndpointAddress)}")

    barcode = ""
    last_char_time = time.time()

    while not stop_flag:
        try:
            data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout=1000)
            char = decode_hid(data)
            if char:
                if char == "\n":
                    if barcode:
                        if prefix == active_scanner:
                            print(f"{prefix}: {barcode}")
                        barcode = ""
                else:
                    barcode += char
                    last_char_time = time.time()

        except usb.core.USBError as e:
            if e.errno in (110, 10060):  # timeout
                if barcode and (time.time() - last_char_time > 0.5):
                    if prefix == active_scanner:
                        print(f"{prefix}: {barcode}")
                    barcode = ""
                continue
            elif e.errno == 19:  # disconnected
                print(f"{prefix}: Device disconnected")
                break
            else:
                print(f"{prefix}: USB Error {e}")
                break


# ✅ Direct-run mode for testing
def main():
    global stop_flag, active_scanner
    choice = input("Which scanner do you want to use? (scan1/scan2): ").strip().lower()
    if choice not in ("scan1", "scan2"):
        print("Invalid choice. Exiting.")
        return

    active_scanner = choice
    print(f"✅ Only listening to {active_scanner}. Other scanner will be ignored.")
    print("Press 'q' then Enter to quit.")

    threads = []
    for s in SCANNERS:
        t = threading.Thread(target=read_scanner, args=(s["vendor"], s["product"], s["prefix"]), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            key = sys.stdin.readline().strip().lower()
            if key == "q":
                stop_flag = True
                print("Stopping...")
                break
    except KeyboardInterrupt:
        stop_flag = True

    for t in threads:
        t.join()


# ✅ Flask listener mode (used by app.py)
def main_listener(callback):
    """Run scanner in background and send barcodes to Flask callback"""
    global stop_flag, active_scanner
    active_scanner = "scan2"   # ✅ automatically use your working scanner
    print(f"✅ Listening to {active_scanner}")

    threads = []
    for s in SCANNERS:
        t = threading.Thread(
            target=read_scanner,
            args=(s["vendor"], s["product"], s["prefix"]),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # ✅ Intercept print() output to capture barcodes
    old_print = print

    def custom_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args).strip()

        # Always show debug text in console
        old_print(*args, **kwargs)

        # ✅ Only process lines that clearly look like scanner data
        if not msg.startswith(active_scanner + ":"):
            return

        # Extract the barcode value (text after the colon)
        barcode_value = msg.split(":", 1)[1].strip()

        # 🚫 Skip lines that are not valid barcodes
        if (
            not barcode_value
            or "endpoint" in barcode_value.lower()
            or "device" in barcode_value.lower()
            or "error" in barcode_value.lower()
        ):
            return

        # ✅ Forward only proper student IDs to Flask
        if len(barcode_value) >= 3:  # or use .isdigit() if your barcodes are numeric
            callback(barcode_value)

    # Replace print globally
    globals()["print"] = custom_print

    # Keep thread alive
    while not stop_flag:
        time.sleep(0.5)



if __name__ == "__main__":
    main()
