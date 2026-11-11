"""Document model for native draw.io (.drawio / mxfile) files.

A .drawio file is XML:

    <mxfile host=...>
      <diagram id=.. name="Page-1">            <- one per page
        <mxGraphModel dx=.. grid=1 ...>          <- either inline...
          <root>
            <mxCell id="0"/>                      <- root cell
            <mxCell id="1" parent="0"/>           <- default layer
            <mxCell id=.. vertex="1" parent="1" style=.. value=..>
              <mxGeometry x y width height as="geometry"/>
            </mxCell>
            <mxCell edge="1" source=.. target=..> ...
          </root>
        </mxGraphModel>
      </diagram>
    </mxfile>

...or the <diagram> text is "compressed": base64(raw-deflate(urlencode(xml))).
We always decompress on load and keep the model inline in memory.
"""

import base64
import hashlib
import os
import re
import uuid
import zlib
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote

HOST = "cli-anything-drawio"
FILE_VERSION = "24.0.0"


class DrawioError(Exception):
    """User-facing error (bad id, missing page, invalid input)."""


# ── compression helpers (mirror draw.io's Graph.compress/decompress) ──────────

def decompress_diagram(data: str) -> str:
    raw = base64.b64decode(data.strip())
    inflated = zlib.decompress(raw, -15).decode("utf-8")
    return unquote(inflated)


def compress_diagram(xml: str) -> str:
    encoded = quote(xml, safe="~()*!.'").encode("utf-8")
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(c.compress(encoded) + c.flush()).decode("ascii")


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


# ── Document ──────────────────────────────────────────────────────────────────

class Document:
    """In-memory mxfile with all pages decompressed."""

    def __init__(self, root: ET.Element):
        if root.tag != "mxfile":
            raise DrawioError(f"Not a draw.io file: root element is <{root.tag}>, expected <mxfile>")
        self.root = root
        for d in self.root.findall("diagram"):
            _ensure_inline(d)

    # pages
    @property
    def pages(self) -> list:
        return self.root.findall("diagram")

    def page(self, ref=None) -> ET.Element:
        """Resolve a page by index (int / numeric str), id or name. None -> first page."""
        pages = self.pages
        if not pages:
            raise DrawioError("Document has no pages")
        if ref is None or ref == "":
            return pages[0]
        if isinstance(ref, int) or (isinstance(ref, str) and re.fullmatch(r"-?\d+", ref)):
            i = int(ref)
            if not -len(pages) <= i < len(pages):
                raise DrawioError(f"Page index {i} out of range (0..{len(pages) - 1})")
            return pages[i]
        for p in pages:
            if p.get("id") == ref:
                return p
        for p in pages:
            if p.get("name") == ref:
                return p
        raise DrawioError(f"Page not found: {ref!r}. Pages: {[p.get('name') for p in pages]}")

    def page_index(self, page: ET.Element) -> int:
        return self.pages.index(page)

    @staticmethod
    def model(page: ET.Element) -> ET.Element:
        return page.find("mxGraphModel")

    @staticmethod
    def graph_root(page: ET.Element) -> ET.Element:
        return page.find("mxGraphModel/root")

    def cells(self, page: ET.Element) -> list:
        return self.graph_root(page).findall("mxCell") + _object_cells(self.graph_root(page))

    def to_xml(self, compressed: bool = False) -> str:
        root = ET.fromstring(ET.tostring(self.root))
        if compressed:
            for d in root.findall("diagram"):
                m = d.find("mxGraphModel")
                if m is not None:
                    xml = ET.tostring(m, encoding="unicode")
                    d.remove(m)
                    d.text = compress_diagram(xml)
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode")

    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(self.to_xml().encode()).hexdigest()


def _object_cells(root: ET.Element) -> list:
    """<object>/<UserObject> wrappers hold an mxCell child; treat wrapper as the cell."""
    return [o for o in root if o.tag in ("object", "UserObject")]


def _ensure_inline(diagram: ET.Element):
    if diagram.find("mxGraphModel") is not None:
        return
    text = (diagram.text or "").strip()
    if not text:
        model = _empty_model()
    else:
        try:
            model = ET.fromstring(decompress_diagram(text))
        except Exception as e:  # pragma: no cover - corrupt input
            raise DrawioError(f"Could not decompress page '{diagram.get('name')}': {e}")
    diagram.text = None
    diagram.append(model)


def _empty_model(width=850, height=1100, grid=True, background=None) -> ET.Element:
    m = ET.Element("mxGraphModel", {
        "dx": "1000", "dy": "1000", "grid": "1" if grid else "0", "gridSize": "10",
        "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1",
        "page": "1", "pageScale": "1", "pageWidth": str(width), "pageHeight": str(height),
        "math": "0", "shadow": "0",
    })
    if background:
        m.set("background", background)
    r = ET.SubElement(m, "root")
    ET.SubElement(r, "mxCell", {"id": "0"})
    ET.SubElement(r, "mxCell", {"id": "1", "parent": "0"})
    return m


def make_page(name: str, width=850, height=1100, grid=True, background=None) -> ET.Element:
    d = ET.Element("diagram", {"id": new_id("p-"), "name": name})
    d.append(_empty_model(width, height, grid, background))
    return d


# ── public API ────────────────────────────────────────────────────────────────

PAGE_SIZES = {
    "letter": (850, 1100), "a4": (827, 1169), "a3": (1169, 1654),
    "legal": (850, 1400), "16:9": (1600, 900), "4:3": (1200, 900), "square": (1000, 1000),
}


def new_document(page_name="Page-1", page_size="letter", landscape=False,
                 grid=True, background=None) -> Document:
    if page_size not in PAGE_SIZES:
        raise DrawioError(f"Unknown page size '{page_size}'. Choose: {', '.join(PAGE_SIZES)}")
    w, h = PAGE_SIZES[page_size]
    if landscape:
        w, h = max(w, h), min(w, h)
    root = ET.Element("mxfile", {"host": HOST, "version": FILE_VERSION, "type": "device"})
    root.append(make_page(page_name, w, h, grid, background))
    return Document(root)


def load(path: str) -> Document:
    if not os.path.isfile(path):
        raise DrawioError(f"File not found: {path}")
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise DrawioError(f"Invalid XML in {path}: {e}")
    root = tree.getroot()
    if root.tag == "mxGraphModel":  # bare model: wrap it
        wrapper = ET.Element("mxfile", {"host": HOST, "version": FILE_VERSION})
        d = ET.SubElement(wrapper, "diagram", {"id": new_id("p-"), "name": "Page-1"})
        d.append(root)
        root = wrapper
    return Document(root)


def from_xml(xml: str) -> Document:
    return Document(ET.fromstring(xml))


def save(doc: Document, path: str, compressed: bool = False) -> dict:
    data = '<?xml version="1.0" encoding="UTF-8"?>\n' + doc.to_xml(compressed=compressed) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)
    return {"path": os.path.abspath(path), "bytes": len(data.encode()), "compressed": compressed}


def info(doc: Document, path: str | None = None) -> dict:
    pages = []
    for i, p in enumerate(doc.pages):
        m = doc.model(p)
        cells = doc.cells(p)
        vertices = [c for c in cells if _cell(c).get("vertex") == "1"]
        edges = [c for c in cells if _cell(c).get("edge") == "1"]
        layers = [c for c in cells if _cell(c).get("parent") == "0"]
        pages.append({
            "index": i, "id": p.get("id"), "name": p.get("name"),
            "page_width": int(float(m.get("pageWidth", 850))),
            "page_height": int(float(m.get("pageHeight", 1100))),
            "background": m.get("background"),
            "shapes": len(vertices), "connectors": len(edges), "layers": len(layers),
        })
    return {"path": os.path.abspath(path) if path else None, "pages": pages,
            "page_count": len(pages),
            "total_shapes": sum(p["shapes"] for p in pages),
            "total_connectors": sum(p["connectors"] for p in pages)}


def _cell(el: ET.Element) -> ET.Element:
    """Return the mxCell carrying vertex/edge/style for a cell or object wrapper."""
    if el.tag == "mxCell":
        return el
    inner = el.find("mxCell")
    return inner if inner is not None else el
