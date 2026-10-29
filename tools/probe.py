#!/usr/bin/env python3
# Read-only probe of the QMK raw HID interface: sends info queries, prints replies.
import os, select, sys

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/hidraw6"
fd = os.open(dev, os.O_RDWR)

def query(name, payload):
    os.write(fd, bytes([0x00]) + bytes(payload).ljust(32, b"\x00"))  # report id 0 + 32 bytes
    r, _, _ = select.select([fd], [], [], 1.0)
    if not r:
        print(f"{name}: no reply"); return
    data = os.read(fd, 64)
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    print(f"{name}:\n  hex   {data.hex(' ')}\n  ascii {text}")

query("cmd 0x01 (protocol version)", [0x01])
query("cmd 0x02 (qmk version)", [0x02])
query("cmd 0x03 (OpenRGB device info)", [0x03])
os.close(fd)
