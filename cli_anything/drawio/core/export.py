"""Export pipeline: write the native .drawio, then render with real draw.io Desktop."""

import os
import re
import struct
import tempfile

from . import project as P
from ..utils import drawio_backend as backend

MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "pdf": b"%PDF-",
    "jpg": b"\xff\xd8\xff",
}


def verify_output(path: str, fmt: str) -> dict:
    """Programmatic output verification (magic bytes, dimensions, structure)."""
    with open(path, "rb") as f:
        head = f.read(4096)
    info = {"valid": False}
    if fmt in MAGIC:
        info["valid"] = head.startswith(MAGIC[fmt])
        if fmt == "png" and info["valid"]:
            w, h = struct.unpack(">II", head[16:24])
            info.update(width=w, height=h)
        if fmt == "pdf" and info["valid"]:
            with open(path, "rb") as f:
                data = f.read()
            info["pages"] = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
            if info["pages"] <= 0:
                info["pages"] = data.count(b"/Type/Page") - data.count(b"/Type/Pages")
    elif fmt == "svg":
        txt = head.decode("utf-8", "replace")
        info["valid"] = "<svg" in txt
    elif fmt == "vsdx":
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            info["valid"] = "[Content_Types].xml" in names and any(n.startswith("visio/pages/") for n in names)
            info["pages"] = len([n for n in names if re.fullmatch(r"visio/pages/page\d+\.xml", n)])
        except zipfile.BadZipFile:
            info["valid"] = False
    return info


def render(doc: P.Document, output: str, fmt: str | None = None, page=None, all_pages=False,
           scale=None, width=None, height=None, border=None, transparent=False, crop=False,
           embed_diagram=False, quality=None, overwrite=False) -> dict:
    fmt = (fmt or os.path.splitext(output)[1].lstrip(".") or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if os.path.exists(output) and not overwrite:
        raise P.DrawioError(f"Output exists: {output} (use --overwrite)")
    page_index = None
    if page is not None and not all_pages:
        page_index = doc.page_index(doc.page(page))
    with tempfile.TemporaryDirectory(prefix="cli-drawio-") as td:
        src = os.path.join(td, "diagram.drawio")
        P.save(doc, src)
        res = backend.export(src, output, fmt, page_index=page_index, all_pages=all_pages,
                             scale=scale, width=width, height=height, border=border,
                             transparent=transparent, crop=crop, embed_diagram=embed_diagram,
                             quality=quality)
    res.pop("command", None)
    res["verification"] = verify_output(res["output"], fmt)
    if not res["verification"]["valid"]:
        raise P.DrawioError(f"draw.io produced an invalid {fmt} file: {res['output']}")
    res["page"] = "all" if all_pages else (page_index if page_index is not None else 0)
    return res
