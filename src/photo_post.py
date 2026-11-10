"""Stage one known image and attach it through observed photo-picker controls."""
from pathlib import Path
import re
import shlex
import subprocess
import uuid
import xml.etree.ElementTree as ET
from .comment_reply import label, norm, usable, point, is_edit


def adb(serial, *args):
    result = subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or "ADB işlemi başarısız").strip()[:300])
    return result.stdout


def stage_image(serial, local_path, wait):
    token = uuid.uuid4().hex
    album = "AutoFarm_" + token[:10]
    filename = "autofarm_" + token + Path(local_path).suffix.lower()
    remote = f"/sdcard/Pictures/{album}/{filename}"
    adb(serial, "shell", "mkdir", "-p", f"/sdcard/Pictures/{album}")
    adb(serial, "push", str(local_path), remote)
    adb(serial, "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + remote)
    for _ in range(6):
        result = adb(serial, "shell", "content", "query", "--uri", "content://media/external/images/media",
                     "--projection", "_display_name:bucket_display_name", "--where", shlex.quote(f"_display_name='{filename}'"))
        if f"_display_name={filename}" in result and f"bucket_display_name={album}" in result:
            return {"album": album, "filename": filename, "remote": remote}
        wait(1)
    raise ValueError("Görsel aktarıldı ancak Android galeri indeksinde doğrulanamadı; paylaşım yapılmadı.")


def matches(root, pattern):
    parents = {c: n for n in root.iter() for c in n}
    found = {}
    for node in root.iter("node"):
        if not usable(node) or not re.fullmatch(pattern, norm(label(node))):
            continue
        candidate = node
        while candidate.get("clickable") != "true" and parents.get(candidate) is not None:
            candidate = parents[candidate]
        if candidate.get("clickable") != "true" or not usable(candidate):
            continue
        try:
            found[point(candidate)] = candidate
        except ValueError:
            pass
    return list(found.values())


def click_one(device, nodes, description):
    if len(nodes) != 1:
        raise ValueError(description + " tek ve açık biçimde bulunamadı.")
    device.click(*point(nodes[0]))


def attached(root, filename):
    return any(usable(n) and (re.fullmatch(r"(?:remove|edit) (?:photo|photos|image|images)(?: \d+)?|photo \d+ of \d+|fotoğrafı kaldır|fotoğrafı düzenle", norm(label(n)))
                             or filename in label(n)) for n in root.iter("node"))


def dismiss_optional_dialog(device, root):
    """Only close an optional modal's own close control, never the composer X."""
    for dialog in root.iter("node"):
        if not ("dialog" in dialog.get("class", "").lower() or "dialog" in dialog.get("resource-id", "").lower()):
            continue
        content = " ".join(norm(label(n)) for n in dialog.iter("node") if usable(n))
        if re.search(r"discard|delete|password|log in|permission|privacy|audience|approval|checkpoint|community standards", content):
            continue
        if not re.search(r"try|new feature|boost|promot|add music|reach more|learn more", content):
            continue
        close = matches(dialog, r"close|dismiss|not now|skip|kapat|şimdi değil")
        if len(close) == 1:
            click_one(device, close, "Ek pencerenin kapatma düğmesi")
            return True
    return False


def post_evidence(root, caption, author=""):
    """Require caption, author (when known) and media within one post container."""
    if not caption:
        return False
    parents = {c: n for n in root.iter() for c in n}
    for node in root.iter("node"):
        if is_edit(node) or label(node).strip() != caption.strip():
            continue
        scope = parents.get(node)
        while scope is not None:
            if scope.get("scrollable") == "true" or "RecyclerView" in scope.get("class", ""):
                break
            nodes = [n for n in scope.iter("node") if usable(n)]
            texts = {norm(label(n)) for n in nodes}
            media = any(n.get("class") == "android.widget.ImageView" and
                        (norm(label(n)) in {"photo", "image"} or "photo" in n.get("resource-id", "").lower()) for n in nodes)
            if media and (not author or norm(author) in texts):
                return True
            scope = parents.get(scope)
    return False


def attach_and_publish(device, image, caption, wait, record=lambda stage, xml: None,
                       on_sending=lambda: None, expected_author=""):
    def read(stage):
        xml = device.dump_hierarchy()
        record(stage, xml)
        root = ET.fromstring(xml)
        packages = {n.get("package", "") for n in root.iter("node") if usable(n)}
        if any("permissioncontroller" in p for p in packages):
            raise ValueError("Telefonda fotoğraf erişim izni ekranı açık; izin tercihini telefondan tamamlayın.")
        if stage in {"ready", "publish_review", "after_post"}:
            for _ in range(2):
                if not dismiss_optional_dialog(device, root):
                    break
                wait(1)
                xml = device.dump_hierarchy()
                record(stage + "_after_popup", xml)
                root = ET.fromstring(xml)
        return root

    root = read("target")
    # Enter the observed composer; no fixed center-screen tap.
    write = matches(root, r"write something[.…]*|create (?:a public )?post|what's on your mind[?…]*|bir şeyler yaz[.…]*")
    if write:
        click_one(device, write, "Gönderi oluşturma alanı")
        wait(2)
        root = read("composer")
    photo_pattern = r"gallery|galeri|(?:add )?photos?(?:/videos?| and videos?)?(?: to your post)?|fotoğraf(?:/video)?"
    photo = matches(root, photo_pattern)
    if not photo:
        expand = matches(root, r"add to your post|add photos and videos|gönderine ekle")
        if expand:
            click_one(device, expand, "Gönderiye ekleme menüsü")
            wait(1)
            root = read("add_menu")
            photo = matches(root, photo_pattern)
    click_one(device, photo, "Photo/video düğmesi")
    wait(2)

    album_selected = False
    menu_open = False
    selected = False
    for step in range(8):
        root = read(f"picker_{step}")
        direct = matches(root, r".*" + re.escape(image["filename"].casefold()) + r".*")
        if direct:
            click_one(device, direct, "Seçilen dosyanın galeri öğesi")
            selected = True
            break
        albums = matches(root, re.escape(image["album"].casefold()) + r"(?:[ ,]+(?:\(1\)|1(?: photos?| items?)?))?")
        if albums and not album_selected:
            click_one(device, albums, "Görsele özel albüm")
            album_selected = True
            wait(1)
            continue
        if album_selected:
            # The freshly indexed unique album contains only our staged image.
            if not any(image["album"].casefold() in norm(label(n)) for n in root.iter("node")):
                raise ValueError("Seçilen albümün adı doğrulanamadı; başka fotoğraf seçilmedi.")
            # Facebook exposes each thumbnail three times. Prefer its selection control.
            thumbnails = [n for n in root.iter("node") if usable(n) and
                          n.get("class") == "android.widget.CompoundButton" and
                          re.match(r"photo, item \d+, taken on", norm(label(n)))]
            if not thumbnails:
                unique = {}
                for n in root.iter("node"):
                    if not usable(n):
                        continue
                    desc = norm(label(n))
                    if (re.search(r"thumbnail|icon_thumb", n.get("resource-id", ""), re.I) or
                        re.match(r"photo (?:taken|from)|image (?:taken|from)", desc)):
                        try:
                            unique[point(n)] = n
                        except ValueError:
                            pass
                thumbnails = list(unique.values())
            click_one(device, thumbnails, "Tek görselin küçük resmi")
            selected = True
            break
        if not menu_open:
            for option in (r"albums|albümler", r"(?:select album, )?(?:gallery|galeri)", r"recents|recent|recent photos|son kullanılanlar"):
                controls = matches(root, option)
                if controls:
                    click_one(device, controls, "Galeri albüm seçimi")
                    menu_open = True
                    wait(1)
                    break
            else:
                raise ValueError("Galeri açıldı ancak dosya/albüm seçicisi tanınmadı; rastgele görsel seçilmedi.")
        else:
            device.swipe_ext("up", scale=0.5)
            wait(1)
    if not selected:
        raise ValueError("Seçilen dosya galeride bulunamadı; başka görsel paylaşılmadı.")
    wait(1)
    for step in range(3):
        root = read(f"selection_{step}")
        if attached(root, image["filename"]) and any(is_edit(n) for n in root.iter("node")):
            break
        done = matches(root, r"done|next|add(?: \(1\))?|bitti|ileri|ekle")
        click_one(device, done, "Görsel seçimini tamamlama düğmesi")
        wait(1)
    root = read("attachment")
    if not attached(root, image["filename"]):
        raise ValueError("Görselin gönderiye eklendiği doğrulanamadı; Paylaş düğmesine basılmadı.")
    fields = [n for n in root.iter("node") if usable(n) and is_edit(n)]
    if caption:
        if len(fields) != 1:
            raise ValueError("Tek başlık alanı bulunamadı; paylaşım yapılmadı.")
        edit = device(className=fields[0].get("class"))
        if edit.count != 1:
            raise ValueError("Başlık alanı değişti; paylaşım yapılmadı.")
        edit.set_text(caption)
        wait(0.5)
    root = read("ready")
    # Facebook expands its caption field into a full-screen Add text editor.
    # Finish that sub-editor before requiring the photo preview/Post controls.
    titles = {norm(label(n)) for n in root.iter("node") if usable(n) and not is_edit(n)}
    if caption and "add text" in titles and not attached(root, image["filename"]):
        if not any(is_edit(n) and n.get("text") == caption for n in root.iter("node")):
            raise ValueError("Add text ekranındaki yazı doğrulanamadı; paylaşım yapılmadı.")
        done = matches(root, r"done|bitti|tamam")
        click_one(device, done, "Add text ekranının Done düğmesi")
        wait(1)
        root = read("caption_done")
    if caption and not any(is_edit(n) and n.get("text") == caption for n in root.iter("node")):
        raise ValueError("Başlık metni doğrulanamadı; paylaşım yapılmadı.")
    if not attached(root, image["filename"]):
        raise ValueError("Görsel gönderim öncesinde kayboldu; paylaşım yapılmadı.")
    if device.app_current().get("package") != "com.facebook.katana":
        raise ValueError("Facebook ön planda değil; paylaşım yapılmadı.")
    buttons = matches(root, r"post|publish|share now|paylaş|yayınla")
    if not buttons:
        next_step = matches(root, r"next|ileri")
        if len(next_step) == 1:
            click_one(device, next_step, "Gönderi inceleme adımı")
            wait(1)
            root = read("publish_review")
            buttons = matches(root, r"post|publish|share now|paylaş|yayınla")
    if len(buttons) != 1:
        raise ValueError("Tek Paylaş/Post düğmesi bulunamadı; paylaşım yapılmadı.")
    on_sending()
    click_one(device, buttons, "Paylaş/Post düğmesi")
    # Upload may outlast the optimistic local transition.
    for elapsed in range(2, 62, 2):
        wait(2)
        root = read("after_post")
        labels = {norm(label(n)) for n in root.iter("node") if usable(n)}
        pending = any(re.match(r"posting|uploading|sending|paylaşılıyor|yükleniyor", v) for v in labels)
        if labels & {"try again", "retry", "failed to post"}:
            raise ValueError("Facebook yükleme hatası gösterdi; otomatik tekrar yapılmadı.")
        if any("pending approval" in value or "waiting for approval" in value for value in labels):
            return {"visible": False, "detail": "Gönderi yönetici onayı bekliyor; yayınlanmış sayılmadı."}
        if elapsed >= 16 and not pending and not attached(root, image["filename"]):
            visible = post_evidence(root, caption, expected_author)
            return {"visible": visible, "detail": "Görsel ve yazı gönderi ekranında görüldü; bağımsız sunucu teyidi değildir." if visible else "Gönderim denendi; görsel ve yazı gönderi ekranında birlikte doğrulanamadı."}
    raise ValueError("Görsel yükleme sonucu 60 saniyede doğrulanamadı; otomatik tekrar yapılmadı.")
