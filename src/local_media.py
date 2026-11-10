"""Validate selected images and make a stable, Android-compatible upload copy."""
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


def validate_image(path):
    image_path = Path(path).expanduser().resolve()
    if not image_path.is_file():
        raise ValueError("Lütfen bilgisayarınızdan bir görsel seçin.")
    try:
        with Image.open(image_path) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("JPG, PNG veya WEBP biçiminde bir görsel seçin.")
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Görsel okunamadı. Başka bir JPG, PNG veya WEBP dosyası seçin.") from exc
    return os.fspath(image_path)


def prepare_image(path, output_dir="downloads"):
    image_path = validate_image(path)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"upload_{uuid.uuid4().hex}.jpg"
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        background.save(target, "JPEG", quality=95)
    return os.fspath(target)
