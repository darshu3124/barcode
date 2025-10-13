import threading
import time
from typing import Callable

# We reuse the scanner logic from both_test.py by importing its functions
import both_test as scanner


def _run_threads():
    threads = []
    for s in scanner.SCANNERS:
        t = threading.Thread(
            target=scanner.read_scanner,
            args=(s["vendor"], s["product"], s["prefix"]),
            daemon=True,
        )
        t.start()
        threads.append(t)

    while not scanner.stop_flag:
        time.sleep(0.25)


def start_listener(callback: Callable[[str], None]):
    # Configure which scanner output we accept
    scanner.active_scanner = "scan1"

    # Intercept prints from both_test.py to capture barcode lines
    old_print = print

    def custom_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        # Lines look like: "scan1: 123456"; extract after ':'
        if scanner.active_scanner in msg and ":" in msg:
            try:
                barcode_value = msg.split(":", 1)[1].strip()
                if barcode_value:
                    callback(barcode_value)
            except Exception:
                pass
        old_print(*args, **kwargs)

    globals()["print"] = custom_print

    _run_threads()


