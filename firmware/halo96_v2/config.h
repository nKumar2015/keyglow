#pragma once

// NuPhy ships 2 ms of eager debounce, which lets release bounce through as a second press
// (repeated characters). keyboard.json's "debounce": 2 is already defined by the time this
// file is read, hence the #undef.
#undef DEBOUNCE
#define DEBOUNCE 8
