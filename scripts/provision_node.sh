#!/bin/bash
echo "=== Redmi 15C Node Provisioning Baslatiliyor ==="
adb wait-for-device
echo "[+] Cihaz baglantisi dogrulandi."
adb shell settings put global window_animation_scale 0.0
adb shell settings put global transition_animation_scale 0.0
adb shell settings put global animator_duration_scale 0.0
adb shell settings put global stay_on_while_plugged_in 7
adb shell settings put system screen_brightness_mode 0
adb shell settings put system screen_brightness 5
adb shell settings put secure location_mode 0
adb shell settings put global wifi_scan_always_enabled 0
adb shell settings put global ble_scan_always_enabled 0
adb shell device_config set_sync_disabled_for_tests persistent
adb shell device_config put activity_manager max_phantom_processes 2147483647
echo "=== Cihaz basariyla hazirlandi! ==="
