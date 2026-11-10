"""Verified portrait comment composer; a send click is never publication proof."""
import re
import xml.etree.ElementTree as ET
from .comment_reply import is_edit, label, norm, point, usable
from .facebook_navigation import group_feed


def ensure_portrait(device, lock, wait):
    for _ in range(3):
        lock()
        wait(0.6)
        info = device.info
        width, height = info.get("displayWidth", 0), info.get("displayHeight", 0)
        rotation = info.get("displayRotation")
        if width > 0 and height >= width and rotation in (None, 0):
            return
    raise ValueError("Ekran dikey moda geçmedi; yorum yazılmadı/gönderilmedi.")


def public_composer(xml, expected=None):
    root = ET.fromstring(xml)
    fields = [n for n in root.iter("node") if usable(n) and is_edit(n)]
    if len(fields) != 1:
        raise ValueError("Tek bir gönderi yorum alanı bulunamadı.")
    field = fields[0]
    hint = norm(" ".join(field.get(k, "") for k in ("content-desc", "hint", "text")))
    recipient_hint = norm(" ".join(field.get(k, "") for k in ("content-desc", "hint")))
    if "reply" in recipient_hint or "yanıt" in recipient_hint:
        raise ValueError("Gönderi yorumu yerine yanıt alanı açık; gönderilmedi.")
    if expected is None:
        if not re.search(r"\bcomment\b|yorum", hint):
            raise ValueError("Açık alanın gönderi yorum alanı olduğu doğrulanamadı.")
    elif field.get("text", "") != expected:
        raise ValueError("Yorum metni yazma alanında doğrulanamadı; gönderilmedi.")
    return root, field


def post_comment(device, text, lock, wait, diagnostic=lambda stage, xml: None, recheck=None):
    sending = False

    def dump(stage):
        xml = device.dump_hierarchy()
        diagnostic(stage, xml)
        return xml

    def foreground():
        if device.app_current().get("package") != "com.facebook.katana":
            raise ValueError("Facebook ön planda değil; yorum gönderilmedi.")

    try:
        foreground()
        ensure_portrait(device, lock, wait)
        xml = dump("before_comment")
        if group_feed(xml):
            raise ValueError("Facebook gönderi yerine grup akışını açtı; başka gönderiye yorum yazılmadı. Doğrudan gönderi bağlantısını kontrol edin.")
        try:
            public_composer(xml)
        except ValueError:
            root = ET.fromstring(xml)
            controls = [n for n in root.iter("node") if usable(n) and
                        re.fullmatch(r"comment|comments|view comments|\d+[,.\d]* comments|comment button(?:[.].*)?|yorum yap|yorumlar", norm(label(n)))]
            if len(controls) != 1:
                raise ValueError("Gönderiye ait tek Comment düğmesi bulunamadı; rastgele alana tıklanmadı.")
            device.click(*point(controls[0]))
            wait(1.5)
        ensure_portrait(device, lock, wait)
        _, field = public_composer(dump("composer"))
        selector = device(className=field.get("class"))
        if selector.count != 1:
            raise ValueError("Yorum alanı değişti; yazılmadı.")
        selector.click()
        ensure_portrait(device, lock, wait)
        public_composer(dump("keyboard"))
        selector.set_text(text)
        wait(0.5)
        ensure_portrait(device, lock, wait)
        xml = dump("typed")
        root, field = public_composer(xml, text)
        foreground()
        # Search only ancestors of the verified composer, never a guessed coordinate.
        parents = {child: parent for parent in root.iter() for child in parent}
        scope = parents.get(field)
        buttons = []
        while scope is not None:
            buttons = [n for n in scope.iter("node") if usable(n) and
                       norm(label(n)) in {"send", "post", "send comment", "post comment", "gönder", "paylaş"}]
            if len(buttons) == 1:
                break
            if len(buttons) > 1:
                raise ValueError("Birden fazla gönderme düğmesi var; yorum gönderilmedi.")
            scope = parents.get(scope)
        if not buttons:
            raise ValueError("Yorum alanına ait Send/Post düğmesi bulunamadı.")
        sending = True
        device.click(*point(buttons[0]))
        from .delivery_check import wait_for_delivery
        state, message = wait_for_delivery(device, wait, recheck, record=diagnostic)
        prefix = "[YORUM YENIDEN GORULDU]" if state == "RECHECK_VISIBLE" else "[SONUC BELIRSIZ]" if state == "UNKNOWN" else "[GONDERIM DENENDI]"
        return f"{prefix} {message}"
    except Exception as exc:
        state = "[SONUC BELIRSIZ]" if sending else "[YORUM GONDERILMEDI]"
        return f"{state} {exc}"
