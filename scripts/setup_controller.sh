#!/bin/bash
# Controller setup for UAV Neo.
#
# The kit's ESM-9110 gamepad spoofs the Nintendo Switch Pro VID:PID (057e:2009).
# On Pi 5 / kernel 6.x the hid_nintendo driver claims that spoof at boot and
# presents a 6-axis/14-button Switch profile (no js0, wrong mapping) instead of
# the standard XInput layout config/xbox_mapping.yaml expects. Blacklisting
# hid_nintendo lets the pad fall back to xpad (XInput) automatically on every
# boot. See scripts/modprobe.d/blacklist-hid-nintendo.conf for the full rationale.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/modprobe.d/blacklist-hid-nintendo.conf"
DST="/etc/modprobe.d/blacklist-hid-nintendo.conf"

changed=0
if ! cmp -s "$SRC" "$DST" 2>/dev/null; then
    sudo install -m 0644 "$SRC" "$DST"
    echo "Installed $DST"
    changed=1
else
    echo "$DST already up to date"
fi

# Unload hid_nintendo now if it is loaded and idle, so the fix applies without a
# reboot when possible. If the module is in use it stays blacklisted for next boot.
if lsmod | grep -q '^hid_nintendo'; then
    if sudo modprobe -r hid_nintendo 2>/dev/null; then
        echo "Unloaded hid_nintendo"
    else
        echo "hid_nintendo busy; blacklist takes effect on next boot"
    fi
fi

# Regenerate the initramfs so the blacklist also applies to early-boot module
# loading (the pad can be enumerated before the root filesystem's modprobe.d
# is consulted otherwise).
if [ "$changed" -eq 1 ]; then
    sudo update-initramfs -u
    echo "initramfs regenerated."
fi

echo
echo "Done. Replug the controller (or reboot) and confirm XInput mode:"
echo "    lsusb | grep 2f24:00b7        # 'ESM GAME FOR WINDOWS'"
echo "    ls /dev/input/js0             # should exist"
echo "    ros2 topic echo /joy --once   # 11 buttons / 8 axes"
