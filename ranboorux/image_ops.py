from __future__ import annotations

from typing import Optional

from PIL import Image


def resize_image(img: Optional[Image.Image], width: int, height: int, cropping: bool = True):
    if img is None:
        return None
    if width <= 0 or height <= 0:
        return img
    if cropping:
        img_aspect = img.width / img.height
        target_aspect = width / height
        if img_aspect > target_aspect:
            new_height = height
            new_width = int(new_height * img_aspect)
        else:
            new_width = width
            new_height = int(new_width / img_aspect)
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - width) / 2
        top = (new_height - height) / 2
        right = (new_width + width) / 2
        bottom = (new_height + height) / 2
        return img_resized.crop((left, top, right, bottom))
    return img.resize((width, height), Image.Resampling.LANCZOS)
