#!/bin/bash
# Watches the active gscam log for "Could not get gstreamer sample" and snapshots
# system state on hit. Captures dmesg, USB power/runtime, /dev/video*, gstreamer
# pipeline state. Writes a report next to the offending log.
#
# Usage: ./gscam_crash_capture.sh
# Stops after first hit (the failure mode is one-shot — gscam exits on detection).

set -u

LATEST_DIR=$(readlink -f "$HOME/logs/latest")
echo "[capture] watching $LATEST_DIR"

# Wait for gscam log to appear (teleop start + arducam_launch 5s delay + node init)
deadline=$(($(date +%s) + 60))
GSCAM_LOG=""
while [ "$(date +%s)" -lt "$deadline" ]; do
    GSCAM_LOG=$(ls -t "$LATEST_DIR"/gscam_node_*.log 2>/dev/null | head -1)
    [ -n "$GSCAM_LOG" ] && break
    sleep 1
done
if [ -z "$GSCAM_LOG" ]; then
    echo "[capture] no gscam log appeared within 60s — aborting"
    exit 1
fi
echo "[capture] tailing $GSCAM_LOG"

REPORT="$LATEST_DIR/gscam_crash_report.txt"

# Use tail -F so we follow the file even if gscam reopens
tail -F -n 0 "$GSCAM_LOG" 2>/dev/null | while read -r line; do
    case "$line" in
        *"Could not get gstreamer sample"*|*"GStreamer stream stopped"*)
            T=$(date '+%Y-%m-%d %H:%M:%S')
            echo "[capture] HIT at $T: $line"
            {
                echo "===== gscam crash report — $T ====="
                echo
                echo "Trigger line: $line"
                echo
                echo "===== gscam log (last 50 lines) ====="
                tail -50 "$GSCAM_LOG"
                echo
                echo "===== dmesg (last 100 lines, only USB/v4l) ====="
                sudo dmesg -T | grep -iE "usb|v4l|video|uvc|xhci" | tail -100
                echo
                echo "===== Arducam USB device state ====="
                for d in /sys/bus/usb/devices/*; do
                    if [ -f "$d/idVendor" ] && [ -f "$d/idProduct" ]; then
                        vid=$(cat "$d/idVendor")
                        pid=$(cat "$d/idProduct")
                        if [ "$vid" = "0c45" ] && [ "$pid" = "0578" ]; then
                            echo "Arducam at $d:"
                            for f in product manufacturer power/control power/runtime_status \
                                     power/autosuspend power/autosuspend_delay_ms \
                                     bMaxPower speed bcdDevice; do
                                [ -r "$d/$f" ] && echo "  $f: $(cat $d/$f)"
                            done
                        fi
                    fi
                done
                echo
                echo "===== /dev/video* ====="
                ls -la /dev/video* 2>&1
                echo
                echo "===== v4l2-ctl --list-devices ====="
                v4l2-ctl --list-devices 2>&1 | head -40
                echo
                echo "===== gscam process state ====="
                pgrep -af gscam_node 2>&1 | grep -v grep || echo "(no gscam_node running — already exited)"
                echo
                echo "===== teleop.log tail ====="
                tail -30 "$LATEST_DIR/teleop.log" 2>/dev/null | grep -iE "gscam|arducam|usb|v4l"
                echo
                echo "===== watchdog response (post-crash) ====="
                tail -20 "$LATEST_DIR/watchdog.log" 2>/dev/null
            } > "$REPORT"
            echo "[capture] report written to $REPORT"
            exit 0
            ;;
    esac
done
