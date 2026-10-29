# keyglow

Hold **Super** and the keyboard goes dark except for the keys that have a Hyprland bind, each in a color
you choose. Add **Shift** and the lit set switches to your Super+Shift binds.

```
host/keyglow.py  --hyprctl binds -j-->  bind table  --raw HID-->  firmware/keyglow.c
                 (re-push on Hyprland reload, rebuild,            (draws it whenever GUI is held,
                  keyboard reset, or replug)                       so there's no host round-trip on keypress)
```

The firmware keeps the table in RAM and draws it by itself. The host only sends a new table when the binds
or the config change.

## Layout

| Path | What |
|------|------|
| `firmware/keyglow.{c,h}` | Board-agnostic QMK module |
| `firmware/PROTOCOL.md` | Raw HID wire protocol |
| `firmware/halo96_v2/` | NuPhy Halo96 V2 keymap: NuPhy's VIA keymap plus keyglow |
| `firmware/patches/` | Patches applied to NuPhy's QMK tree (see [Patches](#patches)) |
| `host/keyglow.py` | Host tool and daemon. Python standard library only |
| `config.example.toml` | Annotated example config |
| `flake.nix` | Package, NixOS module, home-manager module, firmware dev shell |
| `tools/probe.py` | Read-only query of a keyboard's raw HID interface, to identify its firmware |
| `tools/link-keymap.sh` | Links `firmware/halo96_v2/` into `qmk/` and applies the patches (safe to re-run) |
| `tools/flash.sh` | Backs up the current firmware, then flashes over DFU |

## Firmware (NuPhy Halo96 V2)

The base is NuPhy's official [nuphy-src/qmk_firmware](https://github.com/nuphy-src/qmk_firmware)
(`nuphy-keyboards` branch). It is cloned to `qmk/`, which is git-ignored.

### Build

```sh
git clone --depth 1 -b nuphy-keyboards https://github.com/nuphy-src/qmk_firmware.git qmk
git -C qmk submodule update --init --depth 1 lib/chibios lib/chibios-contrib lib/printf
nix develop                    # qmk, dfu-util, python3
tools/link-keymap.sh
cd qmk && make nuphy/halo96_v2/ansi:keyglow && cd ..
```

This produces `qmk/nuphy_halo96_v2_ansi_keyglow.bin`.

### Flash

Raw HID only works over USB, so connect the board with a cable.

```sh
sudo tools/flash.sh "$(which dfu-util)"                    # inside `nix develop`
sudo tools/flash.sh "$(which dfu-util)" backup-<time>.bin  # flash a specific .bin, e.g. to restore a backup
```

1. When the script asks, unplug the board, hold **Esc**, and plug it back in.
   If that doesn't work, hold the button under the Caps Lock keycap while plugging in.
2. The script saves the current firmware to `backup-<time>.bin` (git-ignored), then flashes.

The STM32 bootloader is in ROM, so a bad flash can always be retried.

After flashing, the table is empty until the host pushes one. The daemon does this on its own, or run `keyglow push`.

### Patches

`tools/link-keymap.sh` applies these to `qmk/`:

- `advanced-indicators-user.patch`: NuPhy's `rgb_matrix_indicators_advanced_kb()` never calls the keymap's
  hook. This patch makes it call it, which is where keyglow draws.
- `drop-unused-appdirs.patch`: NuPhy's `requirements.txt` lists `appdirs`. Nothing imports it, and nixpkgs'
  `qmk` doesn't ship it, so QMK's environment check fails without this patch.

keyglow only touches LEDs that sit under a key. The halo ring (LEDs 99–143) keeps doing whatever NuPhy's
effects are doing.

### Debounce

NuPhy ships 2 ms of `sym_eager_pk` debounce, which can turn switch bounce into repeated characters.
The keyglow keymap uses `asym_eager_defer_pk` with 8 ms instead. Presses still register instantly, and a release
only counts once the key has stayed up for 8 ms. Tune `DEBOUNCE` in `firmware/halo96_v2/config.h`; a larger
value suppresses more bounce but slows down fast repeated taps of the same key.

### Other QMK boards

The board needs `RGB_MATRIX_ENABLE = yes` (per-key RGB) and `RAW_ENABLE = yes`.
Copy `firmware/keyglow.{c,h}` into the keymap folder, then:

```make
# rules.mk
SRC += keyglow.c
```

```c
// keymap.c
#include "keyglow.h"

bool rgb_matrix_indicators_advanced_user(uint8_t led_min, uint8_t led_max) {
    return keyglow_indicators(led_min, led_max);
}
```

Hook raw HID in whichever way matches the firmware:

- **VIA firmware:** `bool via_command_kb(uint8_t *data, uint8_t length) { return keyglow_raw_hid(data, length); }`
- **OpenRGB QMK fork:** add `if (keyglow_raw_hid(data, length)) return;` as the first line of `raw_hid_receive()` in `quantum/openrgb.c`
- **Neither:** `void raw_hid_receive(uint8_t *data, uint8_t length) { keyglow_raw_hid(data, length); }`

Make sure the board's `_kb` indicator hook calls the `_user` one (see the patch above). Set the board's USB
ID in the config (`[device]`) and in `hardware.keyglow.devices`.

## NixOS / home-manager

```nix
# flake inputs
keyglow = {
  url = "github:nKumar2015/keyglow";
  inputs.nixpkgs.follows = "nixpkgs";
};

# NixOS modules
inputs.keyglow.nixosModules.default
{ hardware.keyglow.enable = true; }

# home-manager imports
inputs.keyglow.homeManagerModules.default
{
  services.keyglow = {
    enable = true;
    target = "hyprland-session.target";
    highlightColor = "#00b4ff";
    ignore = [ "SUPER+Q" "SUPER+KP_*" ];
    settings = {
      colors.dispatcher.close = "#ff2020";
      filter.exclude_dispatchers = [ "focus" "move" ];
    };
  };
}
```

Replug the keyboard after the first rebuild so the udev rule applies.

### `hardware.keyglow` (NixOS)

| Option | Default | |
|--------|---------|-|
| `enable` | `false` | Adds a udev rule so the logged-in user can open the keyboard's hidraw node (no sudo) |
| `devices` | `[ "19f5:3302" ]` | USB `vendor:product` IDs, lowercase hex |

### `services.keyglow` (home-manager)

| Option | Default | |
|--------|---------|-|
| `enable` | `false` | Runs `keyglow daemon` as a systemd user service |
| `package` | this flake's | |
| `target` | `graphical-session.target` | User target the daemon starts and stops with |
| `highlightColor` | `#00b4ff` | Color of every bound key (becomes `colors.default`) |
| `ignore` | `[]` | Binds to leave dark (becomes `filter.exclude_keys`). See [Combo names](#combo-names) |
| `settings` | `{}` | Anything else for `config.toml`, merged over the two options above |
| `pushOnRebuild` | `true` | Restart the daemon at the end of each home-manager activation |

The module writes `~/.config/keyglow/config.toml`, so don't edit that file by hand.

On every rebuild, home-manager reloads Hyprland's config. After that, `pushOnRebuild` restarts the daemon,
and the daemon pushes the new binds and config on startup. The rebuild uses a restart rather than a second
`push` so the daemon stays the only process writing to the keyboard.

`hyprctl` isn't bundled because it has to match the running Hyprland. The service takes it from the user and system profiles.

## Configuration

`~/.config/keyglow/config.toml`. Every key is optional; see `config.example.toml`.

```toml
[device]
vid = 0x19F5          # keyboard USB IDs
pid = 0x3302

[colors]
background = "#000000"     # unbound keys while Super is held
default = "#00b4ff"        # bound keys, unless a rule below matches

[colors.dispatcher]        # by Hyprland dispatcher (Lua names like exec_cmd/focus, or classic exec/workspace)
exec_cmd = "#00ff80"

[colors.keys]              # by combo
"SUPER+Q" = "#ffffff"

[filter]
exclude_dispatchers = ["focus", "move"]   # e.g. drop the workspace binds
exclude_keys = ["SUPER+KP_*"]             # combos to leave dark
```

A key's color comes from the first rule that matches, in this order: `colors.keys`, then `colors.dispatcher`,
then `colors.default`.

### Combo names

Combos are written the way `keyglow show` prints them: modifiers, then the key, joined by `+`.

- Case, spacing and modifier order don't matter: `"shift + super+m"` is the same as `SUPER+SHIFT+M`.
- `WIN`, `META` and `MOD4` mean `SUPER`, and `CONTROL` means `CTRL`. Any other modifier is an error.
- In `exclude_keys` / `ignore`, the shell globs `*` and `?` work. `"SUPER+KP_*"` matches the whole numpad,
  and `"SUPER+?"` matches any single-character key.

## Host tool

`keyglow` when installed from the flake, `host/keyglow.py` from a checkout.

```sh
keyglow show      # dry run: print the table with color swatches (no keyboard needed)
keyglow push      # send the table once
keyglow daemon    # push now, then whenever Hyprland reloads or the keyboard comes back empty
keyglow ping      # firmware version, capacity, current entry count
keyglow on|off    # enable or disable the effect on the keyboard
keyglow -c FILE … # use another config file
```

## Troubleshooting

- **`Permission denied: '/dev/hidrawN'`:** enable `hardware.keyglow` and replug the keyboard.
  For a one-off, run it with `sudo`; the tool still finds your Hyprland session.
- **Daemon:** `systemctl --user status keyglow` and `journalctl --user -u keyglow`.
- **Nothing lights up:** check `keyglow ping` (`entries` should be non-zero). NuPhy's win-lock blocks the
  Super key, and its green indicator shows when it's on.
- **Wireless:** the table can only be updated over USB. In 2.4G or Bluetooth mode the keyboard keeps
  showing the last table, and the daemon catches up when the cable is back.
- **A bind never lights up:** binds made by keycode (`code:NN`), submap binds, and mouse binds are skipped.
  Keysyms are mapped assuming a US layout.

## Halo controls (NuPhy Halo96 V2)

These are NuPhy's own shortcuts and keyglow doesn't change them. Fn + ←/→/↑/↓ and Fn + `<`/`>` control the
**key** backlight. The halo ring's controls are on the Fn + M layer; see NuPhy's manual.

## History

An earlier version was built on ryodeushii's community fork. It was dropped because its halo effects differ
from stock: no rainbow wave or breathe, and dimmer, coarser brightness levels.
