"""Conservative single-account reply adapter for English Facebook comment views.

No fixed coordinates, no account switching, no unverified global Reply clicks.
"""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET


def norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def label(node):
    return (node.get("text") or node.get("content-desc") or "").strip()


def is_edit(node):
    return node.get("class") in {"android.widget.EditText", "android.widget.AutoCompleteTextView"}


def usable(node):
    return node.get("visible-to-user") != "false" and node.get("enabled") != "false"


def is_reply(node):
    text = norm(label(node))
    return usable(node) and (text in {"reply", "yanıtla", "cevapla"} or
                            node.get("clickable") == "true" and bool(re.fullmatch(r"reply to .{1,100}(?:'s comment)?", text)))


def point(node):
    values = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
    if not values:
        raise ValueError("Düğmenin geçerli ekran konumu yok.")
    left, top, right, bottom = map(int, values.groups())
    if right <= left or bottom <= top:
        raise ValueError("Düğme ekran dışında veya boş.")
    return (left + right) // 2, (top + bottom) // 2


def control_text(text):
    value = norm(text)
    return bool(re.match(r"(?:like|downvote) .+\'s comment(?: button[.]?.*)?$", value)) or value in {"just now", "now", "yesterday", "today", "like", "liked", "reply", "replies", "share", "edited", "author", "admin", "moderator", "follow", "see more", "see less", "most relevant", "all comments", "top fan", "view profile"} or bool(re.fullmatch(r"\d+\s*(?:s|m|h|d|w|y|sec|min|hr|hrs|hour|hours|day|days|week|weeks)(?:\s+ago)?", value)) or bool(re.fullmatch(r"(?:view|hide)\s+\d+\s+repl(?:y|ies)", value))


def _row_info(row, parents, reply):
    nodes = [n for n in row.iter("node") if usable(n)]
    reaction_nodes = {child for n in nodes if re.match(r"\d+\s+reactions?\b", norm(label(n))) for child in n.iter("node")}
    leaves = [n for n in nodes if n not in reaction_nodes and label(n) and not list(n) and not is_edit(n)]
    # Facebook exposes the name and body as Buttons on this phone.
    profile_names = {label(n)[:-len(" profile picture")] for n in leaves
                     if n.get("class") == "android.widget.ImageView" and label(n).endswith(" profile picture")}
    author_nodes = [n for n in leaves if label(n) in profile_names
                    and n.get("clickable") == "true" and n.get("class") == "android.widget.Button"]
    if not author_nodes:
        author_nodes = [n for n in leaves if re.search(r"(?:author|actor|user|profile)[_-]?name", n.get("resource-id", ""), re.I)]
    if not author_nodes:
        author_nodes = [n for n in leaves if n.get("clickable") == "true" and n.get("class") in {"android.widget.TextView", "android.view.View"} and not control_text(label(n)) and n is not reply and len(label(n)) <= 100]
    authors = list(dict.fromkeys(label(n) for n in author_nodes))
    if len(authors) != 1:
        return None
    author = authors[0]
    bodies = [n for n in leaves if re.search(r"comment[_-]?(?:text|body|content)|message[_-]?text", n.get("resource-id", ""), re.I)]
    if not bodies:
        bodies = [n for n in leaves if n not in author_nodes and n is not reply and not control_text(label(n)) and label(n) != author and (n.get("class") != "android.widget.Button" or n.get("clickable") == "false") and not label(n).endswith(" profile picture")]
    values = list(dict.fromkeys(label(n) for n in bodies if 1 <= len(label(n)) <= 1500))
    if len(values) != 1:
        return None
    try:
        position = point(reply)
    except ValueError:
        return None
    has_replies = any(re.search(r"\b(?:view\s+)?\d+\s+repl(?:y|ies)\b|\bview\s+repl(?:y|ies)\b", norm(label(n))) for n in nodes)
    return {"author": author, "text": values[0], "reply_point": position, "has_replies": has_replies}


def reply_indicator(row, parents):
    def controls(scope):
        return [n for n in scope.iter("node") if usable(n) and
                re.match(r"(?:view|hide)\s+(?:\d+\s+)?repl(?:y|ies)\b", norm(label(n)))]
    found = controls(row)
    item = row
    while parents.get(item) is not None:
        parent = parents[item]
        if parent.get("class") in {"androidx.recyclerview.widget.RecyclerView", "android.widget.ListView"} or parent.get("scrollable") == "true":
            siblings = list(parent)
            for following in siblings[siblings.index(item)+1:siblings.index(item)+4]:
                # A following author/comment starts a new row; never borrow its reply count.
                if any(is_reply(n) or label(n).endswith(" profile picture") for n in following.iter("node")):
                    break
                indicators = controls(following)
                if indicators:
                    found.extend(indicators)
                    break
            break
        if len([n for n in parent.iter("node") if is_reply(n)]) > 1:
            break
        item = parent
        found.extend(controls(item))
    clickable = [n for n in dict.fromkeys(found) if n.get("clickable") == "true"]
    position = None
    if len(clickable) == 1:
        try:
            position = point(clickable[0])
        except ValueError:
            pass
    return bool(found), position


def comments_from_xml(xml):
    root = ET.fromstring(xml)
    parents = {child: parent for parent in root.iter() for child in parent}
    results = []
    for reply in [n for n in root.iter("node") if is_reply(n)]:
        row = parents.get(reply)
        for _ in range(10):
            if row is None:
                break
            if len([n for n in row.iter("node") if is_reply(n)]) != 1:
                break
            info = _row_info(row, parents, reply)
            if info:
                indicator, expand_point = reply_indicator(row, parents)
                info["has_replies"] = info["has_replies"] or indicator
                info["reply_expand_point"] = expand_point
                results.append(info)
                break
            row = parents.get(row)
    # Identical visible rows are ambiguous; do not choose either by screen position.
    counts = {}
    for row in results:
        key = (norm(row["author"]), norm(row["text"]))
        counts[key] = counts.get(key, 0) + 1
    return [r for r in results if counts[(norm(r["author"]), norm(r["text"]))] == 1]


def comment_key(target, author, text):
    parts = urlsplit(target)
    # Ignore tracking parameters, preserve the post path and identity-bearing query keys.
    from urllib.parse import parse_qsl, urlencode
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k in {"story_fbid", "id", "fbid", "comment_id"}))
    canonical = urlunsplit(("https", (parts.hostname or "").removeprefix("www.").removeprefix("m."), parts.path.rstrip("/"), query, ""))
    return hashlib.sha256((canonical + "|" + norm(author) + "|" + norm(text)).encode("utf-8")).hexdigest()


def composer(xml, author, expected_text=None):
    root = ET.fromstring(xml)
    edits = [n for n in root.iter("node") if usable(n) and is_edit(n)]
    if len(edits) != 1:
        raise ValueError("Tek ve açık bir yanıt yazma alanı bulunamadı.")
    author_text = norm(author)
    # Do not accept a comment's arbitrary text as proof of the composer recipient.
    parents = {child: parent for parent in root.iter() for child in parent}
    context = parents.get(edits[0])
    recipient = False
    while context is not None:
        if any(is_reply(n) for n in context.iter("node")):
            break
        fields = [n for n in context.iter("node") if usable(n) and is_edit(n)]
        if len(fields) != 1:
            break
        recipient = bool(re.fullmatch(r"(?:write a )?reply(?:ing)? to\s+" + re.escape(author_text) + r"[.:…]*", norm(edits[0].get("content-desc", ""))))
        recipient = recipient or any(re.fullmatch(r"reply(?:ing)? to\s+" + re.escape(author_text) + r"[.:…]*", norm(label(n)))
                        for n in context.iter("node") if usable(n) and not is_edit(n) and n.get("clickable") != "true")
        if recipient:
            break
        context = parents.get(context)
    if not recipient or context is None:
        raise ValueError("Yanıt alanındaki Replying to / Reply to alıcısı yorum yazarıyla doğrulanamadı; gönderilmedi.")
    if expected_text is not None and edits[0].get("text", "") != expected_text:
        raise ValueError("Yanıt metni yazma alanında doğrulanamadı; gönderilmedi.")
    return context, edits[0]


def send_point(root, edit):
    parents = {child: parent for parent in root.iter() for child in parent}
    row = parents.get(edit)
    send_labels = {"send", "send reply", "post", "post reply", "gönder", "yanıtı gönder"}
    while row is not None:
        edits = [n for n in row.iter("node") if usable(n) and is_edit(n)]
        buttons = [n for n in row.iter("node") if usable(n) and norm(label(n)) in send_labels]
        if len(edits) == 1 and len(buttons) == 1:
            return point(buttons[0])
        if len(buttons) > 1:
            break
        row = parents.get(row)
    raise ValueError("Yanıt alanına bağlı tek bir Send düğmesi bulunamadı.")


def send_reply(device, candidate, reply_text, should_stop, wait, before_send, recheck=None, record=lambda stage, xml: None):
    if should_stop():
        raise ValueError("Durdurma istendi; yanıt gönderilmedi.")
    if device.app_current().get("package") != "com.facebook.katana":
        raise ValueError("Facebook ön planda değil.")
    current = [r for r in comments_from_xml(device.dump_hierarchy()) if norm(r["author"]) == norm(candidate["author"]) and norm(r["text"]) == norm(candidate["text"])]
    if len(current) != 1:
        raise ValueError("Yorum satırı yeniden doğrulanamadı; yanıt gönderilmedi.")
    if current[0].get("has_replies"):
        raise ValueError("Yorumda mevcut yanıt göstergesi var; yeniden yanıt gönderilmedi.")
    device.click(*current[0]["reply_point"])
    if not wait(1):
        raise ValueError("Durdurma istendi; yanıt gönderilmedi.")
    _, input_field = composer(device.dump_hierarchy(), candidate["author"])
    edit = device(className=input_field.get("class"))
    if edit.count != 1:
        raise ValueError("Yanıt yazma alanı değişti.")
    edit.set_text(reply_text)
    root, field = composer(device.dump_hierarchy(), candidate["author"], reply_text)
    position = send_point(root, field)
    if should_stop():
        raise ValueError("Durdurma istendi; Send düğmesine basılmadı.")
    if device.app_current().get("package") != "com.facebook.katana":
        raise ValueError("Gönderimden önce Facebook ön plandan çıktı; gönderilmedi.")
    before_send()
    device.click(*position)
    from .delivery_check import wait_for_delivery
    return wait_for_delivery(device, wait, recheck, should_stop, record)
