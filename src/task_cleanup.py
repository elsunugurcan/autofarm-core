"""Resolve only a task's devices and verify Facebook closes at its boundary."""
from contextlib import closing
from pathlib import Path
import sqlite3
from . import fleet_controls


def task_serials(command, database):
    if len(command) < 3:
        return []
    script = Path(command[1]).name
    if script == "telegram_pipeline.py":
        return list(dict.fromkeys(s for s in command[6].split(",") if s and s != "ALL")) if len(command) > 6 else []
    if script != "core_engine.py":
        return []
    if command[2] == "warmup":
        return list(dict.fromkeys(s for s in command[5].split(",") if s and s != "ALL")) if len(command) > 5 else []
    if command[2] == "run_queue":
        query = "SELECT DISTINCT serial FROM campaign_queue WHERE status LIKE '%PENDING%'"
        params = ()
        if len(command) > 4:
            query += " AND camp_code=?"
            params = (command[4],)
        with closing(sqlite3.connect(database)) as db:
            return [r[0] for r in db.execute(query, params) if r[0]]
    return []


def close_devices(serials, log):
    for serial in dict.fromkeys(serials):
        try:
            result = fleet_controls.sleep_device(serial)
        except Exception as exc:
            log(f"[GÖREV SONU HATASI] {serial}: {exc}")
            continue
        try:
            pid = fleet_controls.adb("-s", serial, "shell", "pidof com.facebook.katana || true").strip()
            closed = not pid
        except Exception as exc:
            closed = False
            result["errors"].append(str(exc))
        state = "Facebook kapalı: doğrulandı" if closed else "Facebook kapanışı doğrulanamadı"
        log(f"[GÖREV SONU] {serial} | {state} | Ekran uykusu: {'doğrulandı' if result['asleep'] else 'doğrulanamadı'}" +
            (" | " + "; ".join(result["errors"]) if result["errors"] else ""))
