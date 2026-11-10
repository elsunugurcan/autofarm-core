"""Normalize post targets and distinguish group feeds from comment views."""
import re
import xml.etree.ElementTree as ET
from .comment_reply import label, norm, usable, point, comments_from_xml


def clean_post_url(url):
    # Facebook owns share-link resolution. Preserve path, query and fragment;
    # rewriting them can change what its Android activity resolves.
    return url.strip()


def group_feed(xml):
    root = ET.fromstring(xml)
    texts = {norm(label(n)) for n in root.iter("node") if usable(n)}
    return "group posts" in texts or "member tools more options" in texts or (
        "write something..." in texts and "photo/video" in texts)


def open_post_comments(device, wait, stopped=lambda: False, record=lambda stage, xml: None):
    """Reobserve after each scroll; never select a post from a group feed."""
    keyboard_hidden = False
    for step in range(3):
        if stopped():
            return False
        xml = device.dump_hierarchy()
        record(f"navigation_{step}", xml)
        if comments_from_xml(xml):
            tree = ET.fromstring(xml)
            if any("inputmethod" in n.get("package", "") for n in tree.iter("node")):
                if keyboard_hidden:
                    raise ValueError("Klavye kapatılamadı; yorum listesine rastgele kaydırma yapılmadı.")
                keyboard_hidden = True
                device.press("back")  # Hide IME; do not scroll the keyboard instead of the comment list.
                wait(0.5)
                continue
            return True
        if group_feed(xml):
            raise ValueError("Facebook verilen bağlantıyı gönderi yerine grup ekranında açtı; yorum yapılmadı. Açılış kaydı logs/watcher_layout içinde.")
        root = ET.fromstring(xml)
        buttons = [n for n in root.iter("node") if usable(n) and
                   re.fullmatch(r"comments?|view comments|\d+[,.\d]* comments|comment button(?:[.].*)?|yorumlar|yorum yap", norm(label(n)))]
        if len(buttons) == 1:
            device.click(*point(buttons[0]))
            wait(1.5)
            return True
        if len(buttons) > 1:
            raise ValueError("Birden fazla gönderinin Comment düğmesi görünüyor; hedef belirsiz olduğu için yorumlar açılmadı.")
        if step < 2:
            device.swipe_ext("up", scale=0.5)
            wait(1)
    return False
