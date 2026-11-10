"""Local monitoring history. Findings are screen text, never confirmed replies."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import os
import sqlite3
import uuid
import re
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "watcher_history.db"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def connection():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started_at TEXT, updated_at TEXT, ended_at TEXT DEFAULT '',
          status TEXT, message TEXT, settings TEXT, process_id INTEGER DEFAULT 0,
          stop_requested INTEGER DEFAULT 0, next_check TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS scans (
          id INTEGER PRIMARY KEY, run_id TEXT, started_at TEXT, finished_at TEXT DEFAULT '',
          node_id TEXT, serial TEXT, account TEXT, target_url TEXT, status TEXT,
          message TEXT DEFAULT '', new_matches INTEGER DEFAULT 0, visible_count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS findings (
          id INTEGER PRIMARY KEY, signature TEXT UNIQUE, first_seen TEXT, last_seen TEXT,
          run_id TEXT, scan_id INTEGER, node_id TEXT, serial TEXT, account TEXT,
          target_url TEXT, screen_text TEXT, keyword TEXT, draft TEXT,
          review_state TEXT DEFAULT 'NEW', seen_count INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS finding_comments (
          finding_id INTEGER PRIMARY KEY, comment_key TEXT, comment_url TEXT, author TEXT DEFAULT '');
        CREATE INDEX IF NOT EXISTS finding_comment_key ON finding_comments(comment_key);
        CREATE TABLE IF NOT EXISTS comment_replies (
          comment_key TEXT PRIMARY KEY, comment_url TEXT, target_url TEXT, text_fingerprint TEXT,
          replied_at TEXT, account TEXT, reply_url TEXT, active INTEGER DEFAULT 1,
          confirmation_source TEXT DEFAULT 'MANUAL');
        CREATE TABLE IF NOT EXISTS reply_audit (
          id INTEGER PRIMARY KEY, comment_key TEXT, changed_at TEXT, action TEXT, account TEXT);
        CREATE TABLE IF NOT EXISTS auto_replies (
          id INTEGER PRIMARY KEY, identity_key TEXT UNIQUE, created_at TEXT, updated_at TEXT,
          run_id TEXT, scan_id INTEGER, node_id TEXT, serial TEXT, account TEXT,
          target_url TEXT, author TEXT, screen_text TEXT, reply_text TEXT, status TEXT, message TEXT);
        """)
        with db:
            yield db
    finally:
        db.close()


def create_run(settings):
    run_id = uuid.uuid4().hex
    stamp = now()
    with connection() as db:
        db.execute("INSERT INTO runs (id,started_at,updated_at,status,message,settings) VALUES (?,?,?,?,?,?)",
                   (run_id, stamp, stamp, "STARTING", ("Sıralı otomatik yanıt hazırlanıyor." if settings.get('sequential_enabled') else "Tek hesaplı otomatik yanıt hazırlanıyor.") if settings.get('auto_reply_enabled') else "İzleme hazırlanıyor; otomatik yanıt gönderilmez.", json.dumps(settings, ensure_ascii=False)))
    return run_id


def update_run(run_id, status, message="", process_id=None, next_check=""):
    with connection() as db:
        db.execute("UPDATE runs SET status=?,message=?,updated_at=?,next_check=? WHERE id=?",
                   (status, message, now(), next_check, run_id))
        if process_id is not None:
            db.execute("UPDATE runs SET process_id=? WHERE id=?", (process_id, run_id))
        if status in {"STOPPED", "ERROR"}:
            db.execute("UPDATE runs SET ended_at=?,next_check='' WHERE id=?", (now(), run_id))
            db.execute("UPDATE scans SET status='INTERRUPTED',finished_at=?,message='İzleme sonuçlanmadan durdu.' WHERE run_id=? AND status='SCANNING'", (now(), run_id))


def get_run(run_id=None):
    with connection() as db:
        row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone() if run_id else db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def request_stop(run_id):
    with connection() as db:
        db.execute("UPDATE runs SET stop_requested=1,message='Durdurma istendi; mevcut okuma tamamlanıyor.' WHERE id=?", (run_id,))


def set_process(run_id, pid):
    with connection() as db:
        db.execute("UPDATE runs SET process_id=? WHERE id=?", (pid, run_id))


def process_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            # Access denied does not prove the process is dead.
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def should_stop(run_id):
    row = get_run(run_id)
    return row is None or bool(row["stop_requested"])


def start_scan(run_id, node_id, serial, account, target_url):
    with connection() as db:
        return db.execute("INSERT INTO scans (run_id,started_at,node_id,serial,account,target_url,status) VALUES (?,?,?,?,?,?,?)",
                          (run_id, now(), node_id, serial, account, target_url, "SCANNING")).lastrowid


def finish_scan(scan_id, status, message, new_matches=0, visible_count=0):
    with connection() as db:
        db.execute("UPDATE scans SET status=?,message=?,finished_at=?,new_matches=?,visible_count=? WHERE id=?",
                   (status, message, now(), new_matches, visible_count, scan_id))


def comment_identity(comment_url):
    parsed = urlparse(comment_url.strip())
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or not (host == 'facebook.com' or host.endswith('.facebook.com')):
        raise ValueError('Orijinal yorumun Facebook bağlantısını girin.')
    if parsed.username or parsed.password:
        raise ValueError('Kullanıcı bilgisi içermeyen bir yorum bağlantısı girin.')
    query = parse_qs(parsed.query)
    ids = query.get('comment_id', [])
    if len(ids) != 1 or not re.fullmatch(r'[0-9]{1,100}', ids[0]):
        raise ValueError('Bağlantıda comment_id bulunmalı. Gönderi linki yerine orijinal yorumun bağlantısını kopyalayın.')
    return 'fb-comment:' + ids[0]


def text_fingerprint(text):
    return hashlib.sha256(' '.join(text.casefold().split()).encode('utf-8')).hexdigest()


def add_finding(run_id, scan_id, node_id, serial, account, target_url, text, keyword, draft, comment_url='', author=''):
    # Only a stable comment identity may suppress a replied comment. Text alone never proves identity.
    key = comment_identity(comment_url) if comment_url else ''
    normalized = " ".join(text.casefold().split())
    signature = hashlib.sha256((key or target_url.rstrip("/") + "|" + normalized).encode("utf-8")).hexdigest()
    stamp = now()
    with connection() as db:
        existing = db.execute('SELECT finding_id AS id FROM finding_comments WHERE comment_key=? ORDER BY finding_id DESC LIMIT 1', (key,)).fetchone() if key else None
        existing = existing or db.execute("SELECT id FROM findings WHERE signature=?", (signature,)).fetchone()
        replied = bool(key and db.execute('SELECT 1 FROM comment_replies WHERE comment_key=? AND active=1', (key,)).fetchone())
        if existing:
            db.execute("UPDATE findings SET last_seen=?,seen_count=seen_count+1 WHERE id=?", (stamp, existing["id"]))
            if replied:
                db.execute("UPDATE findings SET review_state='ANSWERED' WHERE id=?", (existing['id'],))
            return False
        cursor = db.execute("""INSERT INTO findings
           (signature,first_seen,last_seen,run_id,scan_id,node_id,serial,account,target_url,screen_text,keyword,draft)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
           (signature, stamp, stamp, run_id, scan_id, node_id, serial, account, target_url, text, keyword, draft))
        if key:
            db.execute('INSERT INTO finding_comments (finding_id,comment_key,comment_url,author) VALUES (?,?,?,?)', (cursor.lastrowid, key, comment_url.strip(), author.strip()))
        if replied:
            db.execute("UPDATE findings SET review_state='ANSWERED' WHERE id=?", (cursor.lastrowid,))
        return not replied


def list_scans(limit=200):
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))]


def list_findings(limit=200):
    with connection() as db:
        rows = [dict(row) for row in db.execute('''SELECT f.*, COALESCE(c.comment_key,'') AS comment_key,
          COALESCE(c.comment_url,'') AS comment_url, COALESCE(c.author,'') AS comment_author,
          COALESCE(r.active,0) AS is_replied, COALESCE(r.account,'') AS reply_account,
          COALESCE(r.replied_at,'') AS reply_at, COALESCE(r.reply_url,'') AS reply_url
          FROM findings f LEFT JOIN finding_comments c ON c.finding_id=f.id
          LEFT JOIN comment_replies r ON r.comment_key=c.comment_key
          ORDER BY f.id DESC LIMIT ?''', (limit,))]
        for row in rows:
            row['similar_replies'] = db.execute('SELECT COUNT(*) FROM comment_replies WHERE active=1 AND target_url=? AND text_fingerprint=?',
                                               (row['target_url'], text_fingerprint(row['screen_text']))).fetchone()[0]
        return rows


def review_finding(row_id):
    with connection() as db:
        db.execute("UPDATE findings SET review_state='REVIEWED' WHERE id=? AND review_state!='ANSWERED'", (row_id,))


def reserve_auto_reply(identity_key, run_id, scan_id, node, serial, account, target, author, text, reply_text):
    stamp = now()
    with connection() as db:
        cursor = db.execute('''INSERT OR IGNORE INTO auto_replies
          (identity_key,created_at,updated_at,run_id,scan_id,node_id,serial,account,target_url,author,screen_text,reply_text,status,message)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (identity_key, stamp, stamp, run_id, scan_id, node, serial, account, target, author, text, reply_text, 'RESERVED', 'Yorum için tek gönderim hakkı ayrıldı.'))
        return cursor.lastrowid if cursor.rowcount else None


def update_auto_reply(row_id, status, message):
    with connection() as db:
        db.execute('UPDATE auto_replies SET status=?,message=?,updated_at=? WHERE id=?', (status, message, now(), row_id))


def interrupt_auto_replies(identity_keys):
    if not identity_keys:
        return
    with connection() as db:
        for key in identity_keys:
            db.execute("UPDATE auto_replies SET status='UNKNOWN',message='İşçi kesildi; otomatik tekrar yok.',updated_at=? WHERE identity_key=? AND status IN ('RESERVED','SENDING')", (now(), key))


def list_auto_replies(limit=200):
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT * FROM auto_replies ORDER BY id DESC LIMIT ?', (limit,))]


def record_reply(row_id, comment_url, account, reply_url='', author=''):
    key = comment_identity(comment_url)
    account = account.strip()
    if not account:
        raise ValueError('Yanıtlayan hesabımızın adını girin.')
    if reply_url and comment_identity(reply_url) != key:
        raise ValueError('Yanıt bağlantısı aynı orijinal yoruma ait olmalı.')
    with connection() as db:
        row = db.execute('SELECT * FROM findings WHERE id=?', (row_id,)).fetchone()
        if not row:
            raise ValueError('Eşleşme kaydı bulunamadı.')
        existing = db.execute('SELECT comment_key FROM finding_comments WHERE finding_id=?', (row_id,)).fetchone()
        if existing and existing['comment_key'] != key:
            raise ValueError('Bu kayıt farklı bir yorum kimliğine bağlı. Doğru yorum kaydını kullanın.')
        # Free the ambiguous text signature: another person's identical text must remain eligible for review.
        db.execute('UPDATE findings SET signature=? WHERE id=?', ('bound:'+str(row_id)+':'+key, row_id))
        db.execute('INSERT OR REPLACE INTO finding_comments (finding_id,comment_key,comment_url,author) VALUES (?,?,?,?)',
                   (row_id, key, comment_url.strip(), author.strip()))
        db.execute('''INSERT INTO comment_replies (comment_key,comment_url,target_url,text_fingerprint,replied_at,account,reply_url,active)
                   VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(comment_key) DO UPDATE SET
                   comment_url=excluded.comment_url,replied_at=excluded.replied_at,account=excluded.account,reply_url=excluded.reply_url,active=1''',
                   (key, comment_url.strip(), row['target_url'], text_fingerprint(row['screen_text']), now(), account, reply_url.strip()))
        db.execute("UPDATE findings SET review_state='ANSWERED' WHERE id IN (SELECT finding_id FROM finding_comments WHERE comment_key=?)", (key,))
        db.execute("INSERT INTO reply_audit (comment_key,changed_at,action,account) VALUES (?,?,'CONFIRMED_REPLIED',?)", (key, now(), account))


def undo_reply(row_id):
    with connection() as db:
        row = db.execute('SELECT comment_key FROM finding_comments WHERE finding_id=?', (row_id,)).fetchone()
        if not row:
            return
        key = row['comment_key']
        db.execute('UPDATE comment_replies SET active=0 WHERE comment_key=?', (key,))
        db.execute("UPDATE findings SET review_state='REVIEWED' WHERE id IN (SELECT finding_id FROM finding_comments WHERE comment_key=?)", (key,))
        db.execute("INSERT INTO reply_audit (comment_key,changed_at,action,account) VALUES (?,?,'UNDONE','')", (key, now()))


def save_settings(settings, path=None):
    path = Path(path or ROOT / "config/watched_posts.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
