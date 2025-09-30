
from __future__ import annotations
import os, io, base64
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from tqdm import tqdm
import pandas as pd

# Optional deps are imported lazily
def _import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None

def scan_folder(path: str, allowed_exts: List[str], recursive: bool = True) -> List[str]:
    out = []
    for root, dirs, files in os.walk(path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in allowed_exts:
                out.append(os.path.join(root, f))
        if not recursive:
            break
    return sorted(out)

def detect_doc_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]: return "excel"
    if ext in [".pdf"]: return "pdf"
    if ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]: return "image"
    if ext in [".docx"]: return "word"
    if ext in [".html", ".htm"]: return "html"
    if ext in [".txt"]: return "text"
    if ext in [".csv"]: return "csv"
    if ext in [".pptx"]: return "powerpoint"
    return "other"

# -------------------- PDF --------------------

def pdf_text_preview(path: str, max_chars: int = 4000) -> str:
    pypdf = _import("pypdf")
    if not pypdf:
        return ""
    txt = []
    try:
        reader = pypdf.PdfReader(path)
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
                if t:
                    txt.append(t)
                if sum(len(x) for x in txt) > max_chars: break
            except Exception:
                continue
    except Exception:
        return ""
    s = "".join(txt)
    return s[:max_chars]

def pdf_page_count(path: str) -> int:
    pypdf = _import("pypdf")
    if not pypdf:
        return 0
    try:
        reader = pypdf.PdfReader(path)
        return len(reader.pages)
    except Exception:
        return 0

def render_pdf_pages(path: str, dpi: int = 180) -> List[bytes]:
    # Prefer PyMuPDF for reliability
    fitz = _import("fitz")
    if fitz:
        try:
            doc = fitz.open(path)
            imgs = []
            for p in tqdm(doc, desc="Rendering PDF pages"):
                pix = p.get_pixmap(dpi=dpi)
                imgs.append(pix.tobytes("png"))
            return imgs
        except Exception:
            pass
    # Fallback: pdf2image
    pdf2image = _import("pdf2image")
    if pdf2image:
        try:
            pil_images = pdf2image.convert_from_path(path, dpi=dpi)
            out = []
            for im in tqdm(pil_images, desc="Rendering PDF pages"):
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                out.append(buf.getvalue())
            return out
        except Exception:
            pass
    # No renderer available
    return []

# -------------------- Images -----------------
def load_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

# -------------------- Text / Word / HTML / Powerpoint -----
def text_preview(path: str, max_chars: int = 4000) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".txt"]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:max_chars]
        except Exception:
            return ""
    if ext == ".docx":
        docx = _import("docx")
        if not docx:
            return ""
        try:
            doc = docx.Document(path)
            s = "\n".join(p.text for p in doc.paragraphs)
            return s[:max_chars]
        except Exception:
            return ""
    if ext in [".html", ".htm"]:
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except Exception:
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(" ")[:max_chars]
        except Exception:
            return ""
    if ext == ".pptx":
        return powerpoint_text_preview(path, max_chars)
    return ""

def powerpoint_text_preview(path: str, max_chars: int = 4000) -> str:
    pptx_parser = _import("pptx")
    if not pptx_parser:
        return ""
    try:
        prs = pptx_parser.Presentation(path)
        text_runs = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text_runs.append(shape.text)
        return "\n".join(text_runs)[:max_chars]
    except Exception:
        return ""

def render_powerpoint_pages(path: str, dpi: int = 180) -> List[bytes]:
    # This will require a more complex setup, potentially involving a headless browser or
    # converting to PDF first and then rendering as images. For simplicity, we'll
    # leave this as a placeholder for now and focus on text extraction.
    # A full implementation would involve libraries like 'unoconv' or 'libreoffice'
    # which are external dependencies.
    # For now, we'll return an empty list and rely on text extraction.
    return []

# -------------------- CSV --------------------
def csv_overview(path: str, sample_rows: int = 50) -> Dict[str, List[List[str]]]:
    import pandas as pd
    df = pd.read_csv(path, nrows=sample_rows, header=None)
    grid = [[str(v) for v in row] for row in df.values.tolist()]
    return {"default_sheet": grid}

def csv_load_all(path: str) -> Dict[str, "pd.DataFrame"]:
    import pandas as pd
    df = pd.read_csv(path)
    return {"default_sheet": df}

# -------------------- Excel ------------------
def excel_overview(path: str, sample_rows: int = 50) -> Dict[str, List[List[str]]]:
    # import pandas as pd  # required for excel path
    xls = pd.ExcelFile(path)
    overview = {}
    for sheet in xls.sheet_names:
        try:
            df = xls.parse(sheet, nrows=sample_rows, header=None)
            # Convert to string grid (to avoid dtype noise)
            grid = [[str(v) for v in row] for row in df.values.tolist()]
            overview[sheet] = grid
        except Exception:
            overview[sheet] = []
    return overview

def excel_load_all(path: str) -> Dict[str, "pd.DataFrame"]:
    # import pandas as pd
    xls = pd.ExcelFile(path)
    dfs = {sheet: xls.parse(sheet) for sheet in xls.sheet_names}
    return dfs
