"""Wait for submission before task cleanup; recheck without sending again."""
import re
import xml.etree.ElementTree as ET


def editor_empty(field):
    text = field.get("text", "").strip()
    if not text:
        return True
    hint = field.get("hint", "").strip()
    return bool(hint and text == hint and re.match(r"(?i)^(write|add|reply|yorum)", hint))


def wait_for_delivery(device, wait, recheck=None, stopped=lambda: False,
                      record=lambda stage, xml: None, minimum=16, timeout=30):
    from .comment_reply import is_edit, label, norm, usable
    last_reason = "Gönderim sonrası ekran doğrulanamadı."
    for elapsed in range(2, timeout + 1, 2):
        # Keep Facebook open even after an optimistic local comment appears.
        if wait(2) is False or stopped():
            return "SEND_UNVERIFIED", "Durdurma istendi; yayın teyit edilmedi. Otomatik tekrar yok."
        try:
            xml = device.dump_hierarchy()
            record("delivery", xml)
            root = ET.fromstring(xml)
            texts = {norm(label(n)) for n in root.iter("node") if usable(n) and not is_edit(n)}
            if texts & {"retry", "try again", "failed to post", "couldn't post comment", "comment couldn't be posted"}:
                return "UNKNOWN", "Facebook gönderim hatası gösterdi. Otomatik tekrar yok."
            pending = any(re.fullmatch(r"(?:posting|sending|uploading|pending)[.…]*", value) for value in texts)
            fields = [n for n in root.iter("node") if usable(n) and is_edit(n)]
            cleared = len(fields) == 1 and editor_empty(fields[0])
            if elapsed >= minimum and cleared and not pending:
                if recheck is not None:
                    try:
                        if recheck():
                            return "RECHECK_VISIBLE", "Gönderi yeniden açıldığında hesap ve yanıt metni görüldü; bağımsız yayın teyidi değildir. Otomatik tekrar yok."
                    except Exception as exc:
                        return "SEND_UNVERIFIED", f"Yeniden kontrol tamamlanamadı: {exc}. Otomatik tekrar yok."
                return "SEND_UNVERIFIED", "Gönderim beklemesi tamamlandı; yayın yeniden kontrolde teyit edilemedi. Otomatik tekrar yok."
            last_reason = "Gönderim hâlâ bekliyor veya yorum alanı temizlenmedi."
        except Exception as exc:
            last_reason = f"Gönderim ekranı okunamadı: {exc}."
    return "UNKNOWN", last_reason + " Yayın belirsiz; otomatik tekrar yok."


def recheck_comment(device, author, text, reopen, wait, candidate=None,
                    record=lambda stage, xml: None):
    from .comment_reply import comments_from_xml, norm, label, is_reply, point
    from .facebook_navigation import open_post_comments
    if not author or reopen() is False:
        return False
    if not open_post_comments(device, wait, record=record):
        return False
    thread_opened = candidate is None
    for page in range(3):
        xml = device.dump_hierarchy()
        record("recheck", xml)
        rows = comments_from_xml(xml)
        if thread_opened and any(norm(r["author"]) == norm(author) and r["text"] == text for r in rows):
            return True
        if candidate is not None and not thread_opened:
            matches = [r for r in rows if norm(r["author"]) == norm(candidate["author"]) and r["text"] == candidate["text"]]
            if len(matches) == 1:
                if matches[0].get("reply_expand_point"):
                    device.click(*matches[0]["reply_expand_point"])
                    wait(2)
                    thread_opened = True
                    continue
                root = ET.fromstring(xml)
                parents = {c: n for n in root.iter() for c in n}
                controls = [n for n in root.iter("node") if is_reply(n) and point(n) == matches[0]["reply_point"]]
                if len(controls) == 1:
                    scope = parents.get(controls[0])
                    while scope is not None:
                        if len([n for n in scope.iter("node") if is_reply(n)]) > 1:
                            break
                        expand = [n for n in scope.iter("node") if n.get("clickable") == "true" and
                                  re.match(r"view\s+(?:\d+\s+)?repl(?:y|ies)\b", norm(label(n)))]
                        if len(expand) == 1:
                            device.click(*point(expand[0]))
                            wait(2)
                            thread_opened = True
                            break
                        scope = parents.get(scope)
                    if thread_opened:
                        continue
        if page < 2:
            device.swipe_ext("up", scale=0.5)
            wait(1)
    return False
