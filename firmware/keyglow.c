#include <string.h>
#include QMK_KEYBOARD_H
#include "raw_hid.h"
#include "keyglow.h"

#define KG_VERSION 1
#define KG_HEADER 3     // cmd, subcommand, count/arg
#define KG_ENTRY_SIZE 5 // mods, keycode, r, g, b
#define KG_NONE 0xFF // LED isn't under a key (e.g. NuPhy's halo ring): leave it alone
#define KG_BG 0xFE   // key with no bind for the held mods: background color

#ifndef RGB_MATRIX_LED_COUNT
#    define RGB_MATRIX_LED_COUNT DRIVER_LED_TOTAL // older QMK
#endif

enum {
    KG_PING        = 0x00,
    KG_CLEAR       = 0x01,
    KG_ADD         = 0x02,
    KG_SET_BG      = 0x03,
    KG_SET_ENABLED = 0x04,
};

typedef struct {
    uint8_t mods; // CSAG bits: ctrl 0x01, shift 0x02, alt 0x04, gui 0x08
    uint8_t kc;   // basic (HID usage) keycode
    uint8_t r, g, b;
} kg_entry_t;

static kg_entry_t entries[KEYGLOW_MAX_ENTRIES];
static uint8_t    n_entries;
static uint8_t    bg[3];
static bool       enabled = true;

// Per-LED entry index for the current mods/layers, rebuilt only when they change.
static uint8_t      led_entry[RGB_MATRIX_LED_COUNT];
static uint8_t      cached_mods  = KG_NONE;
static layer_state_t cached_layers;
static bool         dirty = true;

// Left and right modifiers folded together into CSAG bits.
static uint8_t current_mods(void) {
    uint8_t m = get_mods() | get_oneshot_mods();
    return (m | (m >> 4)) & 0x0F;
}

// Tap keycode of a key, so mod-taps and layer-taps still match their letter.
static uint8_t basic_keycode(uint16_t kc) {
    if (IS_QK_BASIC(kc)) return kc;
    if (IS_QK_MODS(kc)) return QK_MODS_GET_BASIC_KEYCODE(kc);
    if (IS_QK_MOD_TAP(kc)) return QK_MOD_TAP_GET_TAP_KEYCODE(kc);
    if (IS_QK_LAYER_TAP(kc)) return QK_LAYER_TAP_GET_TAP_KEYCODE(kc);
    return 0;
}

static void rebuild(uint8_t mods) {
    memset(led_entry, KG_NONE, sizeof(led_entry));
    for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
        for (uint8_t col = 0; col < MATRIX_COLS; col++) {
            uint8_t led = g_led_config.matrix_co[row][col];
            if (led == NO_LED || led >= RGB_MATRIX_LED_COUNT) continue;
            keypos_t pos = {.row = row, .col = col};
            uint8_t  kc  = basic_keycode(keymap_key_to_keycode(layer_switch_get_layer(pos), pos));
            led_entry[led] = KG_BG;
            if (!kc) continue;
            for (uint8_t i = 0; i < n_entries; i++) {
                if (entries[i].mods == mods && entries[i].kc == kc) {
                    led_entry[led] = i;
                    break;
                }
            }
        }
    }
    cached_mods   = mods;
    cached_layers = layer_state | default_layer_state;
    dirty         = false;
}

bool keyglow_indicators(uint8_t led_min, uint8_t led_max) {
    if (!enabled || n_entries == 0) return false;
    uint8_t mods = current_mods();
    if (!(mods & MOD_BIT(KC_LGUI))) return false;

    if (dirty || mods != cached_mods || (layer_state | default_layer_state) != cached_layers) rebuild(mods);

    for (uint8_t i = led_min; i < led_max; i++) {
        uint8_t e = led_entry[i];
        if (e == KG_NONE) {
            continue;
        } else if (e == KG_BG) {
            rgb_matrix_set_color(i, bg[0], bg[1], bg[2]);
        } else {
            rgb_matrix_set_color(i, entries[e].r, entries[e].g, entries[e].b);
        }
    }
    return false;
}

bool keyglow_raw_hid(uint8_t *data, uint8_t length) {
    if (length < KG_HEADER + 3 || data[0] != KEYGLOW_CMD) return false;

    switch (data[1]) {
        case KG_PING:
            data[2] = KG_VERSION;
            data[3] = KEYGLOW_MAX_ENTRIES;
            data[4] = n_entries;
            break;
        case KG_CLEAR:
            n_entries = 0;
            break;
        case KG_ADD:
            for (uint8_t i = 0; i < data[2]; i++) {
                uint8_t off = KG_HEADER + i * KG_ENTRY_SIZE;
                if (off + KG_ENTRY_SIZE > length || n_entries >= KEYGLOW_MAX_ENTRIES) break;
                entries[n_entries++] = (kg_entry_t){data[off], data[off + 1], data[off + 2], data[off + 3], data[off + 4]};
            }
            data[2] = n_entries;
            break;
        case KG_SET_BG:
            memcpy(bg, &data[2], 3);
            break;
        case KG_SET_ENABLED:
            enabled = data[2];
            break;
        default:
            data[1] = KG_NONE;
            break;
    }
    dirty = true;
    raw_hid_send(data, length);
    return true;
}
