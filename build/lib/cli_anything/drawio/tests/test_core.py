"""Unit tests — synthetic data only, no draw.io Desktop required."""

import json
import os
import struct
import xml.etree.ElementTree as ET
import zlib

import pytest

from cli_anything.drawio.core import project as P
from cli_anything.drawio.core import styles as ST
from cli_anything.drawio.core import shapes as SH
from cli_anything.drawio.core import connectors as CN
from cli_anything.drawio.core import pages as PG
from cli_anything.drawio.core import layout as LY
from cli_anything.drawio.core import session as SS
from cli_anything.drawio.core.export import verify_output


@pytest.fixture
def doc():
    return P.new_document()


@pytest.fixture
def page(doc):
    return doc.page()


def _geom(doc, page, cid):
    return SH.geom_dict(SH.find_cell(doc, page, cid))


# ── project ───────────────────────────────────────────────────────────────────

class TestProject:
    def test_new_document_structure(self, doc):
        assert doc.root.tag == "mxfile"
        root = doc.graph_root(doc.page())
        assert [c.get("id") for c in root] == ["0", "1"]
        assert root[1].get("parent") == "0"

    def test_new_document_page_size_landscape(self):
        d = P.new_document(page_size="a4", landscape=True)
        m = d.model(d.page())
        assert (m.get("pageWidth"), m.get("pageHeight")) == ("1169", "827")

    def test_unknown_page_size(self):
        with pytest.raises(P.DrawioError):
            P.new_document(page_size="huge")

    def test_compress_roundtrip(self):
        xml = '<mxGraphModel><root><mxCell id="0"/><mxCell id="x" value="a &amp; b ü"/></root></mxGraphModel>'
        assert P.decompress_diagram(P.compress_diagram(xml)) == xml

    def test_decompress_drawio_style_payload(self):
        # build the payload exactly as draw.io's Graph.compress does: encodeURIComponent -> deflateRaw -> base64
        from urllib.parse import quote
        import base64
        xml = '<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>'
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        data = base64.b64encode(c.compress(quote(xml).encode()) + c.flush()).decode()
        assert P.decompress_diagram(data) == xml

    def test_save_load_plain(self, doc, tmp_path):
        SH.add_shape(doc, doc.page(), label="Hello", cell_id="h")
        f = tmp_path / "a.drawio"
        P.save(doc, str(f))
        d2 = P.load(str(f))
        assert SH.get_label(SH.find_cell(d2, d2.page(), "h")) == "Hello"

    def test_save_load_compressed(self, doc, tmp_path):
        SH.add_shape(doc, doc.page(), label="Zip", cell_id="z")
        f = tmp_path / "c.drawio"
        P.save(doc, str(f), compressed=True)
        raw = ET.parse(str(f)).getroot()
        assert raw.find("diagram/mxGraphModel") is None
        assert raw.find("diagram").text.strip()
        d2 = P.load(str(f))
        assert SH.get_label(SH.find_cell(d2, d2.page(), "z")) == "Zip"

    def test_load_bare_model(self, tmp_path):
        f = tmp_path / "bare.xml"
        f.write_text('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>')
        d = P.load(str(f))
        assert len(d.pages) == 1

    def test_load_wrong_root(self, tmp_path):
        f = tmp_path / "x.xml"
        f.write_text("<svg/>")
        with pytest.raises(P.DrawioError, match="mxfile"):
            P.load(str(f))

    def test_load_invalid_xml(self, tmp_path):
        f = tmp_path / "bad.drawio"
        f.write_text("<mxfile><diagram>")
        with pytest.raises(P.DrawioError, match="Invalid XML"):
            P.load(str(f))

    def test_load_missing(self):
        with pytest.raises(P.DrawioError, match="not found"):
            P.load("/nonexistent/x.drawio")

    def test_page_lookup(self, doc):
        PG.add_page(doc, "Second")
        assert doc.page(1).get("name") == "Second"
        assert doc.page("1").get("name") == "Second"
        assert doc.page("Second") is doc.page(1)
        assert doc.page(doc.page(1).get("id")) is doc.page(1)
        assert doc.page(-1) is doc.page(1)

    def test_page_lookup_errors(self, doc):
        with pytest.raises(P.DrawioError, match="out of range"):
            doc.page(5)
        with pytest.raises(P.DrawioError, match="not found"):
            doc.page("Nope")

    def test_info_counts(self, doc, page):
        SH.add_shape(doc, page, cell_id="a")
        SH.add_shape(doc, page, cell_id="b")
        CN.add_connector(doc, page, "a", "b")
        i = P.info(doc)
        assert i["total_shapes"] == 2 and i["total_connectors"] == 1 and i["pages"][0]["layers"] == 1


# ── styles ────────────────────────────────────────────────────────────────────

class TestStyles:
    def test_parse_format_roundtrip(self):
        s = "ellipse;whiteSpace=wrap;html=1;fillColor=#fff;"
        assert ST.format_style(ST.parse_style(s)) == s

    def test_parse_bare_tokens_and_equals_in_value(self):
        d = ST.parse_style("text;image=data:image/png,a=b;")
        assert d["text"] is None and d["image"] == "data:image/png,a=b"

    def test_parse_empty(self):
        assert ST.parse_style(None) == {} and ST.format_style({}) == ""

    def test_apply_theme(self):
        d = ST.apply_theme({}, "green")
        assert d == {"fillColor": "#d5e8d4", "strokeColor": "#82b366"}

    def test_unknown_theme_shape_edge(self):
        with pytest.raises(P.DrawioError):
            ST.apply_theme({}, "neon")
        with pytest.raises(P.DrawioError):
            ST.shape_style("blob")
        with pytest.raises(P.DrawioError):
            ST.edge_style("zigzag")

    def test_validate_color(self):
        for c in ("#fff", "#A1b2C3", "none", "default"):
            assert ST.validate_color(c) == c
        for c in ("red", "#12", "#gggggg"):
            with pytest.raises(P.DrawioError):
                ST.validate_color(c)

    def test_parse_kv_pairs(self):
        assert ST.parse_kv_pairs(["dashed=1", "fontColor=#000"]) == {"dashed": "1", "fontColor": "#000"}

    def test_parse_kv_pairs_errors(self):
        with pytest.raises(P.DrawioError):
            ST.parse_kv_pairs(["dashed"])
        with pytest.raises(P.DrawioError):
            ST.parse_kv_pairs(["fillColor=blue"])


# ── shapes ────────────────────────────────────────────────────────────────────

class TestShapes:
    def test_add_defaults(self, doc, page):
        s = SH.add_shape(doc, page, "cylinder", "DB", 10, 20)
        assert s["type"] == "shape" and s["geometry"] == {"x": 10, "y": 20, "width": 60, "height": 80}
        assert "shape=cylinder3" in s["style"] and s["parent"] == "1"

    def test_add_theme_and_extra(self, doc, page):
        s = SH.add_shape(doc, page, theme="red", style_extra={"fontStyle": "1"})
        st = ST.parse_style(s["style"])
        assert st["fillColor"] == "#f8cecc" and st["fontStyle"] == "1"

    def test_add_duplicate_id(self, doc, page):
        SH.add_shape(doc, page, cell_id="x")
        with pytest.raises(P.DrawioError, match="already exists"):
            SH.add_shape(doc, page, cell_id="x")

    def test_add_bad_size(self, doc, page):
        with pytest.raises(P.DrawioError):
            SH.add_shape(doc, page, width=0)

    def test_add_into_container(self, doc, page):
        SH.add_shape(doc, page, "container", cell_id="box")
        s = SH.add_shape(doc, page, parent="box", cell_id="inner")
        assert s["parent"] == "box"

    def test_parent_cannot_be_edge(self, doc, page):
        SH.add_shape(doc, page, cell_id="a"); SH.add_shape(doc, page, cell_id="b")
        CN.add_connector(doc, page, "a", "b", cell_id="e")
        with pytest.raises(P.DrawioError, match="connector"):
            SH.add_shape(doc, page, parent="e")

    def test_list_and_kind_filter(self, doc, page):
        SH.add_shape(doc, page, cell_id="a"); SH.add_shape(doc, page, cell_id="b")
        CN.add_connector(doc, page, "a", "b")
        assert len(SH.list_cells(doc, page)) == 3
        assert len(SH.list_cells(doc, page, "shape")) == 2
        assert len(SH.list_cells(doc, page, "connector")) == 1
        assert len(SH.list_cells(doc, page, "layer")) == 1

    def test_find_by_label(self, doc, page):
        SH.add_shape(doc, page, label="Auth Service")
        SH.add_shape(doc, page, label="Auth")
        assert len(SH.find_by_label(doc, page, "auth")) == 2
        assert len(SH.find_by_label(doc, page, "Auth", exact=True)) == 1

    def test_remove_cascades(self, doc, page):
        SH.add_shape(doc, page, "container", cell_id="box")
        SH.add_shape(doc, page, parent="box", cell_id="inner")
        SH.add_shape(doc, page, cell_id="other")
        CN.add_connector(doc, page, "inner", "other", cell_id="e")
        r = SH.remove_cell(doc, page, "box")
        assert set(r["removed"]) == {"box", "inner", "e"}
        assert [c["id"] for c in SH.list_cells(doc, page)] == ["other"]

    def test_remove_protections(self, doc, page):
        with pytest.raises(P.DrawioError):
            SH.remove_cell(doc, page, "0")
        with pytest.raises(P.DrawioError, match="only layer"):
            SH.remove_cell(doc, page, "1")
        with pytest.raises(P.DrawioError, match="not found"):
            SH.remove_cell(doc, page, "ghost")

    def test_move_abs_and_rel(self, doc, page):
        SH.add_shape(doc, page, x=0, y=0, cell_id="a")
        SH.move(doc, page, "a", x=100)
        SH.move(doc, page, "a", dx=5, dy=-10)
        g = _geom(doc, page, "a")
        assert (g["x"], g["y"]) == (105, -10)

    def test_resize(self, doc, page):
        SH.add_shape(doc, page, cell_id="a")
        SH.resize(doc, page, "a", width=300)
        assert _geom(doc, page, "a")["width"] == 300
        with pytest.raises(P.DrawioError):
            SH.resize(doc, page, "a", height=-1)

    def test_relabel_and_style(self, doc, page):
        SH.add_shape(doc, page, cell_id="a", theme="blue")
        SH.relabel(doc, page, "a", "<b>New</b>")
        s = SH.set_style(doc, page, "a", {"dashed": "1"}, remove=["fillColor"])
        st = ST.parse_style(s["style"])
        assert s["label"] == "<b>New</b>" and st["dashed"] == "1" and "fillColor" not in st
        s = SH.set_style(doc, page, "a", replace="ellipse;")
        assert s["style"] == "ellipse;"

    def test_set_data_converts_to_object(self, doc, page):
        SH.add_shape(doc, page, label="Svc", cell_id="a", x=7)
        s = SH.set_data(doc, page, "a", "owner", "team-x")
        el = SH.find_cell(doc, page, "a")
        assert el.tag == "object" and el.get("label") == "Svc" and s["data"] == {"owner": "team-x"}
        assert SH.geom_dict(el)["x"] == 7 and SH.is_vertex(el)
        SH.set_data(doc, page, "a", "owner", None)
        assert "owner" not in SH.find_cell(doc, page, "a").attrib
        with pytest.raises(P.DrawioError):
            SH.set_data(doc, page, "a", "id", "x")

    def test_duplicate(self, doc, page):
        SH.add_shape(doc, page, label="A", x=10, y=10, cell_id="a")
        d = SH.duplicate(doc, page, "a")
        assert d["id"] != "a" and d["label"] == "A" and d["geometry"]["x"] == 30

    def test_reorder(self, doc, page):
        for i in "abc":
            SH.add_shape(doc, page, cell_id=i)
        SH.reorder(doc, page, "a", "front")
        SH.reorder(doc, page, "c", "back")
        assert [c.get("id") for c in doc.graph_root(page)] == ["0", "1", "c", "b", "a"]

    def test_layers(self, doc, page):
        l = SH.add_layer(doc, page, "Annotations")
        assert l["type"] == "layer"
        SH.set_layer_visible(doc, page, l["id"], False)
        assert SH.find_cell(doc, page, l["id"]).get("visible") == "0"
        SH.set_layer_visible(doc, page, l["id"], True)
        assert SH.find_cell(doc, page, l["id"]).get("visible") is None
        s = SH.add_shape(doc, page, parent=l["id"])
        assert s["parent"] == l["id"]


# ── connectors ────────────────────────────────────────────────────────────────

class TestConnectors:
    def test_add(self, doc, page):
        SH.add_shape(doc, page, cell_id="a"); SH.add_shape(doc, page, cell_id="b")
        e = CN.add_connector(doc, page, "a", "b", "calls", "rounded", end_arrow="open",
                             dashed=True, color="#ff0000", width=2)
        st = ST.parse_style(e["style"])
        assert (e["source"], e["target"], e["label"]) == ("a", "b", "calls")
        assert st["endArrow"] == "open" and st["dashed"] == "1" and st["strokeWidth"] == "2"
        geo = SH.find_cell(doc, page, e["id"]).find("mxGeometry")
        assert geo.get("relative") == "1"

    def test_bad_endpoints(self, doc, page):
        SH.add_shape(doc, page, cell_id="a")
        with pytest.raises(P.DrawioError):
            CN.add_connector(doc, page, "a", "missing")
        with pytest.raises(P.DrawioError):
            CN.add_connector(doc, page, "a", "1")

    def test_bad_arrow(self, doc, page):
        SH.add_shape(doc, page, cell_id="a"); SH.add_shape(doc, page, cell_id="b")
        with pytest.raises(P.DrawioError, match="arrow"):
            CN.add_connector(doc, page, "a", "b", end_arrow="laser")

    def test_reconnect(self, doc, page):
        for i in "abc":
            SH.add_shape(doc, page, cell_id=i)
        CN.add_connector(doc, page, "a", "b", cell_id="e")
        r = CN.reconnect(doc, page, "e", target="c")
        assert r["target"] == "c"
        with pytest.raises(P.DrawioError):
            CN.reconnect(doc, page, "a", target="c")

    def test_connectors_of(self, doc, page):
        for i in "abc":
            SH.add_shape(doc, page, cell_id=i)
        CN.add_connector(doc, page, "a", "b"); CN.add_connector(doc, page, "c", "a"); CN.add_connector(doc, page, "b", "c")
        assert len(CN.connectors_of(doc, page, "a")) == 2


# ── pages ─────────────────────────────────────────────────────────────────────

class TestPages:
    def test_add_list(self, doc):
        PG.add_page(doc, "Two", "16:9")
        ls = PG.list_pages(doc)
        assert [p["name"] for p in ls] == ["Page-1", "Two"] and ls[1]["page_width"] == "1600"

    def test_remove(self, doc):
        with pytest.raises(P.DrawioError, match="only page"):
            PG.remove_page(doc, 0)
        PG.add_page(doc, "B")
        PG.remove_page(doc, "Page-1")
        assert [p.get("name") for p in doc.pages] == ["B"]

    def test_rename(self, doc):
        PG.rename_page(doc, 0, "Overview")
        assert doc.page(0).get("name") == "Overview"
        with pytest.raises(P.DrawioError):
            PG.rename_page(doc, 0, "  ")

    def test_duplicate_is_deep(self, doc):
        SH.add_shape(doc, doc.page(0), cell_id="a", label="orig")
        PG.duplicate_page(doc, 0)
        SH.relabel(doc, doc.page(1), "a", "changed")
        assert SH.get_label(SH.find_cell(doc, doc.page(0), "a")) == "orig"
        assert doc.page(0).get("id") != doc.page(1).get("id")

    def test_move(self, doc):
        PG.add_page(doc, "B"); PG.add_page(doc, "C")
        PG.move_page(doc, "C", 0)
        assert [p.get("name") for p in doc.pages] == ["C", "Page-1", "B"]
        PG.move_page(doc, "C", 2)
        assert [p.get("name") for p in doc.pages] == ["Page-1", "B", "C"]
        with pytest.raises(P.DrawioError):
            PG.move_page(doc, "C", 9)

    def test_set_props(self, doc):
        r = PG.set_page_props(doc, 0, background="#eeeeee", grid=False, page_size="a4")
        assert r["background"] == "#eeeeee" and r["grid"] == "0" and r["page_width"] == "827"
        r = PG.set_page_props(doc, 0, background="none")
        assert r["background"] is None


# ── layout ────────────────────────────────────────────────────────────────────

class TestLayout:
    def _three(self, doc, page):
        SH.add_shape(doc, page, x=0, y=0, width=100, height=50, cell_id="a")
        SH.add_shape(doc, page, x=50, y=200, width=60, height=40, cell_id="b")
        SH.add_shape(doc, page, x=500, y=90, width=80, height=80, cell_id="c")

    def test_align(self, doc, page):
        self._three(doc, page)
        LY.align(doc, page, ["a", "b", "c"], "left")
        assert {_geom(doc, page, i)["x"] for i in "abc"} == {0}
        LY.align(doc, page, [], "bottom")
        assert {_geom(doc, page, i)["y"] + _geom(doc, page, i)["height"] for i in "abc"} == {240}
        LY.align(doc, page, ["a", "b"], "center")
        ga, gb = _geom(doc, page, "a"), _geom(doc, page, "b")
        assert ga["x"] + ga["width"] / 2 == gb["x"] + gb["width"] / 2

    def test_align_errors(self, doc, page):
        SH.add_shape(doc, page, cell_id="a")
        with pytest.raises(P.DrawioError):
            LY.align(doc, page, ["a"], "left")
        SH.add_shape(doc, page, cell_id="b")
        with pytest.raises(P.DrawioError):
            LY.align(doc, page, ["a", "b"], "diagonal")

    def test_distribute(self, doc, page):
        self._three(doc, page)
        r = LY.distribute(doc, page, ["a", "b", "c"], "horizontal")
        xs = sorted((_geom(doc, page, i)["x"], _geom(doc, page, i)["width"]) for i in "abc")
        gaps = [xs[i + 1][0] - (xs[i][0] + xs[i][1]) for i in range(2)]
        assert abs(gaps[0] - gaps[1]) < 0.01 and abs(gaps[0] - r["gap"]) < 0.01

    def test_grid_row_column(self, doc, page):
        for i in range(5):
            SH.add_shape(doc, page, width=100, height=50, cell_id=f"n{i}")
        LY.grid_layout(doc, page, columns=2, spacing=10, x0=0, y0=0)
        assert (_geom(doc, page, "n3")["x"], _geom(doc, page, "n3")["y"]) == (110, 60)
        LY.line_layout(doc, page, direction="row", spacing=10, x0=0, y0=0)
        assert {_geom(doc, page, f"n{i}")["y"] for i in range(5)} == {0}
        LY.line_layout(doc, page, direction="column", spacing=10, x0=0, y0=0)
        assert {_geom(doc, page, f"n{i}")["x"] for i in range(5)} == {0}

    def test_tree(self, doc, page):
        for i in "rabc":
            SH.add_shape(doc, page, width=100, height=40, cell_id=i)
        for t in "ab":
            CN.add_connector(doc, page, "r", t)
        CN.add_connector(doc, page, "a", "c")
        res = LY.tree_layout(doc, page, level_gap=50)
        assert res["levels"] == 3 and res["roots"] == ["r"]
        ys = {i: _geom(doc, page, i)["y"] for i in "rabc"}
        assert ys["r"] < ys["a"] == ys["b"] < ys["c"]
        LY.tree_layout(doc, page, direction="right")
        assert _geom(doc, page, "r")["x"] < _geom(doc, page, "a")["x"]

    def test_tree_cycle_needs_root(self, doc, page):
        SH.add_shape(doc, page, cell_id="a"); SH.add_shape(doc, page, cell_id="b")
        CN.add_connector(doc, page, "a", "b"); CN.add_connector(doc, page, "b", "a")
        with pytest.raises(P.DrawioError, match="cyclic"):
            LY.tree_layout(doc, page)
        assert LY.tree_layout(doc, page, root_id="a")["levels"] == 2


# ── session ───────────────────────────────────────────────────────────────────

class TestSession:
    def test_undo_redo(self, doc):
        s = SS.Session(); s.set_project(doc, None)
        s.snapshot("add"); SH.add_shape(s.doc, s.page(), cell_id="a")
        s.snapshot("move"); SH.move(s.doc, s.page(), "a", x=99)
        assert s.undo() == "move" and _geom(s.doc, s.page(), "a")["x"] == 0
        assert s.undo() == "add" and SH.list_cells(s.doc, s.page()) == []
        with pytest.raises(P.DrawioError):
            s.undo()
        s.redo(); s.redo()
        assert _geom(s.doc, s.page(), "a")["x"] == 99
        with pytest.raises(P.DrawioError):
            s.redo()

    def test_new_snapshot_clears_redo(self, doc):
        s = SS.Session(); s.set_project(doc, None)
        s.snapshot("x"); s.undo()
        s.snapshot("y")
        assert s.history() == {"undo": ["y"], "redo": []}

    def test_history_cap(self, doc):
        s = SS.Session(); s.set_project(doc, None)
        for i in range(SS.MAX_HISTORY + 10):
            s.snapshot(f"op{i}")
        assert len(s.undo_stack) == SS.MAX_HISTORY

    def test_save_and_sidecar_reload(self, doc, tmp_path):
        f = str(tmp_path / "d.drawio")
        s = SS.Session(); s.set_project(doc, f)
        s.snapshot("add"); SH.add_shape(s.doc, s.page(), cell_id="a")
        s.save_session()
        assert os.path.isfile(SS.sidecar_path(f)) and not s._modified
        s2 = SS.Session(); s2.open(f)
        assert s2.history()["undo"] == ["add"]
        s2.undo()
        assert SH.list_cells(s2.doc, s2.page()) == []

    def test_stale_sidecar_ignored(self, doc, tmp_path):
        f = str(tmp_path / "d.drawio")
        s = SS.Session(); s.set_project(doc, f)
        s.snapshot("add"); SH.add_shape(s.doc, s.page(), cell_id="a")
        s.save_session()
        d = P.load(f); SH.add_shape(d, d.page(), cell_id="gui-edit"); P.save(d, f)  # edited elsewhere
        s2 = SS.Session(); s2.open(f)
        assert s2.history()["undo"] == []

    def test_locked_save_json_and_require(self, tmp_path):
        p = tmp_path / "sub" / "x.json"
        SS._locked_save_json(str(p), {"a": 1})
        SS._locked_save_json(str(p), {"b": 2})
        assert json.loads(p.read_text()) == {"b": 2}
        s = SS.Session()
        with pytest.raises(P.DrawioError, match="No diagram open"):
            s.require()
        s.set_project(P.new_document(), None)
        with pytest.raises(P.DrawioError, match="No output path"):
            s.save_session()


# ── export verification ───────────────────────────────────────────────────────

class TestVerify:
    def test_png_pdf_svg(self, tmp_path):
        png = tmp_path / "a.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 320, 200) + b"\0" * 20)
        v = verify_output(str(png), "png")
        assert v["valid"] and (v["width"], v["height"]) == (320, 200)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4\n/Type /Pages\n/Type /Page\n/Type /Page\n")
        assert verify_output(str(pdf), "pdf") == {"valid": True, "pages": 2}
        svg = tmp_path / "a.svg"
        svg.write_text('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>')
        assert verify_output(str(svg), "svg")["valid"]

    def test_invalid(self, tmp_path):
        f = tmp_path / "x.png"
        f.write_bytes(b"%PDF-1.4")
        assert not verify_output(str(f), "png")["valid"]
        z = tmp_path / "x.vsdx"
        z.write_bytes(b"not a zip")
        assert not verify_output(str(z), "vsdx")["valid"]
