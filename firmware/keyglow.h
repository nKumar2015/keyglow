// keyglow: while GUI (Super) is held, blank the RGB matrix and light only the
// keys that have a bind for the currently held modifier combo. The bind table
// is pushed from the host over raw HID (see PROTOCOL.md).
#pragma once

#include <stdbool.h>
#include <stdint.h>

// First byte of every keyglow raw HID packet. Chosen to stay clear of VIA
// (0x01-0x15, 0xFF) and OpenRGB (0x01-0x0F) command IDs.
#define KEYGLOW_CMD 0xA5

#ifndef KEYGLOW_MAX_ENTRIES
#    define KEYGLOW_MAX_ENTRIES 96
#endif

// Handle a raw HID packet. Returns true (and sends the reply) if it was a
// keyglow packet, false if it should be passed on to VIA/OpenRGB.
bool keyglow_raw_hid(uint8_t *data, uint8_t length);

// Call from rgb_matrix_indicators_advanced_user/_kb.
bool keyglow_indicators(uint8_t led_min, uint8_t led_max);
