# keyglow raw HID protocol (v1)

Packets are 32 bytes on the QMK raw HID interface (usage page `0xFF60`).
The firmware echoes every packet back with reply fields filled in.

| byte 0 | byte 1 (sub) | payload                                   | reply                                   |
|--------|--------------|-------------------------------------------|-----------------------------------------|
| `0xA5` | `0x00` ping  | –                                         | `[2]` version, `[3]` max entries, `[4]` entry count |
| `0xA5` | `0x01` clear | –                                         | –                                       |
| `0xA5` | `0x02` add   | `[2]` count (≤5), then count × `mods kc r g b` from `[3]` | `[2]` entry count after adding |
| `0xA5` | `0x03` bg    | `[2..4]` r g b for unbound keys           | –                                       |
| `0xA5` | `0x04` enable| `[2]` 0/1                                 | –                                       |

Unknown subcommands reply with `[1] = 0xFF`.

- `mods` uses CSAG bits with left/right folded together: ctrl `0x01`, shift `0x02`, alt `0x04`, gui `0x08`.
  An entry lights only when the held mods match it exactly, so `SUPER+Q` and `SUPER+SHIFT+Q` are separate entries.
- `kc` is a QMK basic keycode, which is the same as the USB HID keyboard usage (`KC_A` = `0x04`).
- The table lives in RAM. It's empty after power-up, and the host daemon pushes it again when a ping shows 0 entries.
