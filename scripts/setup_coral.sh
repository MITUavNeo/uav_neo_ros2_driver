#!/bin/bash
# setup_coral.sh — Install Coral EdgeTPU USB Accelerator dependencies
#
# This script:
#   1. Installs libedgetpu runtime (.deb from depend/)
#   2. Installs tflite_runtime Python wheel (from depend/)
#   3. Installs pycoral Python wheel (from depend/)
#   4. Adds udev rule for non-root USB access
#   5. Verifies the TPU is detected
#
# No reboot required (udev rule takes effect on next plug).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPEND_DIR="$SCRIPT_DIR/../depend"

echo "=== Coral EdgeTPU Setup ==="

# --- 1. Install libedgetpu ---
echo "[1/4] Installing libedgetpu runtime..."
if dpkg -l libedgetpu1-std 2>/dev/null | grep -q "^ii"; then
    echo "  libedgetpu1-std already installed. Skipping."
else
    sudo dpkg -i "$DEPEND_DIR"/libedgetpu1-std_*.deb
fi

# --- 2. Install tflite_runtime ---
echo "[2/4] Installing tflite_runtime..."
if python3 -c "import tflite_runtime" 2>/dev/null; then
    echo "  tflite_runtime already installed. Skipping."
else
    pip3 install --break-system-packages "$DEPEND_DIR"/tflite_runtime-*.whl
fi

# --- 3. Install pycoral ---
echo "[3/4] Installing pycoral..."
if python3 -c "import pycoral" 2>/dev/null; then
    echo "  pycoral already installed. Skipping."
else
    pip3 install --break-system-packages "$DEPEND_DIR"/pycoral-*.whl
fi

# --- 4. Udev rule for non-root access ---
echo "[4/4] Installing udev rule for Coral USB access..."
UDEV_SRC="$SCRIPT_DIR/99-coral-edgetpu.rules"
UDEV_DST="/etc/udev/rules.d/99-coral-edgetpu.rules"

if cmp -s "$UDEV_SRC" "$UDEV_DST" 2>/dev/null; then
    echo "  Coral udev rules: already installed (unchanged)."
else
    sudo cp "$UDEV_SRC" "$UDEV_DST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=usb
    echo "  Udev rule installed. Covers both pre-init (1a6e:089a) and post-init (18d1:9302) IDs."
fi

# --- Verify ---
echo ""
echo "Verifying Coral EdgeTPU..."
if lsusb | grep -qi "google\|1a6e:089a\|18d1:9302"; then
    echo "  Coral USB device detected on bus."
else
    echo "  WARNING: Coral USB device not found. Is it plugged in?"
fi

if python3 -c "from pycoral.utils.edgetpu import list_edge_tpus; tpus = list_edge_tpus(); assert tpus" 2>/dev/null; then
    echo "  pycoral can see the EdgeTPU. OK."
else
    echo "  WARNING: pycoral cannot detect the EdgeTPU. Check USB connection and libedgetpu install."
fi

echo ""
echo "=== Coral EdgeTPU setup complete! ==="
echo "No reboot required."
