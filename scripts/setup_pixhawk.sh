#!/bin/bash
# setup_pixhawk.sh - Configure Pi 5 UART and install MAVROS for Pixhawk communication
#
# This script:
#   1. Removes the serial console from kernel command line
#   2. Disables the serial login service
#   3. Disables the kernel SysRq handler
#   4. Disables Bluetooth on the PL011 UART
#   5. Adds user to dialout group for serial access
#   6. Installs MAVROS and GeographicLib datasets
#
# WARNING: A reboot is required after running this script before connecting
# the Pixhawk. The script will prompt you to reboot at the end.
#
# After reboot, configure Pixhawk parameters via QGroundControl:
#   MAV_1_CONFIG  = TELEM2
#   SER_TEL2_BAUD = 921600
#   MAV_1_RATE    = 0 (auto)
#   MAV_1_MODE    = Onboard
#
# Wiring (TELEM2 -> Pi GPIO):
#   TELEM2 TX  -> GPIO 15 (RXD)
#   TELEM2 RX  -> GPIO 14 (TXD)
#   TELEM2 GND -> GND
#   Do NOT connect 5V.

set -e

echo "=== Pixhawk / MAVROS Setup ==="

CHANGES_MADE=false

# --- 1. Remove serial console from kernel command line ---
echo "[1/6] Removing serial console from kernel cmdline..."
CMDLINE="/boot/firmware/cmdline.txt"
if grep -q "console=serial0" "$CMDLINE"; then
    sudo sed -i 's/ console=serial0,[0-9]*//' "$CMDLINE"
    echo "  Removed console=serial0 from $CMDLINE"
    CHANGES_MADE=true
else
    echo "  Already removed (no console=serial0 found)"
fi

# --- 2. Disable serial login service ---
echo "[2/6] Disabling serial-getty on ttyAMA0..."
if systemctl is-enabled serial-getty@ttyAMA0.service &>/dev/null; then
    sudo systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true
    sudo systemctl disable serial-getty@ttyAMA0.service
    echo "  Disabled serial-getty@ttyAMA0"
    CHANGES_MADE=true
else
    echo "  Already disabled"
fi

# --- 3. Disable SysRq ---
echo "[3/6] Disabling kernel SysRq handler..."
SYSRQ_CONF="/etc/sysctl.d/99-disable-sysrq.conf"
if [ ! -f "$SYSRQ_CONF" ] || ! grep -q "kernel.sysrq = 0" "$SYSRQ_CONF"; then
    echo "kernel.sysrq = 0" | sudo tee "$SYSRQ_CONF" > /dev/null
    sudo sysctl -p "$SYSRQ_CONF"
    echo "  SysRq disabled"
    CHANGES_MADE=true
else
    echo "  Already disabled"
fi

# --- 4. Disable Bluetooth on UART ---
echo "[4/6] Disabling Bluetooth on PL011 UART..."
CONFIG="/boot/firmware/config.txt"
if ! grep -q "dtoverlay=disable-bt" "$CONFIG"; then
    echo -e "\n# Free PL011 UART for Pixhawk MAVLink\ndtoverlay=disable-bt" | sudo tee -a "$CONFIG" > /dev/null
    echo "  Added disable-bt overlay to $CONFIG"
    CHANGES_MADE=true
else
    echo "  Already configured"
fi

if systemctl is-enabled bluetooth.service &>/dev/null; then
    sudo systemctl disable bluetooth.service
    echo "  Disabled bluetooth.service"
else
    echo "  bluetooth.service already disabled"
fi

# --- 4b. Pin UART0 to GPIO 14/15 (Pi 5) ---
# On Pi 5 the GPIO-header UART is provided by RP1 and is NOT guaranteed by
# enable_uart=1 alone. A firmware/DTB update can leave serial0 (rp1) disabled,
# dropping /dev/ttyAMA0 entirely and silently breaking the MAVLink link (MAVROS
# then loops on serial:open "No such file or directory"). The uart0-pi5 overlay
# pins UART0 to GPIOs 14/15 so /dev/ttyAMA0 is always present for the Pixhawk.
echo "[4b/6] Pinning UART0 to GPIO 14/15 (uart0-pi5)..."
if ! grep -q "dtoverlay=uart0-pi5" "$CONFIG"; then
    echo -e "\n# Pin UART0 to GPIO 14/15 for Pixhawk (Pi 5; survives firmware updates)\ndtoverlay=uart0-pi5" | sudo tee -a "$CONFIG" > /dev/null
    echo "  Added uart0-pi5 overlay to $CONFIG"
    CHANGES_MADE=true
else
    echo "  Already configured"
fi

# --- 5. Serial port permissions ---
echo "[5/6] Adding $USER to dialout group..."
if id -nG "$USER" | grep -qw dialout; then
    echo "  Already in dialout group"
else
    sudo usermod -aG dialout "$USER"
    echo "  Added $USER to dialout group"
fi

# --- 6. Install MAVROS ---
echo "[6/6] Installing MAVROS..."
source /opt/ros/jazzy/setup.bash
sudo apt install -y ros-jazzy-mavros ros-jazzy-mavros-extras ros-jazzy-mavros-msgs ros-jazzy-joy ros-jazzy-topic-tools

echo "  Installing GeographicLib datasets (this may take a minute)..."
sudo /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh

echo ""
echo "=== Pixhawk / MAVROS setup complete! ==="

if [ "$CHANGES_MADE" = true ]; then
    echo ""
    echo "*** REBOOT REQUIRED ***"
    echo "UART/Bluetooth changes were made that require a reboot."
    echo "Run 'sudo reboot' now. After reboot:"
    echo "  1. Connect Pixhawk TELEM2 to Pi GPIO (TX->RXD, RX->TXD, GND->GND)"
    echo "  2. Configure Pixhawk parameters via QGroundControl (see script header)"
    echo "  3. Verify: ros2 launch mavros px4.launch fcu_url:=/dev/ttyAMA0:921600"
else
    echo "All UART/Bluetooth settings already configured. No reboot needed."
fi
