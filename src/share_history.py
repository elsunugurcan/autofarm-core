"""Durable, per-target sharing history shared by the UI and worker."""
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
from datetime import datetime
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "share_history.db"
MEDIA = ROOT / "share_history_media"
LABELS = {"VISIBLE": "Yeniden açılışta görsel ve yazı görüldü", "PREPARING": "Hazırlanıyor", "SENDING": "Gönderim deneniyor",
          "UNVERIFIED": "Gönderim denendi; doğrulanamadı", "LINK_CAPTURED": "Bağlantı alındı; yayın teyitsiz",
          "ERROR": "Hata", "SKIPPED": "Atlandı", "INTERRUPTED": "Yarıda kesildi"}


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS shares (
        id INTEGER PRIMARY KEY, created_at TEXT, updated_at TEXT, node_id TEXT,
        serial TEXT, fb_name TEXT, target_name TEXT, target_url TEXT,
        title TEXT, image_name TEXT, image_path TEXT, status TEXT,
        post_url TEXT DEFAULT '', detail TEXT DEFAULT '', process_id INTEGER)""")
    try:
        with db:
            yield db
    finally:
        db.close()


def remember_image(path):
    MEDIA.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    destination = MEDIA / f"{digest}.jpg"
    if not destination.exists():
        shutil.copyfile(path, destination)
    return str(destination)


def start_share(node_id, serial, fb_name, target_name, target_url, title, image_name, image_path):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connect() as db:
        cursor = db.execute("""INSERT INTO shares
            (created_at,updated_at,node_id,serial,fb_name,target_name,target_url,title,image_name,image_path,status,process_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, now, node_id, serial, fb_name, target_name, target_url, title, image_name, image_path, "PREPARING", os.getpid()))
        return cursor.lastrowid


def update_share(row_id, status, detail="", post_url=""):
    if status not in LABELS:
        raise ValueError("Unknown share status")
    with connect() as db:
        db.execute("UPDATE shares SET status=?,detail=?,post_url=?,updated_at=? WHERE id=?",
                   (status, detail, post_url, datetime.now().astimezone().isoformat(timespec="seconds"), row_id))


def interrupt_process(pid):
    with connect() as db:
        db.execute("UPDATE shares SET status='INTERRUPTED',detail='İşçi sonuç kaydetmeden kapandı.' WHERE process_id=? AND status IN ('PREPARING','SENDING')", (pid,))


def list_shares(limit=200):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM shares ORDER BY id DESC LIMIT ?", (limit,))]


def get_share(row_id):
    with connect() as db:
        row = db.execute("SELECT * FROM shares WHERE id=?", (row_id,)).fetchone()
        return dict(row) if row else None
