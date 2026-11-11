"""Connector (edge) operations — GUI: hover a shape and drag its blue arrow to another."""

import xml.etree.ElementTree as ET

from .project import Document, DrawioError, new_id, _cell
from . import styles as S
from .shapes import find_cell, is_edge, is_layer, default_layer, cell_summary


def add_connector(doc: Document, page, source: str, target: str, label="", kind="orthogonal",
                  end_arrow=None, start_arrow=None, dashed=False, color=None, width=None,
                  style_extra=None, cell_id=None) -> dict:
    for ref in (source, target):
        el = find_cell(doc, page, ref)
        if is_edge(el) or is_layer(el):
            raise DrawioError(f"Connector endpoint '{ref}' must be a shape")
    style = S.parse_style(S.edge_style(kind))
    for name, val in (("endArrow", end_arrow), ("startArrow", start_arrow)):
        if val is not None:
            if val not in S.ARROWS:
                raise DrawioError(f"Unknown arrow '{val}'. Choose: {', '.join(S.ARROWS)}")
            style[name] = val
    if dashed:
        style["dashed"] = "1"
    if color:
        style["strokeColor"] = S.validate_color(color)
    if width is not None:
        style["strokeWidth"] = str(width)
    if style_extra:
        style.update(style_extra)
    cid = cell_id or new_id("e-")
    if any(c.get("id") == cid for c in doc.cells(page)):
        raise DrawioError(f"Cell id '{cid}' already exists")
    root = doc.graph_root(page)
    el = ET.SubElement(root, "mxCell", {
        "id": cid, "value": label, "style": S.format_style(style), "edge": "1",
        "parent": default_layer(doc, page), "source": source, "target": target})
    ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
    return cell_summary(el)


def reconnect(doc: Document, page, edge_id: str, source=None, target=None) -> dict:
    el = find_cell(doc, page, edge_id)
    if not is_edge(el):
        raise DrawioError(f"'{edge_id}' is not a connector")
    c = _cell(el)
    for attr, ref in (("source", source), ("target", target)):
        if ref is not None:
            e = find_cell(doc, page, ref)
            if is_edge(e) or is_layer(e):
                raise DrawioError(f"'{ref}' must be a shape")
            c.set(attr, ref)
    return cell_summary(el)


def connectors_of(doc: Document, page, shape_id: str) -> list:
    find_cell(doc, page, shape_id)
    return [cell_summary(c) for c in doc.cells(page)
            if is_edge(c) and shape_id in (_cell(c).get("source"), _cell(c).get("target"))]
