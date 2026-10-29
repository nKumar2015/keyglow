# keyglow

Hold **Super** and the keyboard goes dark except for the keys that have a Hyprland bind, each in a color
set by what the bind does. Hold **Super+Shift** and the lit set switches to your Super+Shift binds.

```
host/keyglow.py  --hyprctl binds -j-->  bind table  --raw HID-->  firmware/keyglow.c
                 (re-push on configreloaded,                      (draws it whenever GUI is held,
                  keyboard reset, or replug)                       so there's no host round-trip on keypress)
```

## Layout

| Path | What |
|------|------|
| `firmware/` | Board-agnostic QMK module (`keyglow.c/.h`) and the wire protocol (`PROTOCOL.md`) |
| `host/keyglow.py` | Reads binds, pushes them; `show`, `push`, `daemon`, `ping`, `on`, `off`. Uses only the Python standard library |
| `config.example.toml` | Colors by dispatcher and per combo. Copy it to `~/.config/keyglow/config.toml` |
| `flake.nix` | Package, NixOS module (udev rule), home-manager module (daemon + config), dev shell |
| `tools/probe.py` | Read-only query to identify the board's firmware (`sudo python3 -I tools/probe.py`) |

## Firmware integration

Requires `RGB_MATRIX_ENABLE = yes` (per-key RGB) and `RAW_ENABLE = yes`. Copy `firmware/keyglow.{c,h}`
into your keymap folder, then:

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

Then hook raw HID in whichever way matches the firmware:

- **VIA firmware:** add `bool via_command_kb(uint8_t *data, uint8_t length) { return keyglow_raw_hid(data, length); }`
- **OpenRGB QMK fork:** in `raw_hid_receive()` (`quantum/openrgb.c`), add `if (keyglow_raw_hid(data, length)) return;` as the first line
- **Neither:** define `void raw_hid_receive(uint8_t *data, uint8_t length) { keyglow_raw_hid(data, length); }`

## NixOS / home-manager

```nix
# flake inputs
keyglow = {
  url = "github:nKumar2015/keyglow";
  inputs.nixpkgs.follows = "nixpkgs";
};

# NixOS modules: lets the logged-in user open the keyboard's hidraw node
inputs.keyglow.nixosModules.default
{ hardware.keyglow.enable = true; }   # devices = [ "19f5:3302" ] by default

# home-manager imports: the daemon, started with the Hyprland session
inputs.keyglow.homeManagerModules.default
{
  services.keyglow = {
    enable = true;
    target = "hyprland-session.target";
    highlightColor = "#00b4ff";                 # every lit key
    ignore = [ "SUPER+Q" "SUPER+KP_*" ];        # binds to leave dark; any mod order, globs ok
    settings = {                                # anything else for ~/.config/keyglow/config.toml
      colors.dispatcher.close = "#ff2020";      # per-dispatcher colors beat highlightColor
      filter.exclude_dispatchers = [ "focus" "move" ];
    };
  };
}
```

On every home-manager activation (each rebuild), the daemon is restarted after Hyprland has reloaded,
so the keyboard gets the new binds and `config.toml`. Turn this off with `pushOnRebuild = false`.

`hyprctl` isn't bundled because it has to match the running Hyprland. The service takes it from the user and system profiles.

## Host

```sh
host/keyglow.py show            # dry run: print the table with color swatches
host/keyglow.py push            # send once
host/keyglow.py daemon          # keep in sync (what the systemd service runs)
```

## Status

- [x] Host: bind parsing, keysym→HID mapping (US layout), push protocol, daemon. Tested against live `hyprctl` output
- [x] Board: NuPhy Halo96 V2 (STM32F072, `stm32-dfu`). Base firmware is NuPhy's official
      [nuphy-src/qmk_firmware](https://github.com/nuphy-src/qmk_firmware) (`nuphy-keyboards` branch), cloned to `qmk/`
- [x] Keymap `firmware/halo96_v2/` = NuPhy's VIA keymap + keyglow; `tools/link-keymap.sh` links it in as `keymaps/keyglow`
- [x] Build: `nix develop`, then `tools/link-keymap.sh && make -C qmk nuphy/halo96_v2/ansi:keyglow`
- [x] Flash: `sudo tools/flash.sh "$(which dfu-util)"` inside `nix develop` (backs up first; wired only)
- [ ] Enable the flake's modules in the NixOS config

Patches to NuPhy's tree live in `firmware/patches/` and are applied by `tools/link-keymap.sh`.
`advanced-indicators-user.patch`: NuPhy's `rgb_matrix_indicators_advanced_kb()` never calls the keymap's hook; this makes it.
`drop-unused-appdirs.patch`: NuPhy's `requirements.txt` lists `appdirs`, which nothing imports and nixpkgs' `qmk` doesn't ship.

An earlier version was built on ryodeushii's community fork. It was dropped because its halo
effects differ from stock: no rainbow wave or breathe, and dimmer, coarser brightness levels.

Known limits: binds made by keycode (`code:NN`) and submap binds are skipped. Keys missing from the
board's keymap simply stay dark.
