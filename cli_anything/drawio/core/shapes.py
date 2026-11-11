"""Shape (vertex) operations + shared cell helpers.

Maps to GUI actions: drag from sidebar (add), Edit > Delete (remove),
Arrange > geometry panel (move/resize), Format panel (style), double-click (label).
"""

import xml.etree.ElementTree as ET

from .project import Document, DrawioError, new_id, _cell
from . import styles as S


# ── cell helpers ──────────────────────────────────────────────────────────────

def find_cell(doc: Document, page, cell_id: str) -> ET.Element:
    for c in doc.cells(page):
        if c.get("id") == cell_id:
            return c
    raise DrawioError(f"Cell '{cell_id}' not found on page '{page.get('name')}'")


def get_label(el: ET.Element) -> str:
    if el.tag in ("object", "UserObject"):
        return el.get("label", "")
    return el.get("value", "")


def set_label(el: ET.Element, text: str):
    if el.tag in ("object", "UserObject"):
        el.set("label", text)
    else:
        el.set("value", text)


def geometry(el: ET.Element) -> ET.Element | None:
    return _cell(el).find("mxGeometry")


def geom_dict(el: ET.Element) -> dict | None:
    g = geometry(el)
    if g is None:
        return None
    return {k: float(g.get(k, 0)) for k in ("x", "y", "width", "height")}


def is_vertex(el) -> bool:
    return _cell(el).get("vertex") == "1"


def is_edge(el) -> bool:
    return _cell(el).get("edge") == "1"


def is_layer(el) -> bool:
    return _cell(el).get("parent") == "0"


def default_layer(doc: Document, page) -> str:
    for c in doc.cells(page):
        if is_layer(c):
            return c.get("id")
    raise DrawioError("Page has no layer")


def _num(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def cell_summary(el: ET.Element) -> dict:
    c = _cell(el)
    d = {
        "id": el.get("id"),
        "type": "connector" if is_edge(el) else "layer" if is_layer(el) else "shape" if is_vertex(el) else "cell",
        "label": get_label(el),
        "style": c.get("style", ""),
        "parent": c.get("parent"),
    }
    g = geom_dict(el)
    if g and is_vertex(el):
        d["geometry"] = g
    if is_edge(el):
        d["source"] = c.get("source")
        d["target"] = c.get("target")
    if el.tag in ("object", "UserObject"):
        d["data"] = {k: v for k, v in el.attrib.items() if k not in ("id", "label", "placeholders")}
    return d


# ── shapes ────────────────────────────────────────────────────────────────────

def add_shape(doc: Document, page, shape="rectangle", label="", x=0, y=0, width=None,
              height=None, theme=None, style_extra=None, parent=None, cell_id=None) -> dict:
    base, dw, dh = S.shape_style(shape)
    style = S.parse_style(base)
    if theme:
        S.apply_theme(style, theme)
    if style_extra:
        style.update(style_extra)
    w = float(width) if width is not None else dw
    h = float(height) if height is not None else dh
    if w <= 0 or h <= 0:
        raise DrawioError("Width and height must be positive")
    parent = parent or default_layer(doc, page)
    pel = find_cell(doc, page, parent)
    if is_edge(pel):
        raise DrawioError(f"Parent '{parent}' is a connector, not a layer or container")
    cid = cell_id or new_id("s-")
    if any(c.get("id") == cid for c in doc.cells(page)):
        raise DrawioError(f"Cell id '{cid}' already exists")
    root = doc.graph_root(page)
    el = ET.SubElement(root, "mxCell", {
        "id": cid, "value": label, "style": S.format_style(style),
        "vertex": "1", "parent": parent})
    ET.SubElement(el, "mxGeometry", {"x": _num(x), "y": _num(y), "width": _num(w),
                                     "height": _num(h), "as": "geometry"})
    return cell_summary(el)


def list_cells(doc: Document, page, kind="all") -> list:
    out = []
    for c in doc.cells(page):
        if c.get("id") in ("0",):
            continue
        s = cell_summary(c)
        if kind == "all" and s["type"] == "layer":
            continue
        if kind in ("shape", "connector", "layer") and s["type"] != kind:
            continue
        out.append(s)
    return out


def find_by_label(doc: Document, page, text: str, exact=False) -> list:
    t = text.lower()
    res = []
    for c in doc.cells(page):
        lab = get_label(c)
        if (lab == text) if exact else (t in lab.lower()):
            res.append(cell_summary(c))
    return res


def remove_cell(doc: Document, page, cell_id: str) -> dict:
    """Delete a cell, its descendants, and any connector attached to them."""
    if cell_id in ("0",):
        raise DrawioError("Cannot remove the root cell")
    target = find_cell(doc, page, cell_id)
    if is_layer(target) and sum(1 for c in doc.cells(page) if is_layer(c)) == 1:
        raise DrawioError("Cannot remove the only layer")
    doomed = {cell_id}
    changed = True
    cells = doc.cells(page)
    while changed:
        changed = False
        for c in cells:
            cc = _cell(c)
            cid = c.get("id")
            if cid in doomed:
                continue
            if cc.get("parent") in doomed or cc.get("source") in doomed or cc.get("target") in doomed:
                doomed.add(cid)
                changed = True
    root = doc.graph_root(page)
    for c in list(root):
        if c.get("id") in doomed:
            root.remove(c)
    return {"removed": sorted(doomed), "count": len(doomed)}


def move(doc: Document, page, cell_id, x=None, y=None, dx=None, dy=None) -> dict:
    el = find_cell(doc, page, cell_id)
    g = geometry(el)
    if g is None or not is_vertex(el):
        raise DrawioError(f"Cell '{cell_id}' is not a shape with geometry")
    if x is not None:
        g.set("x", _num(x))
    if y is not None:
        g.set("y", _num(y))
    if dx:
        g.set("x", _num(float(g.get("x", 0)) + float(dx)))
    if dy:
        g.set("y", _num(float(g.get("y", 0)) + float(dy)))
    return cell_summary(el)


def resize(doc: Document, page, cell_id, width=None, height=None) -> dict:
    el = find_cell(doc, page, cell_id)
    g = geometry(el)
    if g is None or not is_vertex(el):
        raise DrawioError(f"Cell '{cell_id}' is not a shape with geometry")
    for k, v in (("width", width), ("height", height)):
        if v is not None:
            if float(v) <= 0:
                raise DrawioError(f"{k} must be positive")
            g.set(k, _num(v))
    return cell_summary(el)


def relabel(doc: Document, page, cell_id, text: str) -> dict:
    el = find_cell(doc, page, cell_id)
    set_label(el, text)
    return cell_summary(el)


def set_style(doc: Document, page, cell_id, props: dict | None = None, remove=None,
              theme=None, replace: str | None = None) -> dict:
    el = find_cell(doc, page, cell_id)
    c = _cell(el)
    style = S.parse_style(replace if replace is not None else c.get("style", ""))
    if theme:
        S.apply_theme(style, theme)
    for k, v in (props or {}).items():
        style[k] = v
    for k in remove or []:
        style.pop(k, None)
    c.set("style", S.format_style(style))
    return cell_summary(el)


def set_data(doc: Document, page, cell_id, key: str, value: str | None) -> dict:
    """Custom properties (Edit Data dialog). Converts mxCell to <object> wrapper if needed."""
    if key in ("id", "label", "placeholders"):
        raise DrawioError(f"'{key}' is reserved")
    el = find_cell(doc, page, cell_id)
    if el.tag == "mxCell":
        root = doc.graph_root(page)
        idx = list(root).index(el)
        obj = ET.Element("object", {"label": el.get("value", ""), "id": el.get("id")})
        inner = ET.SubElement(obj, "mxCell", {k: v for k, v in el.attrib.items() if k not in ("id", "value")})
        for child in list(el):
            inner.append(child)
        root.remove(el)
        root.insert(idx, obj)
        el = obj
    if value is None:
        el.attrib.pop(key, None)
    else:
        el.set(key, value)
    return cell_summary(el)


def duplicate(doc: Document, page, cell_id, dx=20, dy=20) -> dict:
    el = find_cell(doc, page, cell_id)
    if not is_vertex(el):
        raise DrawioError("Only shapes can be duplicated")
    copy = ET.fromstring(ET.tostring(el))
    copy.set("id", new_id("s-"))
    root = doc.graph_root(page)
    root.append(copy)
    g = geometry(copy)
    g.set("x", _num(float(g.get("x", 0)) + dx))
    g.set("y", _num(float(g.get("y", 0)) + dy))
    return cell_summary(copy)


def reorder(doc: Document, page, cell_id, where="front") -> dict:
    """Arrange > To Front / To Back (z-order = document order within root)."""
    el = find_cell(doc, page, cell_id)
    if is_layer(el):
        raise DrawioError("Use the layer commands to reorder layers")
    root = doc.graph_root(page)
    root.remove(el)
    if where == "front":
        root.append(el)
    elif where == "back":
        # just after the layer cells so it stays below other shapes
        kids = list(root)
        idx = max(i for i, c in enumerate(kids) if c.get("id") == "0" or is_layer(c)) + 1
        root.insert(idx, el)
    else:
        raise DrawioError("where must be 'front' or 'back'")
    return cell_summary(el)


# ── layers ────────────────────────────────────────────────────────────────────

def add_layer(doc: Document, page, name: str) -> dict:
    root = doc.graph_root(page)
    el = ET.SubElement(root, "mxCell", {"id": new_id("l-"), "value": name, "parent": "0"})
    return cell_summary(el)


def set_layer_visible(doc: Document, page, layer_id: str, visible: bool) -> dict:
    el = find_cell(doc, page, layer_id)
    if not is_layer(el):
        raise DrawioError(f"'{layer_id}' is not a layer")
    c = _cell(el)
    if visible:
        c.attrib.pop("visible", None)
    else:
        c.set("visible", "0")
    return cell_summary(el)
