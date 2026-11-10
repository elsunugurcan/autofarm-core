"""Bounded ADB helpers for fleet viewing and sleeping; no social actions."""
import math
import os
import subprocess

PACKAGES = ("com.facebook.katana", "com.zhiliaoapp.musically", "com.ss.android.ugc.trill")


def adb(*args, timeout=8):
    result = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "ADB komutu başarısız").strip()[:400])
    return result.stdout


def online_devices():
    output = adb("devices", timeout=15)
    return list(dict.fromkeys(parts[0] for line in output.splitlines()[1:]
                             if len(parts := line.split()) >= 2 and parts[1] == "device"))


def sleep_device(serial):
    errors = []
    for package in PACKAGES:
        try:
            adb("-s", serial, "shell", "am", "force-stop", package)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
    for key in (3, 223):
        try:
            adb("-s", serial, "shell", "input", "keyevent", str(key))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
    try:
        state = adb("-s", serial, "shell", "dumpsys", "power")
        asleep = any(token in state for token in ("mWakefulness=Asleep", "mWakefulness=Dozing", "mInteractive=false", "Display Power: state=OFF"))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
        asleep = False
    return {"asleep": asleep, "errors": errors}


def stop_process_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, timeout=8)
        if result.returncode and proc.poll() is None:
            raise RuntimeError(result.stderr.strip() or "Görev süreç ağacı durdurulamadı.")
    else:
        proc.terminate()
    proc.wait(timeout=5)


def mirror_layout(count, screen_width, screen_height):
    if count < 1:
        return []
    usable_height = max(240, screen_height - 80)
    usable_width = max(320, screen_width - 20)
    best = None
    for columns in range(1, min(count, 12) + 1):
        rows = math.ceil(count / columns)
        cell_width, cell_height = usable_width // columns, usable_height // rows
        height = min(cell_height - 36, int((cell_width - 12) / 0.45))
        if best is None or height > best[0]:
            best = (height, columns, cell_width, cell_height)
    height, columns, cell_width, cell_height = best
    height = max(80, height)
    width = max(40, int(height * 0.45))
    return [(10 + (i % columns) * cell_width, 30 + (i // columns) * cell_height, width, height) for i in range(count)]
