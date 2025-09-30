# llm_doc_pipeline/utils/images.py
import io, base64
from PIL import Image

def _ensure_rgb(im: Image.Image) -> Image.Image:
    return im.convert("RGB") if im.mode != "RGB" else im

def resize_for_vision(im: Image.Image, long_side_px: int) -> Image.Image:
    im = _ensure_rgb(im)
    w, h = im.size
    scale = long_side_px / max(w, h)
    if scale < 1.0:
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    return im

def encode_jpeg_b64(im: Image.Image, quality: int = 70) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return base64.b64encode(buf.getvalue())

def estimate_total_bytes(imgs, long_side_px: int, quality: int) -> int:
    total = 0
    for im in imgs:
        r = resize_for_vision(im, long_side_px)
        b64 = encode_jpeg_b64(r, quality=quality)
        total += len(b64)
    return total

def make_image_parts(imgs, long_side_px: int, quality: int):
    """Returns Chat Completions 'image_url' parts with data URLs."""
    parts = []
    for im in imgs:
        r = resize_for_vision(im, long_side_px)
        b64 = encode_jpeg_b64(r, quality=quality).decode()
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })
    return parts

def batch_images_by_bytes(imgs, long_side_px, quality, max_bytes, max_images):
    batch, out, running = [], [], 0
    for im in imgs:
        # pre-encode to measure
        r = resize_for_vision(im, long_side_px)
        b64 = encode_jpeg_b64(r, quality=quality)
        size = len(b64)
        # if adding this image exceeds limits, flush
        if batch and (running + size > max_bytes or len(batch) >= max_images):
            out.append(batch)
            batch, running = [], 0
        batch.append((r, b64))
        running += size
    if batch:
        out.append(batch)

    # convert batches into image parts
    finalized = []
    for b in out:
        parts = []
        for r, b64 in b:
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64.decode()}"}
            })
        finalized.append(parts)
    return finalized
