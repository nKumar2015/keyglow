VIA_ENABLE = yes
RGB_MATRIX_CUSTOM_USER = yes
override EXTRAFLAGS += -I$(KEYMAP_PATH)/../via
SRC += keyglow.c

# Presses register instantly; a release only counts once the key has stayed up for DEBOUNCE ms.
# Overrides keyboard.json's sym_eager_pk.
DEBOUNCE_TYPE = asym_eager_defer_pk
