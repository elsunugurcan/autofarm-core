"""Shared, side-effect-free feed freeze policy."""
import hashlib
import xml.etree.ElementTree as ET

FREEZE_STEP_LIMIT = 25


def screen_fingerprint(xml):
    if not xml or not xml.strip():
        return None
    try:
        root = ET.fromstring(xml)
        rows = []
        for node in root.iter("node"):
            if node.get("package") == "com.android.systemui":
                continue
            rows.append(tuple(node.get(name, "") for name in
                              ("class", "resource-id", "text", "content-desc", "bounds", "selected", "checked")))
        content = repr(rows) if rows else xml
    except ET.ParseError:
        content = xml
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class FreezeTracker:
    def __init__(self, limit=FREEZE_STEP_LIMIT):
        if limit < 1:
            raise ValueError("Freeze limit must be positive")
        self.limit = limit
        self.reset()

    def reset(self):
        self.previous = None
        self.unchanged_steps = 0

    def observe(self, xml):
        current = screen_fingerprint(xml)
        if current is None:
            self.reset()
            return False
        self.unchanged_steps = self.unchanged_steps + 1 if current == self.previous else 0
        self.previous = current
        if self.unchanged_steps >= self.limit:
            self.reset()
            return True
        return False
