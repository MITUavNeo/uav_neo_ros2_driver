#!/bin/bash
# reset_networking.sh - Revert the UAV Neo networking config to stock.
#
# Undoes everything setup_networking.sh creates, returning the Pi to a clean
# state suitable for imaging/cloning:
#   1. Deletes the "uav-neo-ap" AP connection. On this build NetworkManager
#      stores connections in netplan (/etc/netplan/90-NM-<uuid>.yaml), so this
#      is what removes the SSID and the plaintext WPA2 PSK from the image.
#   2. Deletes the "netplan-eth0" connection and /etc/netplan/99-uav-eth0.yaml,
#      dropping the static 192.168.52.200 and this board's MAC lock. eth0
#      returns to plain DHCP (NetworkManager's default wired behavior).
#   3. Removes the AP-isolation dispatcher.
#   4. Flushes the wlan0 FORWARD REJECT rules.
#   5. Runs `netplan apply`.
#
# All steps are idempotent and touch only what setup_networking.sh added; an
# already-stock system reports no changes. Re-provision with:
#   drone setup networking   (or scripts/setup_networking.sh)
#
# WARNING: step 5 tears down and rebuilds eth0. Over an eth0 link (SSH / VS
# Code) this drops the session. Run from a local console (tty) or over the
# wlan0 AP, or accept the drop and reconnect via DHCP.

set -u

AP_CON_NAME="uav-neo-ap"
ETH_CON_NAME="netplan-eth0"
NETPLAN_ETH_PATH="/etc/netplan/99-uav-eth0.yaml"
DISPATCHER_PATH="/etc/NetworkManager/dispatcher.d/99-uav-ap-isolate"

ASSUME_YES=false
for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=true ;;
        -h|--help)
            echo "usage: reset_networking.sh [--yes]"
            echo "  Revert UAV Neo networking to stock (removes the AP + PSK, the"
            echo "  eth0 static IP, and the AP-isolation rules). Idempotent."
            echo "  -y, --yes   skip the connectivity-loss confirmation prompt"
            exit 0
            ;;
        *)
            echo "reset_networking.sh: unknown argument '$arg'" >&2
            echo "  try: reset_networking.sh --help" >&2
            exit 2
            ;;
    esac
done

echo "=== UAV Neo Networking Reset ==="
echo
echo "Reverts networking to stock. This will drop an eth0-based session when"
echo "netplan is reapplied at the end."
if [ "$ASSUME_YES" != true ]; then
    read -rp "Continue? [y/N] " ans
    case "$ans" in
        [Yy]*) ;;
        *) echo "Aborted - nothing changed."; exit 0 ;;
    esac
fi

CHANGES_MADE=false

# --- 1. Delete the AP connection (removes SSID + PSK) -------------------------
echo "[1/5] Removing AP connection '$AP_CON_NAME'..."
if nmcli -t -f NAME con show | grep -qx "$AP_CON_NAME"; then
    sudo nmcli connection delete "$AP_CON_NAME"
    echo "  Deleted '$AP_CON_NAME'."
    CHANGES_MADE=true
else
    echo "  Not present."
fi

# --- 2. Revert eth0 to stock DHCP --------------------------------------------
echo "[2/5] Reverting eth0 to stock DHCP..."
if nmcli -t -f NAME con show | grep -qx "$ETH_CON_NAME"; then
    echo "  Deleting connection '$ETH_CON_NAME' (static IP + MAC lock)..."
    sudo nmcli connection delete "$ETH_CON_NAME"
    CHANGES_MADE=true
else
    echo "  Connection '$ETH_CON_NAME' not present."
fi
if sudo test -e "$NETPLAN_ETH_PATH"; then
    sudo rm -f "$NETPLAN_ETH_PATH"
    echo "  Removed $NETPLAN_ETH_PATH"
    CHANGES_MADE=true
else
    echo "  $NETPLAN_ETH_PATH already absent."
fi

# --- 3. Remove AP-isolation dispatcher ---------------------------------------
echo "[3/5] Removing AP isolation dispatcher..."
if sudo test -e "$DISPATCHER_PATH"; then
    sudo rm -f "$DISPATCHER_PATH"
    echo "  Removed $DISPATCHER_PATH"
    CHANGES_MADE=true
else
    echo "  Dispatcher already absent."
fi

# --- 4. Flush the wlan0 FORWARD REJECT rules ---------------------------------
# The dispatcher removes these on AP-down, but flush any that outlived it so a
# reset from a running AP leaves no stray rules behind.
echo "[4/5] Flushing wlan0 FORWARD REJECT rules..."
rules_removed=false
while sudo iptables -C FORWARD -i wlan0 -j REJECT 2>/dev/null; do
    sudo iptables -D FORWARD -i wlan0 -j REJECT
    rules_removed=true
done
while sudo iptables -C FORWARD -o wlan0 -j REJECT 2>/dev/null; do
    sudo iptables -D FORWARD -o wlan0 -j REJECT
    rules_removed=true
done
if [ "$rules_removed" = true ]; then
    echo "  Rules flushed."
    CHANGES_MADE=true
else
    echo "  No wlan0 REJECT rules present."
fi

# --- 5. Apply ----------------------------------------------------------------
echo "[5/5] Applying netplan..."
sudo netplan apply

echo
echo "=== Done ==="
echo
echo "Verify with:"
echo "  nmcli -t -f NAME,TYPE,DEVICE con show   # no uav-neo-ap; eth0 stock"
echo "  ip -br addr show eth0                    # DHCP only, no 192.168.52.200"
echo "  ls /etc/netplan/                         # no 99-uav-eth0.yaml"
if [ "$CHANGES_MADE" = false ]; then
    echo
    echo "(Nothing to reset - networking was already at stock.)"
fi
