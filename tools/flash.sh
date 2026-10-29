#!/bin/sh
# Back up the current firmware, then flash keyglow (or another .bin, e.g. a backup).
# Run as root with the path to dfu-util:
#   nix-shell -p dfu-util --run 'sudo tools/flash.sh "$(which dfu-util)" [firmware.bin]'
set -e
DFU=${1:-dfu-util}
root=$(cd "$(dirname "$0")/.." && pwd)
bin=$(realpath "${2:-$root/qmk/nuphy_halo96_v2_ansi_keyglow.bin}")
backup="$root/backup-$(date +%Y%m%d-%H%M%S).bin"
[ -f "$bin" ] || { echo "missing $bin, build first"; exit 1; }

has_usb() { grep -qsx "$1" /sys/bus/usb/devices/*/idVendor && for d in /sys/bus/usb/devices/*; do
    [ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" = "$1:$2" ] && return 0; done; return 1; }

echo "Unplug the keyboard, hold Esc, plug it back in (or hold the button under Caps Lock)."
i=0; until has_usb 0483 df11; do i=$((i+1)); [ $i -gt 120 ] && { echo "no DFU device after 60s"; exit 1; }; sleep 0.5; done
echo "STM32 DFU bootloader found. You can let go of Esc."

echo "== Backing up current firmware to $backup"
if "$DFU" -a 0 -d 0483:df11 -s 0x08000000:131072 -U "$backup"; then
    chown "${SUDO_UID:-0}:${SUDO_GID:-0}" "$backup"
else
    echo "Backup failed (flash may be read-protected)."; rm -f "$backup"
    printf "Flash anyway? [y/N] "; read -r a; [ "$a" = y ] || exit 1
fi

echo "== Flashing $bin"
"$DFU" -a 0 -d 0483:df11 -s 0x08000000:leave -D "$bin"

i=0; while has_usb 0483 df11; do i=$((i+1)); [ $i -gt 30 ] && { echo "still in DFU mode, replug the keyboard"; exit 1; }; sleep 0.5; done
echo "== Done: keyboard left DFU mode"
