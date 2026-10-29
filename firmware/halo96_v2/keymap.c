// NuPhy Halo96 V2 (official NuPhy firmware): the VIA keymap plus keyglow.
#include "../via/keymap.c"
#include "keyglow.h"

bool rgb_matrix_indicators_advanced_user(uint8_t led_min, uint8_t led_max) {
    return keyglow_indicators(led_min, led_max);
}

bool via_command_kb(uint8_t *data, uint8_t length) {
    return keyglow_raw_hid(data, length);
}
