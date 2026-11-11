"""Arrange menu: align, distribute, simple grid/row/column/tree layouts.

These only rewrite mxGeometry in the native file; draw.io renders the result.
"""

from collections import defaultdict, deque

from .project import Document, DrawioError, _cell
from .shapes import find_cell, geometry, is_vertex, is_edge, _num


def _shapes(doc, page, ids):
    if ids:
        els = [find_cell(doc, page, i) for i in ids]
        for e in els:
            if not is_vertex(e):
                raise DrawioError(f"'{e.get('id')}' is not a shape")
        return els
    layer_ids = {c.get("id") for c in doc.cells(page) if _cell(c).get("parent") == "0"}
    return [c for c in doc.cells(page) if is_vertex(c) and _cell(c).get("parent") in layer_ids]


def _g(el):
    g = geometry(el)
    return g, float(g.get("x", 0)), float(g.get("y", 0)), float(g.get("width", 0)), float(g.get("height", 0))


def align(doc: Document, page, ids, mode: str) -> dict:
    els = _shapes(doc, page, ids)
    if len(els) < 2:
        raise DrawioError("Align needs at least 2 shapes")
    gs = [_g(e) for e in els]
    if mode == "left":
        v = min(x for _, x, _, _, _ in gs); [g.set("x", _num(v)) for g, *_ in gs]
    elif mode == "right":
        v = max(x + w for _, x, _, w, _ in gs); [g.set("x", _num(v - w)) for g, x, y, w, h in gs]
    elif mode == "center":
        v = sum(x + w / 2 for _, x, _, w, _ in gs) / len(gs); [g.set("x", _num(v - w / 2)) for g, x, y, w, h in gs]
    elif mode == "top":
        v = min(y for _, _, y, _, _ in gs); [g.set("y", _num(v)) for g, *_ in gs]
    elif mode == "bottom":
        v = max(y + h for _, _, y, _, h in gs); [g.set("y", _num(v - h)) for g, x, y, w, h in gs]
    elif mode == "middle":
        v = sum(y + h / 2 for _, _, y, _, h in gs) / len(gs); [g.set("y", _num(v - h / 2)) for g, x, y, w, h in gs]
    else:
        raise DrawioError("mode must be left|center|right|top|middle|bottom")
    return {"aligned": [e.get("id") for e in els], "mode": mode}


def distribute(doc: Document, page, ids, axis: str) -> dict:
    els = _shapes(doc, page, ids)
    if len(els) < 3:
        raise DrawioError("Distribute needs at least 3 shapes")
    key = 1 if axis == "horizontal" else 2
    if axis not in ("horizontal", "vertical"):
        raise DrawioError("axis must be horizontal|vertical")
    gs = sorted((_g(e) for e in els), key=lambda t: t[key])
    size = 3 if key == 1 else 4
    first, last = gs[0], gs[-1]
    span = last[key] + last[size] - first[key]
    total = sum(t[size] for t in gs)
    gap = (span - total) / (len(gs) - 1)
    pos = first[key]
    for t in gs:
        t[0].set("x" if key == 1 else "y", _num(round(pos, 2)))
        pos += t[size] + gap
    return {"distributed": [e.get("id") for e in els], "axis": axis, "gap": round(gap, 2)}


def grid_layout(doc: Document, page, ids=None, columns=3, spacing=40, x0=40, y0=40) -> dict:
    els = _shapes(doc, page, ids)
    if columns < 1:
        raise DrawioError("columns must be >= 1")
    cw = max((float(geometry(e).get("width", 0)) for e in els), default=0)
    ch = max((float(geometry(e).get("height", 0)) for e in els), default=0)
    for i, e in enumerate(els):
        g = geometry(e)
        r, c = divmod(i, columns)
        g.set("x", _num(x0 + c * (cw + spacing)))
        g.set("y", _num(y0 + r * (ch + spacing)))
    return {"arranged": len(els), "columns": columns}


def line_layout(doc: Document, page, ids=None, direction="row", spacing=40, x0=40, y0=40) -> dict:
    return grid_layout(doc, page, ids, columns=10**6 if direction == "row" else 1,
                       spacing=spacing, x0=x0, y0=y0) | {"direction": direction}


def tree_layout(doc: Document, page, root_id=None, direction="down", level_gap=80, sibling_gap=40,
                x0=40, y0=40) -> dict:
    """Layered tree layout following connectors (like Arrange > Layout > Vertical Tree)."""
    shapes = {e.get("id"): e for e in _shapes(doc, page, None)}
    children = defaultdict(list)
    indeg = defaultdict(int)
    for c in doc.cells(page):
        if is_edge(c):
            s, t = _cell(c).get("source"), _cell(c).get("target")
            if s in shapes and t in shapes and t not in children[s]:
                children[s].append(t)
                indeg[t] += 1
    roots = [root_id] if root_id else [i for i in shapes if indeg[i] == 0]
    if root_id and root_id not in shapes:
        raise DrawioError(f"Root '{root_id}' is not a top-level shape on this page")
    if not roots:
        raise DrawioError("No root found (graph is cyclic); pass --root")
    level = {}
    q = deque((r, 0) for r in roots)
    while q:
        n, d = q.popleft()
        if n in level:
            continue
        level[n] = d
        for ch in children[n]:
            q.append((ch, d + 1))
    by_level = defaultdict(list)
    for n, d in level.items():
        by_level[d].append(n)
    horizontal = direction == "right"
    max_breadth = 0
    for d in by_level:
        max_breadth = max(max_breadth, sum(
            float(geometry(shapes[n]).get("height" if horizontal else "width")) + sibling_gap for n in by_level[d]))
    depth_pos = y0 if not horizontal else x0
    for d in sorted(by_level):
        nodes = by_level[d]
        sizes = [float(geometry(shapes[n]).get("height" if horizontal else "width")) for n in nodes]
        breadth = sum(sizes) + sibling_gap * (len(nodes) - 1)
        pos = (x0 if not horizontal else y0) + (max_breadth - breadth) / 2
        thick = 0
        for n, sz in zip(nodes, sizes):
            g = geometry(shapes[n])
            if horizontal:
                g.set("x", _num(depth_pos)); g.set("y", _num(pos))
                thick = max(thick, float(g.get("width")))
            else:
                g.set("x", _num(pos)); g.set("y", _num(depth_pos))
                thick = max(thick, float(g.get("height")))
            pos += sz + sibling_gap
        depth_pos += thick + level_gap
    return {"arranged": len(level), "levels": len(by_level), "roots": roots, "direction": direction}
