#!/usr/bin/env python3
"""keyglow host: read Hyprland binds and push them to the keyboard as a glow table.

Usage: keyglow.py {show,push,daemon,ping,on,off} [-c CONFIG]
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import select
import socket
import subprocess
import sys
import time
import tomllib

CMD = 0xA5
PING, CLEAR, ADD, SET_BG, SET_ENABLED = range(5)
PACKET = 32
ENTRIES_PER_PACKET = 5

# Hyprland modmask bits -> firmware CSAG bits
HYPR_MODS = {1: 0x02, 4: 0x01, 8: 0x04, 64: 0x08}  # shift, ctrl, alt, super
MOD_NAMES = [(0x08, "SUPER"), (0x01, "CTRL"), (0x04, "ALT"), (0x02, "SHIFT")]

DEFAULT_CONFIG = {
    "device": {"vid": 0x19F5, "pid": 0x3302},
    "colors": {
        "background": "#000000",
        "default": "#00b4ff",
        "dispatcher": {},
        "keys": {},
    },
    "filter": {"exclude_dispatchers": [], "exclude_keys": []},
}

# xkb keysym name (lowercase) -> USB HID keyboard usage. Assumes a US layout.
KEYSYMS = {chr(ord("a") + i): 0x04 + i for i in range(26)}
KEYSYMS |= {str(i): 0x1E + i - 1 for i in range(1, 10)} | {"0": 0x27}
KEYSYMS |= {f"f{i}": 0x3A + i - 1 for i in range(1, 13)} | {f"f{i}": 0x68 + i - 13 for i in range(13, 25)}
KEYSYMS |= {
    "return": 0x28, "escape": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "bracketleft": 0x2F, "bracketright": 0x30, "backslash": 0x31,
    "semicolon": 0x33, "apostrophe": 0x34, "grave": 0x35, "comma": 0x36, "period": 0x37,
    "slash": 0x38, "caps_lock": 0x39, "print": 0x46, "scroll_lock": 0x47, "pause": 0x48,
    "insert": 0x49, "home": 0x4A, "prior": 0x4B, "page_up": 0x4B, "delete": 0x4C, "end": 0x4D,
    "next": 0x4E, "page_down": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "num_lock": 0x53, "kp_divide": 0x54, "kp_multiply": 0x55, "kp_subtract": 0x56,
    "kp_add": 0x57, "kp_enter": 0x58, "menu": 0x65,
}
# Keypad keys have one keysym with NumLock on and another with it off.
for usage, names in {
    0x59: ("kp_1", "kp_end"), 0x5A: ("kp_2", "kp_down"), 0x5B: ("kp_3", "kp_next", "kp_page_down"),
    0x5C: ("kp_4", "kp_left"), 0x5D: ("kp_5", "kp_begin"), 0x5E: ("kp_6", "kp_right"),
    0x5F: ("kp_7", "kp_home"), 0x60: ("kp_8", "kp_up"), 0x61: ("kp_9", "kp_prior", "kp_page_up"),
    0x62: ("kp_0", "kp_insert"), 0x63: ("kp_decimal", "kp_delete"),
}.items():
    KEYSYMS |= dict.fromkeys(names, usage)


def log(*a):
    print("keyglow:", *a, file=sys.stderr, flush=True)


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            for k, v in values.items():
                if isinstance(v, dict):
                    cfg[section].setdefault(k, {}).update(v)
                else:
                    cfg[section][k] = v
    return cfg


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def combo_name(mods, key):
    return "+".join([n for bit, n in MOD_NAMES if mods & bit] + [key.upper()])


# --- Hyprland -------------------------------------------------------------

def hypr_env():
    """Environment for talking to Hyprland, finding the instance if we were started outside it."""
    env = dict(os.environ)
    if "SUDO_UID" in env:  # under sudo, Hyprland's sockets are still in the invoking user's runtime dir
        env["XDG_RUNTIME_DIR"] = f"/run/user/{env['SUDO_UID']}"
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        dirs = glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "hypr", "*/"))
        if dirs:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(max(dirs, key=os.path.getmtime).rstrip("/"))
    return env


def hypr_binds():
    out = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, env=hypr_env())
    if out.returncode:
        raise RuntimeError(f"hyprctl binds failed: {(out.stderr or out.stdout).strip()}")
    return json.loads(out.stdout)


def dispatcher_name(d):
    m = re.fullmatch(r"HL\.Dispatcher\((\w+)\)", d)  # Lua-config Hyprland wraps the name
    return m.group(1) if m else d


def build_table(binds, cfg):
    """Return [(mods, usage, (r,g,b), label)] for every Super bind on a physical key."""
    colors = cfg["colors"]
    keys = {k.upper(): v for k, v in colors["keys"].items()}
    exclude_disp = set(cfg["filter"]["exclude_dispatchers"])
    exclude_keys = [p.upper() for p in cfg["filter"]["exclude_keys"]]
    table, seen, skipped = [], set(), []
    for b in binds:
        if b["mouse"] or b["key"].startswith("mouse") or b["submap"] or not b["modmask"] & 64:
            continue
        mods = sum(bit for hbit, bit in HYPR_MODS.items() if b["modmask"] & hbit)
        usage = KEYSYMS.get(b["key"].lower())
        if usage is None:
            skipped.append(b["key"] or f"code:{b['keycode']}")
            continue
        name = combo_name(mods, b["key"])
        disp = dispatcher_name(b["dispatcher"])
        if disp in exclude_disp or any(fnmatch.fnmatchcase(name, p) for p in exclude_keys):
            continue
        if (mods, usage) in seen:
            continue
        seen.add((mods, usage))
        color = keys.get(name) or colors["dispatcher"].get(disp) or colors["default"]
        table.append((mods, usage, rgb(color), f"{name} -> {disp}"))
    if skipped:
        log("no HID mapping for:", ", ".join(sorted(set(skipped))))
    return table


# --- Keyboard -------------------------------------------------------------

def find_hidraw(vid, pid):
    want = f"0003:{vid:08X}:{pid:08X}"
    for dev in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(f"{dev}/device/uevent") as f:
                if f"HID_ID={want}" not in f.read().upper():
                    continue
            with open(f"{dev}/device/report_descriptor", "rb") as f:
                if f.read(3) == b"\x06\x60\xff":  # usage page 0xFF60: QMK raw HID
                    return "/dev/" + os.path.basename(dev)
        except OSError:
            continue
    return None


class Keyboard:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def send(self, sub, payload=b""):
        pkt = bytes([CMD, sub]) + bytes(payload)
        os.write(self.fd, b"\x00" + pkt.ljust(PACKET, b"\x00"))
        deadline = time.monotonic() + 1.0
        while (left := deadline - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                break
            reply = os.read(self.fd, 64)
            if reply[:1] == bytes([CMD]):  # skip replies meant for VIA/OpenRGB clients
                if reply[1] == 0xFF:
                    raise RuntimeError(f"firmware rejected subcommand {sub:#x}")
                return reply
        raise TimeoutError("no reply from keyboard (is keyglow in the firmware?)")

    def ping(self):
        r = self.send(PING)
        return {"version": r[2], "max_entries": r[3], "entries": r[4]}

    def push(self, table, background):
        info = self.ping()
        if len(table) > info["max_entries"]:
            log(f"{len(table)} binds but firmware holds {info['max_entries']}; truncating")
            table = table[: info["max_entries"]]
        self.send(CLEAR)
        self.send(SET_BG, bytes(background))
        for i in range(0, len(table), ENTRIES_PER_PACKET):
            chunk = table[i:i + ENTRIES_PER_PACKET]
            payload = bytes([len(chunk)]) + b"".join(bytes([m, u, *c]) for m, u, c, _ in chunk)
            self.send(ADD, payload)
        return len(table)


def open_keyboard(cfg):
    path = find_hidraw(cfg["device"]["vid"], cfg["device"]["pid"])
    if not path:
        raise FileNotFoundError("keyboard raw HID interface not found")
    return Keyboard(path)


# --- Commands -------------------------------------------------------------

def cmd_show(cfg):
    for mods, usage, (r, g, b), label in build_table(hypr_binds(), cfg):
        swatch = f"\x1b[48;2;{r};{g};{b}m  \x1b[0m" if sys.stdout.isatty() else ""
        print(f"{swatch} {label:<40} mods={mods:#04x} hid={usage:#04x} #{r:02x}{g:02x}{b:02x}")


def push(cfg, kb=None):
    table = build_table(hypr_binds(), cfg)
    kb = kb or open_keyboard(cfg)
    n = kb.push(table, rgb(cfg["colors"]["background"]))
    log(f"pushed {n} binds to {kb.path}")
    return kb


def hypr_events():
    env = hypr_env()
    path = os.path.join(env.get("XDG_RUNTIME_DIR", ""), "hypr", env.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket2.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(path)
    return s


def cmd_daemon(cfg, interval=5.0):
    kb, events, buf = None, None, b""
    while True:
        try:
            if events is None:
                events = hypr_events()
            if kb is None:
                kb = push(cfg)
            if select.select([events], [], [], interval)[0]:
                data = events.recv(4096)
                if not data:
                    raise ConnectionError("Hyprland event socket closed")
                buf += data
                *lines, buf = buf.split(b"\n")
                if any(l.startswith(b"configreloaded>>") for l in lines):
                    push(cfg, kb)
            elif kb.ping()["entries"] == 0:  # keyboard was reset or replugged on the same node
                push(cfg, kb)
        except (OSError, TimeoutError, RuntimeError) as e:
            log(f"{e}; retrying in {interval:.0f}s")
            for h in (kb, events):
                try:
                    h and h.close()
                except OSError:
                    pass
            kb, events, buf = None, None, b""
            time.sleep(interval)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["show", "push", "daemon", "ping", "on", "off"])
    p.add_argument("-c", "--config", default=os.path.expanduser("~/.config/keyglow/config.toml"))
    args = p.parse_args()
    cfg = load_config(args.config)

    if args.command == "show":
        cmd_show(cfg)
    elif args.command == "push":
        push(cfg).close()
    elif args.command == "daemon":
        cmd_daemon(cfg)
    else:
        try:
            kb = open_keyboard(cfg)
        except PermissionError as e:
            sys.exit(f"keyglow: {e}\n  install the udev rule from nix/keyglow.nix (or run with sudo once)")
        if args.command == "ping":
            print(kb.ping())
        else:
            kb.send(SET_ENABLED, [args.command == "on"])
        kb.close()


if __name__ == "__main__":
    main()
