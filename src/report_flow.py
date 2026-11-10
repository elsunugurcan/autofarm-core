"""Explicit report category transitions; no coordinate/category guessing."""
import re
import hashlib
import xml.etree.ElementTree as ET
from .comment_reply import label, norm, point, usable, is_edit


def controls(root, pattern):
    parents = {c: n for n in root.iter() for c in n}
    found = {}
    for node in root.iter("node"):
        if not usable(node) or not re.fullmatch(pattern, norm(label(node))):
            continue
        action = node
        while action.get("clickable") != "true" and parents.get(action) is not None:
            action = parents[action]
        if action.get("clickable") != "true" or not usable(action):
            continue
        try:
            found[point(action)] = action
        except ValueError:
            pass
    return list(found.values())


def choose(device, nodes):
    if len(nodes) != 1:
        raise ValueError("Şikayet adımı tek ve açık biçimde eşleştirilemedi.")
    device.click(*point(nodes[0]))


def complete_report(device, reason, wait, record=lambda stage, xml: None):
    patterns = {"SPAM": r"spam|istenmeyen içerik|istenmeyen mesaj",
                "SAHTE": r"fake account|fake profile|pretending to be someone|sahte hesap|birini taklit ediyor",
                "TACIZ": r"harassment|bullying|bullying or harassment|taciz|zorbalık",
                "UYGUNSUZ": r"inappropriate content|nudity|uygunsuz içerik|çıplaklık"}
    if reason not in patterns:
        return "[SIKAYET GONDERILMEDI] Desteklenmeyen kategori; başka neden seçilmedi."
    selected = False
    submitted = False
    actions = set()
    scrolls = 0
    for step in range(12):
        if device.app_current().get("package") != "com.facebook.katana":
            return "[SIKAYET BELIRSIZ] Facebook ön plandan çıktı; sonuç doğrulanamadı."
        xml = device.dump_hierarchy()
        record(f"step_{step}", xml)
        root = ET.fromstring(xml)
        texts = {norm(label(n)) for n in root.iter("node") if usable(n) and not is_edit(n)}
        receipt = any(re.match(r"thanks for (?:your report|reporting|letting us know|your feedback)|we(?:'ve| have) received your report|your report has been submitted|report submitted|şikayetiniz alındı|bildiriminiz alındı", t) for t in texts)
        if selected and receipt:
            done = controls(root, r"done|close|bitti|tamam|kapat")
            if len(done) == 1:
                choose(device, done)
                wait(1)
            return "[SIKAYET ALINDI EKRANI] Facebook bildirimin alındığına dair onay gösterdi."
        if texts & {"try again", "something went wrong", "please try again later"}:
            return "[SIKAYET BELIRSIZ] Facebook hata gösterdi; otomatik tekrar yok."
        state = hashlib.sha256(xml.encode()).hexdigest()
        category = controls(root, patterns[reason]) if not selected else []
        if category:
            choose(device, category)
            selected = True
            wait(2)
            continue
        # The first screen can be a parent category, not the actual Spam choice.
        if not selected:
            parent_pattern = r"(?:scams?, fraud (?:or|and) false information|scams?, fraud (?:or|and) spam|fraud, scams? (?:or|and) spam|scams? or spam)" if reason == "SPAM" else r"(?!)"
            parent = controls(root, parent_pattern)
            route = controls(root, r"something about this (?:profile|page|group)|something about this account")
            option = parent or route
            if option and (state, "parent") not in actions:
                choose(device, option)
                actions.add((state, "parent"))
                wait(2)
                continue
            if scrolls < 2 and any(n.get("scrollable") == "true" for n in root.iter("node")):
                device.swipe_ext("up", scale=0.5)
                scrolls += 1
                wait(1)
                continue
            return "[SIKAYET GONDERILMEDI] Seçilen kategori bulunamadı; başka neden seçilmedi."
        for kind, pattern in [("submit", r"submit|submit report|send report|report|confirm|gönder|onayla"),
                              ("next", r"next|continue|ileri|devam")]:
            nodes = controls(root, pattern)
            if nodes and (state, kind) not in actions and (kind != "submit" or not submitted):
                choose(device, nodes)
                submitted = submitted or kind == "submit"
                actions.add((state, kind))
                wait(2)
                break
        else:
            # Wait for confirmation without retrying submission or guessing Done.
            wait(2)
    return "[SIKAYET BELIRSIZ] Kategori seçildi" + (", gönderim tetiklendi" if submitted else "") + "; alındı onayı görülmedi. Otomatik tekrar yok."

