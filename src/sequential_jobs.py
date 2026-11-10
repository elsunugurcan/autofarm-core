"""Durable manual-start plans and atomic, balanced phone assignment."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import sqlite3
import uuid
import os
from datetime import datetime

DB = Path(__file__).resolve().parent.parent / "sequential_jobs.db"


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY,kind TEXT,data TEXT,status TEXT,created_at TEXT,cursor INTEGER DEFAULT 0,owner_pid INTEGER DEFAULT 0)")
    if "owner_pid" not in {r[1] for r in db.execute("PRAGMA table_info(plans)")}:
        db.execute("ALTER TABLE plans ADD COLUMN owner_pid INTEGER DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY,plan_id TEXT,identity_key TEXT,
        payload TEXT,status TEXT DEFAULT 'WAITING',serial TEXT,message TEXT DEFAULT '',UNIQUE(plan_id,identity_key))""")
    db.commit()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def new_plan(kind, data, plan_id=None):
    plan_id = plan_id or uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO plans(id,kind,data,status,created_at) VALUES (?,?,?,'PAUSED',?)",
                   (plan_id, kind, json.dumps(data, ensure_ascii=False), datetime.now().astimezone().isoformat(timespec="seconds")))
    return plan_id


def watcher_plan(settings):
    identity = {k: settings.get(k) for k in ("posts", "keywords", "reply_template")}
    key = "watcher-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    new_plan("watcher", settings, key)
    return key


def enqueue(plan_id, key, payload):
    with connect() as db:
        return bool(db.execute("INSERT OR IGNORE INTO jobs(plan_id,identity_key,payload) VALUES (?,?,?)",
                    (plan_id, key, json.dumps(payload, ensure_ascii=False))).rowcount)


def plan(plan_id):
    with connect() as db:
        row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row:
        result = dict(row)
        result["data"] = json.loads(result["data"])
        return result


def jobs(plan_id):
    with connect() as db:
        rows = db.execute("SELECT * FROM jobs WHERE plan_id=? ORDER BY id", (plan_id,)).fetchall()
    return [dict(r, payload=json.loads(r["payload"])) for r in rows]


def set_plan(plan_id, status):
    with connect() as db:
        db.execute("UPDATE plans SET status=? WHERE id=?", (status, plan_id))


def acquire(plan_id):
    from .watcher_history import process_alive
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT owner_pid FROM plans WHERE id=?", (plan_id,)).fetchone()
        if row is None:
            raise ValueError("Sıra bulunamadı.")
        if row["owner_pid"] and row["owner_pid"] != os.getpid() and process_alive(row["owner_pid"]):
            raise ValueError("Bu sıra başka bir işçide çalışıyor; ikinci kez başlatılmadı.")
        db.execute("UPDATE plans SET owner_pid=?,status='RUNNING' WHERE id=?", (os.getpid(), plan_id))


def release(plan_id, status="PAUSED"):
    with connect() as db:
        db.execute("UPDATE plans SET owner_pid=0,status=? WHERE id=? AND owner_pid=?", (status, plan_id, os.getpid()))


def update_data(plan_id, data):
    with connect() as db:
        db.execute("UPDATE plans SET data=? WHERE id=? AND owner_pid=?", (json.dumps(data, ensure_ascii=False), plan_id, os.getpid()))


def recover(plan_id):
    # An interrupted assignment may have sent already; never replay it automatically.
    with connect() as db:
        keys = [r[0] for r in db.execute("SELECT identity_key FROM jobs WHERE plan_id=? AND status IN ('ASSIGNED','SENDING')", (plan_id,))]
        db.execute("UPDATE jobs SET status='UNKNOWN',message='İşçi kesildi; otomatik tekrar yok.' WHERE plan_id=? AND status IN ('ASSIGNED','SENDING')", (plan_id,))
    return keys


def claim(plan_id, online, exclude_ids=()):
    online = list(dict.fromkeys(online))
    if not online:
        return None
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT * FROM jobs WHERE plan_id=? AND status='WAITING' ORDER BY id", (plan_id,)).fetchall()
        row = next((r for r in rows if r["id"] not in exclude_ids), None)
        if row is None:
            return None
        counts = {s: 0 for s in online}
        for item in db.execute("SELECT serial,COUNT(*) n FROM jobs WHERE plan_id=? AND serial IS NOT NULL AND status NOT IN ('WAITING','SKIPPED','ALREADY_RECORDED') GROUP BY serial", (plan_id,)):
            if item["serial"] in counts:
                counts[item["serial"]] = item["n"]
        cursor = db.execute("SELECT cursor FROM plans WHERE id=?", (plan_id,)).fetchone()[0]
        rotated = online[cursor % len(online):] + online[:cursor % len(online)]
        serial = min(rotated, key=lambda s: counts[s])
        db.execute("UPDATE jobs SET status='ASSIGNED',serial=? WHERE id=? AND status='WAITING'", (serial, row["id"]))
        db.execute("UPDATE plans SET cursor=cursor+1 WHERE id=?", (plan_id,))
        return dict(row, serial=serial, status="ASSIGNED", payload=json.loads(row["payload"]))


def finish(job_id, status, message=""):
    with connect() as db:
        if status == "WAITING":
            db.execute("UPDATE jobs SET status=?,message=?,serial=NULL WHERE id=?", (status, message, job_id))
        else:
            db.execute("UPDATE jobs SET status=?,message=? WHERE id=?", (status, message, job_id))


def pending_plans(kind=None):
    if not DB.exists():
        return []
    with connect() as db:
        query = "SELECT p.*,COUNT(j.id) pending FROM plans p JOIN jobs j ON j.plan_id=p.id WHERE j.status IN ('WAITING','ASSIGNED','SENDING','UNKNOWN')"
        params = ()
        if kind:
            query += " AND p.kind=?"
            params = (kind,)
        rows = db.execute(query + " GROUP BY p.id ORDER BY p.created_at", params).fetchall()
    return [dict(r, data=json.loads(r["data"])) for r in rows]
