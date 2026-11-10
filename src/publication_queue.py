"""Manual-start, durable publication plans using the existing photo pipeline."""
from . import sequential_jobs as queue
from . import operation_timing as timing


def log(text):
    print(text, flush=True)


def create(image_path, caption, targets, selected, metadata):
    data = {"image_path": image_path, "caption": caption, "targets": list(dict.fromkeys(targets)),
            "selected_serials": list(dict.fromkeys(selected)), "metadata": metadata}
    plan_id = queue.new_plan("publication", data)
    for target in data["targets"]:
        queue.enqueue(plan_id, target, {"target": target})
    return plan_id


def run(api, plan_id, media_path):
    stored = queue.plan(plan_id)
    if not stored or stored["kind"] != "publication":
        raise ValueError("Paylaşım sırası bulunamadı.")
    data = stored["data"]
    info = data["metadata"]
    options = info.get("timing")
    links, blocked = [], set()
    queue.acquire(plan_id)
    queue.recover(plan_id)
    queue.set_plan(plan_id, "RUNNING")
    processed = 0
    try:
        while any(j["status"] == "WAITING" for j in queue.jobs(plan_id)):
            output = api.subprocess.check_output(["adb", "devices"], text=True)
            online = {p[0] for line in output.splitlines()[1:] if len(p := line.split()) >= 2 and p[1] == "device"}
            pool = [s for s in data["selected_serials"] if s in online and s not in blocked]
            if not pool:
                log("[PAYLAŞIM SIRASI] Uygun ONLINE cihaz yok; kalan işler bekliyor.")
                break
            if processed:
                seconds = timing.delay(options) if options else 5
                log(f"[PAYLAŞIM ARALIĞI] {seconds} saniye.")
                api.time.sleep(seconds)
                # Recheck after the pause as well, before assigning.
                output = api.subprocess.check_output(["adb", "devices"], text=True)
                online = {p[0] for line in output.splitlines()[1:] if len(p := line.split()) >= 2 and p[1] == "device"}
                pool = [s for s in pool if s in online]
            job = queue.claim(plan_id, pool)
            if job is None:
                break
            serial, target = job["serial"], job["payload"]["target"]
            row_id = None
            sending = False
            try:
                ok, _, _ = api.check_vpn_and_temp(serial)
                if not ok:
                    blocked.add(serial)
                    queue.finish(job["id"], "WAITING", "VPN kapalı; başka seçili telefon bekleniyor.")
                    continue
                device = info.get("devices", {}).get(serial, {})
                row_id = api.start_share(device.get("node_id", serial), serial, device.get("fb_name", "Kayıtlı ad yok"),
                    info.get("targets", {}).get(target, target), target, data["caption"],
                    info.get("image_name", ""), info.get("history_image", data["image_path"]))
                def before_send():
                    nonlocal sending
                    queue.finish(job["id"], "SENDING", "Post tetikleniyor; yayın teyitsiz.")
                    api.update_share(row_id, "SENDING")
                    sending = True
                result = api.share_on_fb_group_and_grab_link(serial, device.get("node_id", serial), target,
                    data["caption"], media_path, on_sending=before_send, account_name=device.get("fb_name", ""), timing_settings=options)
                api.update_share(row_id, result["status"], result["detail"], result["post_url"])
                queue.finish(job["id"], result["status"], result["detail"])
                if result["post_url"]:
                    links.append(result["post_url"])
                processed += 1
            except Exception as exc:
                queue.finish(job["id"], "UNKNOWN" if sending else "ERROR", str(exc))
                if row_id is not None:
                    api.update_share(row_id, "UNVERIFIED" if sending else "ERROR", str(exc))
                processed += 1
            finally:
                api.home_and_sleep(serial)
    finally:
        queue.release(plan_id, "PAUSED" if any(j["status"] == "WAITING" for j in queue.jobs(plan_id)) else "FINISHED")
    return links
