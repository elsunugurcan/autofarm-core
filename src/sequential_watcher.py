"""Read incoming requests first, then reply sequentially with balanced devices."""
from pathlib import Path
import shlex
from . import sequential_jobs as queue
from . import comment_reply
from .facebook_navigation import clean_post_url, open_post_comments
from .delivery_check import recheck_comment
from . import operation_timing as timing


def dispatch(plan_id, selected, online, ready, send, wait, stopped, gap, limit, log):
    blocked, per_target = set(), {}
    attempts = 0
    while not stopped():
        pending = [j for j in queue.jobs(plan_id) if j["status"] == "WAITING" and per_target.get(j["payload"]["target"], 0) < limit]
        online_now = set(online())
        available = [s for s in selected if s in online_now and s not in blocked]
        if not pending or not available:
            break
        if attempts and gap:
            log(f"[YANIT ARALIĞI] {gap} saniye bekleniyor.")
            if wait(gap) is False or stopped():
                break
            online_now = set(online())
            available = [s for s in selected if s in online_now and s not in blocked]
            if not available:
                break
        excluded = {j["id"] for j in queue.jobs(plan_id) if per_target.get(j["payload"]["target"], 0) >= limit}
        job = queue.claim(plan_id, available, excluded)
        if job is None:
            break
        if stopped():
            queue.finish(job["id"], "WAITING", "Durduruldu; henüz gönderilmedi.")
            break
        ok, reason = ready(job["serial"])
        if not ok:
            queue.finish(job["id"], "WAITING", reason)
            blocked.add(job["serial"])
            continue
        sending = False
        def before_send():
            nonlocal sending
            sending = True
            queue.finish(job["id"], "SENDING", "Send tetikleniyor; yayın henüz doğrulanmadı.")
        try:
            state, message = send(job, before_send)
        except Exception as exc:
            state, message = ("UNKNOWN" if sending else "NOT_SENT"), str(exc)
        queue.finish(job["id"], state, message)
        if state == "WAITING":
            blocked.add(job["serial"])
            continue
        log(f"[SIRALI YANIT] {job['serial']} | {job['payload']['author']} | {state}: {message}")
        if state not in {"SKIPPED", "ALREADY_RECORDED"}:
            attempts += 1
            target = job["payload"]["target"]
            per_target[target] = per_target.get(target, 0) + 1
    return attempts


def _open(api, device, serial, target, run_id):
    api.adb("-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(target)), "com.facebook.katana")
    return api.wait_for(5, run_id) and device.app_current().get("package") == "com.facebook.katana"


def discover(api, serial, target, run_id, scan_id):
    import uiautomator2 as u2
    device = u2.connect(serial)
    device.screen_on()
    folder = Path(api.WATCH_FILE).parent.parent / "logs/watcher_layout"
    folder.mkdir(parents=True, exist_ok=True)
    def record(stage, xml):
        (folder / f"scan_{scan_id}_sequence_{stage}.xml").write_text(xml, encoding="utf-8")
    if not _open(api, device, serial, target, run_id):
        return []
    wait = lambda n: api.wait_for(n, run_id)
    stop = lambda: api.stopping(run_id)
    open_post_comments(device, wait, stop, record)
    results = {}
    for page in range(3):
        if stop():
            break
        xml = device.dump_hierarchy()
        record(f"page_{page}", xml)
        for candidate in comment_reply.comments_from_xml(xml):
            key = comment_reply.comment_key(target, candidate["author"], candidate["text"])
            if key in results:
                candidate["has_replies"] = candidate.get("has_replies", False) or results[key].get("has_replies", False)
            results[key] = candidate
        if page < 2:
            device.swipe_ext("up", scale=0.5)
            if wait(1) is False:
                break
    return list(results.values())


def deliver(api, run_id, settings, job, before_send):
    import uiautomator2 as u2
    serial, payload = job["serial"], job["payload"]
    target = payload["target"]
    meta = settings["device_metadata"][serial]
    node, account = meta.get("node_id", serial), meta["fb_name"]
    scan_id = api.history.start_scan(run_id, node, serial, account, target)
    folder = Path(api.WATCH_FILE).parent.parent / "logs/watcher_layout"
    folder.mkdir(parents=True, exist_ok=True)
    def record(stage, xml):
        (folder / f"job_{job['id']}_{scan_id}_{stage}.xml").write_text(xml, encoding="utf-8")
    wait = lambda n: api.wait_for(n, run_id)
    stop = lambda: api.stopping(run_id)
    row_id = None
    candidate = None
    sent = False
    state, message = "NOT_SENT", "Hedef yorum bu telefonda doğrulanamadı; gönderilmedi."
    def outcome(new_state, new_message):
        nonlocal state, message
        state, message = new_state, new_message
        return state, message
    try:
        device = u2.connect(serial)
        device.screen_on()
        options = settings.get("timing")
        if options and options["prewarm_enabled"]:
            api.adb("-s", serial, "shell", "monkey", "-p", "com.facebook.katana", "-c", "android.intent.category.LAUNCHER", "1")
            if not timing.prewarm(device, options, wait, api.log, stop):
                return outcome("WAITING", "Ön ısınmada durduruldu; gönderilmedi.")
        if not _open(api, device, serial, target, run_id):
            return outcome("NOT_SENT", "Hedef Facebook'ta açılamadı.")
        open_post_comments(device, wait, stop, record)
        candidate = None
        for page in range(3):
            if stop():
                return outcome("WAITING", "Durduruldu; henüz gönderilmedi.")
            xml = device.dump_hierarchy()
            record(f"locate_{page}", xml)
            found = [r for r in comment_reply.comments_from_xml(xml) if comment_reply.norm(r["author"]) == comment_reply.norm(payload["author"]) and r["text"] == payload["text"]]
            if len(found) == 1:
                candidate = found[0]
                break
            if page < 2:
                device.swipe_ext("up", scale=0.5)
                if wait(1) is False:
                    return outcome("WAITING", "Durduruldu; henüz gönderilmedi.")
        if candidate is None:
            return outcome("NOT_SENT", message)
        if candidate.get("has_replies"):
            return outcome("SKIPPED", "View reply göstergesi oluştu; yanıt atlandı.")
        key = comment_reply.comment_key(target, candidate["author"], candidate["text"])
        row_id = api.history.reserve_auto_reply(key, run_id, scan_id, node, serial, account, target,
                    candidate["author"], candidate["text"], settings["reply_template"])
        if row_id is None:
            return outcome("ALREADY_RECORDED", "Bu yorum için önceki gönderim denemesi kayıtlı; tekrar yok.")
        api.history.add_finding(run_id, scan_id, node, serial, account, target, candidate["text"], payload["keyword"], settings["reply_template"])
        def sending():
            nonlocal sent
            api.history.update_auto_reply(row_id, "SENDING", "Send tetikleniyor.")
            before_send()
            sent = True
        def reopen():
            return not stop() and _open(api, device, serial, target, run_id)
        verify = lambda: recheck_comment(device, account, settings["reply_template"], reopen, wait, candidate, record)
        state, message = comment_reply.send_reply(device, candidate, settings["reply_template"], stop, wait, sending, recheck=verify, record=record)
        return state, message
    except Exception as exc:
        if not sent and row_id is None and serial not in api.online_serials():
            return outcome("WAITING", "Telefon gönderimden önce OFFLINE oldu; iş başka telefon için bekliyor.")
        state, message = ("UNKNOWN" if sent else "NOT_SENT"), str(exc)
        return state, message
    finally:
        if row_id is not None:
            api.history.update_auto_reply(row_id, state, message)
        api.history.finish_scan(scan_id, "AUTO_ATTEMPTED" if row_id is not None else "INTERRUPTED" if state == "WAITING" else "ERROR" if state == "NOT_SENT" else "DONE", message, 1 if row_id is not None else 0, 1 if candidate is not None else 0)
        api.sleep_phone(serial)


def scan_cycle(api, run_id, settings):
    plan_id = queue.watcher_plan(settings)
    queue.set_plan(plan_id, "RUNNING")
    own_names = {comment_reply.norm(v.get("fb_name", "")) for v in settings["device_metadata"].values()}
    try:
        # Discovery never sends; dispatch uses a fresh phone check for every request.
        for target in settings["posts"]:
            if api.stopping(run_id):
                break
            online_now = api.online_serials()
            available = [s for s in settings["selected_serials"] if s in online_now]
            if not available:
                break
            serial = next((s for s in available if api.check_readiness(s)[0]), None)
            if serial is None:
                continue
            meta = settings["device_metadata"][serial]
            scan = api.history.start_scan(run_id, meta.get("node_id", serial), serial, meta["fb_name"], target)
            try:
                candidates = discover(api, serial, target, run_id, scan)
                added = 0
                for candidate in candidates:
                    keyword = api.match_keyword(candidate["text"], settings["keywords"])
                    if not keyword or candidate.get("has_replies") or comment_reply.norm(candidate["author"]) in own_names:
                        continue
                    key = comment_reply.comment_key(target, candidate["author"], candidate["text"])
                    added += queue.enqueue(plan_id, key, {"target": target, "author": candidate["author"], "text": candidate["text"], "keyword": keyword})
                api.history.finish_scan(scan, "DONE" if candidates else "CONTEXT_MISSING", f"{len(candidates)} yorum okundu; {added} yeni istek sıraya alındı.", added, len(candidates))
            except Exception as exc:
                api.history.finish_scan(scan, "ERROR", str(exc))
                api.log(f"[SIRALI OKUMA HATASI] {exc}")
            finally:
                api.sleep_phone(serial)
        dispatch(plan_id, settings["selected_serials"], api.online_serials, api.check_readiness,
                 lambda job, before: deliver(api, run_id, settings, job, before),
                 lambda n: api.wait_for(n, run_id), lambda: api.stopping(run_id),
                 settings["reply_delay_seconds"], settings["max_replies_per_visit"], api.log)
    finally:
        queue.set_plan(plan_id, "WAITING_CYCLE")
