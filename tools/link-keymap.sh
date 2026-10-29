#!/bin/sh
# Link firmware/halo96_v2 into the QMK tree as keymaps/keyglow. The directory must be real
# (only its files are symlinks) so that ../default resolves inside the QMK tree.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
dest="$root/qmk/keyboards/nuphy/halo96_v2/ansi/keymaps/keyglow"
rm -rf "$dest" && mkdir -p "$dest"
for f in "$root"/firmware/halo96_v2/*; do ln -s "$f" "$dest/"; done
ls -l "$dest"

# Apply our patches to the QMK clone, skipping any already applied.
for p in "$root"/firmware/patches/*.patch; do
    if git -C "$root/qmk" apply --reverse --check "$p" 2>/dev/null; then
        echo "already applied: $(basename "$p")"
    else
        git -C "$root/qmk" apply "$p" && echo "applied: $(basename "$p")"
    fi
done
