#!/bin/bash
# setup_networking.sh - Configure eth0 dual-IP and wlan0 isolated AP
#
# This script:
#   1. Installs the NetworkManager dispatcher that blocks FORWARD on wlan0
#      so AP clients can't route through the Pi to the internet
#   2. Removes any prior Wi-Fi client connection on wlan0 (e.g. the original
#      "Duck" connection from a previous build)
#   3. Creates the "uav-neo-ap" NetworkManager connection on wlan0 with
#      SSID uav-neo-0 / WPA2 / 2.4 GHz / channel 6 / 10.42.0.1/24
#   4. Writes /etc/netplan/99-uav-eth0.yaml so eth0 carries both a static
#      192.168.52.200/24 address and a DHCP-assigned address simultaneously
#   5. Runs `netplan apply` to bring the new config up
#
# All steps are idempotent - re-running this script is safe.

set -e

echo "=== UAV Neo Networking Setup ==="

AP_SSID="uav-neo-0"
AP_PSK="uavneo@mit"
AP_CON_NAME="uav-neo-ap"
AP_BAND="bg"
AP_CHANNEL=6
AP_ADDR="10.42.0.1/24"

ETH_STATIC_ADDR="192.168.52.200/24"

DISPATCHER_PATH="/etc/NetworkManager/dispatcher.d/99-uav-ap-isolate"
NETPLAN_ETH_PATH="/etc/netplan/99-uav-eth0.yaml"

CHANGES_MADE=false

# --- 1. AP-isolation dispatcher ----------------------------------------------
echo "[1/4] Installing AP isolation dispatcher at $DISPATCHER_PATH..."
sudo tee "$DISPATCHER_PATH" >/dev/null <<'SCRIPT'
#!/bin/sh
# UAV Neo hotspot isolation - NM's ipv4.method=shared enables IP forwarding
# and sets up NAT, which would let wlan0 AP clients route out through eth0.
# Block FORWARD in/out of wlan0 so clients can reach the Pi's own services
# (Jupyter, dashboard, SSH) but cannot use the Pi as an internet gateway.

iface="$1"
action="$2"

[ "$iface" = "wlan0" ] || exit 0
[ "$CONNECTION_ID" = "uav-neo-ap" ] || exit 0

case "$action" in
    up)
        iptables -D FORWARD -i wlan0 -j REJECT 2>/dev/null
        iptables -D FORWARD -o wlan0 -j REJECT 2>/dev/null
        iptables -I FORWARD -i wlan0 -j REJECT
        iptables -I FORWARD -o wlan0 -j REJECT
        ;;
    down|pre-down)
        iptables -D FORWARD -i wlan0 -j REJECT 2>/dev/null
        iptables -D FORWARD -o wlan0 -j REJECT 2>/dev/null
        ;;
esac
exit 0
SCRIPT
sudo chmod 755 "$DISPATCHER_PATH"
sudo chown root:root "$DISPATCHER_PATH"
echo "  Dispatcher installed."

# --- 2. Delete prior Wi-Fi client connections on wlan0 -----------------------
echo "[2/4] Removing any prior Wi-Fi client connection on wlan0..."
mapfile -t prior_wifi < <(
    nmcli -t -f NAME,TYPE,DEVICE con show |
    awk -F: -v ap="$AP_CON_NAME" '
        $2 == "802-11-wireless" && $1 != ap { print $1 }
    '
)
if [ "${#prior_wifi[@]}" -eq 0 ]; then
    echo "  No prior Wi-Fi client connections found."
else
    for con in "${prior_wifi[@]}"; do
        echo "  Deleting connection '$con'..."
        sudo nmcli connection delete "$con"
        CHANGES_MADE=true
    done
fi

# --- 3. Create or update the AP connection -----------------------------------
echo "[3/4] Configuring AP connection '$AP_CON_NAME'..."
if nmcli -t -f NAME con show | grep -qx "$AP_CON_NAME"; then
    echo "  Connection already exists - reapplying settings."
    sudo nmcli connection modify "$AP_CON_NAME" \
        802-11-wireless.ssid "$AP_SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band "$AP_BAND" \
        802-11-wireless.channel "$AP_CHANNEL" \
        802-11-wireless-security.key-mgmt wpa-psk \
        802-11-wireless-security.psk "$AP_PSK" \
        ipv4.method shared \
        ipv4.addresses "$AP_ADDR" \
        connection.autoconnect yes
else
    echo "  Creating new AP connection..."
    sudo nmcli connection add \
        type wifi \
        ifname wlan0 \
        con-name "$AP_CON_NAME" \
        autoconnect yes \
        ssid "$AP_SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band "$AP_BAND" \
        802-11-wireless.channel "$AP_CHANNEL" \
        802-11-wireless-security.key-mgmt wpa-psk \
        802-11-wireless-security.psk "$AP_PSK" \
        ipv4.method shared \
        ipv4.addresses "$AP_ADDR"
    CHANGES_MADE=true
fi
sudo nmcli connection up "$AP_CON_NAME" >/dev/null 2>&1 || true

# --- 4. eth0 dual-IP via netplan ---------------------------------------------
echo "[4/4] Configuring eth0 dual-IP (static $ETH_STATIC_ADDR + DHCP)..."
TMP_NETPLAN=$(mktemp)
cat >"$TMP_NETPLAN" <<YAML
network:
  version: 2
  ethernets:
    eth0:
      renderer: NetworkManager
      addresses:
      - "$ETH_STATIC_ADDR"
      dhcp4: true
      dhcp6: true
      optional: true
      networkmanager:
        passthrough:
          ipv4.method: "auto"
          ipv4.address1: "$ETH_STATIC_ADDR"
          ipv4.dhcp-timeout: "15"
          ipv4.may-fail: "true"
YAML
if sudo cmp -s "$TMP_NETPLAN" "$NETPLAN_ETH_PATH" 2>/dev/null; then
    echo "  $NETPLAN_ETH_PATH already up to date."
else
    sudo install -m 600 -o root -g root "$TMP_NETPLAN" "$NETPLAN_ETH_PATH"
    echo "  Wrote $NETPLAN_ETH_PATH"
    CHANGES_MADE=true
fi
rm -f "$TMP_NETPLAN"

echo
echo "Applying netplan..."
sudo netplan apply

echo
echo "=== Done ==="
echo
echo "Verify with:"
echo "  ip -br addr show eth0           # static .200 + DHCP"
echo "  iw dev wlan0 info               # ssid uav-neo-0, type AP, ch 6"
echo "  sudo iptables -L FORWARD -n     # two REJECT rules for wlan0"
if [ "$CHANGES_MADE" = "false" ]; then
    echo
    echo "(No configuration changes were necessary - system already matched.)"
fi
