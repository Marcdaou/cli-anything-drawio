"""Page operations — GUI: page tabs at the bottom (insert, rename, duplicate, delete, move)."""

import xml.etree.ElementTree as ET

from .project import Document, DrawioError, make_page, new_id, PAGE_SIZES
from . import styles as S


def list_pages(doc: Document) -> list:
    out = []
    for i, p in enumerate(doc.pages):
        m = doc.model(p)
        out.append({"index": i, "id": p.get("id"), "name": p.get("name"),
                    "cells": len(doc.cells(p)) - 2,
                    "page_width": m.get("pageWidth"), "page_height": m.get("pageHeight")})
    return out


def add_page(doc: Document, name: str | None = None, page_size="letter", landscape=False) -> dict:
    if page_size not in PAGE_SIZES:
        raise DrawioError(f"Unknown page size '{page_size}'. Choose: {', '.join(PAGE_SIZES)}")
    w, h = PAGE_SIZES[page_size]
    if landscape:
        w, h = max(w, h), min(w, h)
    name = name or f"Page-{len(doc.pages) + 1}"
    p = make_page(name, w, h)
    doc.root.append(p)
    return {"index": len(doc.pages) - 1, "id": p.get("id"), "name": name}


def remove_page(doc: Document, ref) -> dict:
    if len(doc.pages) <= 1:
        raise DrawioError("Cannot remove the only page")
    p = doc.page(ref)
    idx = doc.page_index(p)
    doc.root.remove(p)
    return {"removed": p.get("name"), "index": idx}


def rename_page(doc: Document, ref, name: str) -> dict:
    if not name.strip():
        raise DrawioError("Page name cannot be empty")
    p = doc.page(ref)
    old = p.get("name")
    p.set("name", name)
    return {"index": doc.page_index(p), "old_name": old, "name": name}


def duplicate_page(doc: Document, ref, name: str | None = None) -> dict:
    p = doc.page(ref)
    copy = ET.fromstring(ET.tostring(p))
    copy.set("id", new_id("p-"))
    copy.set("name", name or f"{p.get('name')} copy")
    idx = doc.page_index(p) + 1
    doc.root.insert(idx, copy)
    return {"index": idx, "id": copy.get("id"), "name": copy.get("name")}


def move_page(doc: Document, ref, to_index: int) -> dict:
    p = doc.page(ref)
    n = len(doc.pages)
    if not 0 <= to_index < n:
        raise DrawioError(f"Target index must be 0..{n - 1}")
    doc.root.remove(p)
    # pages are the only <diagram> children; insert relative to remaining pages
    others = doc.pages
    if to_index >= len(others):
        doc.root.append(p)
    else:
        doc.root.insert(list(doc.root).index(others[to_index]), p)
    return {"name": p.get("name"), "index": doc.page_index(p)}


def set_page_props(doc: Document, ref, background=None, grid=None, page_size=None,
                   landscape=False) -> dict:
    p = doc.page(ref)
    m = doc.model(p)
    if background is not None:
        if background == "none":
            m.attrib.pop("background", None)
        else:
            m.set("background", S.validate_color(background))
    if grid is not None:
        m.set("grid", "1" if grid else "0")
    if page_size is not None:
        if page_size not in PAGE_SIZES:
            raise DrawioError(f"Unknown page size '{page_size}'. Choose: {', '.join(PAGE_SIZES)}")
        w, h = PAGE_SIZES[page_size]
        if landscape:
            w, h = max(w, h), min(w, h)
        m.set("pageWidth", str(w))
        m.set("pageHeight", str(h))
    return {"name": p.get("name"), "background": m.get("background"),
            "grid": m.get("grid"), "page_width": m.get("pageWidth"), "page_height": m.get("pageHeight")}
