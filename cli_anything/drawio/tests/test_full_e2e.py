"""E2E tests: native files, REAL draw.io Desktop rendering, and the installed CLI.

draw.io Desktop is a hard dependency: these tests FAIL (not skip) without it.
Run:  CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/drawio/tests/ -v -s
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib

import pytest

from cli_anything.drawio.core import project as P
from cli_anything.drawio.core import shapes as SH
from cli_anything.drawio.core import connectors as CN
from cli_anything.drawio.core import pages as PG
from cli_anything.drawio.core import layout as LY
from cli_anything.drawio.core import export as EX
from cli_anything.drawio.core import preview as PV
from cli_anything.drawio.core.session import Session
from cli_anything.drawio.utils import drawio_backend as backend


def _resolve_cli(name):
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = name.replace("cli-anything-", "cli_anything.") + "." + name.split("-")[-1] + "_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="drawio-e2e-")
    yield d
    if not os.environ.get("KEEP_ARTIFACTS"):
        shutil.rmtree(d, ignore_errors=True)


def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", head[16:24])


def _png_has_alpha_pixels(path):
    """Decode PNG (RGBA 8-bit, non-interlaced) and report whether any pixel is transparent."""
    with open(path, "rb") as f:
        data = f.read()
    pos, idat, w, h, ctype = 8, b"", 0, 0, 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8]); ctype = body[9]
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    if ctype != 6:
        return False
    raw = zlib.decompress(idat)
    stride = w * 4
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]; c = prev[x - 4] if x >= 4 else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        if any(line[x] < 255 for x in range(3, stride, 4)):
            return True
        prev = line
    return False


def _architecture(doc):
    pg = doc.page()
    specs = [("client", "Web Client", "rounded", "blue"), ("gw", "API Gateway", "hexagon", "purple"),
             ("auth", "Auth Service", "rectangle", "green"), ("orders", "Order Service", "rectangle", "green"),
             ("queue", "Event Queue", "process", "orange"), ("pg", "Postgres", "cylinder", "yellow"),
             ("redis", "Redis Cache", "cylinder", "red")]
    for cid, label, shape, theme in specs:
        SH.add_shape(doc, pg, shape, label, theme=theme, cell_id=cid)
    for s, t, lab, kw in [("client", "gw", "HTTPS", {}), ("gw", "auth", "verify", {}),
                          ("gw", "orders", "REST", {}), ("orders", "queue", "publish", {"dashed": True}),
                          ("auth", "redis", "sessions", {}), ("orders", "pg", "SQL", {}),
                          ("queue", "pg", "projection", {"dashed": True})]:
        CN.add_connector(doc, pg, s, t, lab, **kw)
    LY.tree_layout(doc, pg, root_id="client")
    return doc


# ── native file structure ─────────────────────────────────────────────────────

class TestNativeFile:
    def test_structure_integrity(self, tmp_dir):
        doc = _architecture(P.new_document())
        f = os.path.join(tmp_dir, "arch.drawio")
        P.save(doc, f)
        root = ET.parse(f).getroot()
        assert root.tag == "mxfile"
        cells = root.findall("diagram/mxGraphModel/root/mxCell")
        ids = [c.get("id") for c in cells]
        assert ids[:2] == ["0", "1"] and len(ids) == len(set(ids))
        vertices = {c.get("id") for c in cells if c.get("vertex") == "1"}
        for e in (c for c in cells if c.get("edge") == "1"):
            assert e.get("source") in vertices and e.get("target") in vertices
            assert e.find("mxGeometry").get("relative") == "1"
        for c in cells:
            if c.get("vertex") == "1":
                g = c.find("mxGeometry")
                assert g.get("as") == "geometry" and float(g.get("width")) > 0
        print(f"\n  DRAWIO: {f}")

    def test_compressed_roundtrip(self, tmp_dir):
        doc = _architecture(P.new_document())
        f = os.path.join(tmp_dir, "c.drawio")
        P.save(doc, f, compressed=True)
        d2 = P.load(f)
        assert P.info(d2)["total_shapes"] == 7 and d2.to_xml() == doc.to_xml()


# ── real draw.io backend ──────────────────────────────────────────────────────

class TestBackend:
    def test_drawio_installed(self):
        exe = backend.find_drawio()
        assert os.access(exe, os.X_OK)
        print(f"\n  draw.io: {exe} v{backend.version()}")

    def test_png(self, tmp_dir):
        doc = _architecture(P.new_document())
        out = os.path.join(tmp_dir, "arch.png")
        r = EX.render(doc, out)
        w, h = _png_size(out)
        assert r["method"] == "drawio-desktop-headless" and w > 200 and h > 200 and r["file_size"] > 2000
        print(f"\n  PNG: {out} ({r['file_size']:,} bytes, {w}x{h})")

    def test_png_scale_doubles(self, tmp_dir):
        doc = _architecture(P.new_document())
        a = EX.render(doc, os.path.join(tmp_dir, "1x.png"))
        b = EX.render(doc, os.path.join(tmp_dir, "2x.png"), scale=2)
        w1, _ = _png_size(a["output"]); w2, _ = _png_size(b["output"])
        assert 1.8 < w2 / w1 < 2.2

    def test_png_transparent(self, tmp_dir):
        doc = _architecture(P.new_document())
        opaque = EX.render(doc, os.path.join(tmp_dir, "o.png"))
        clear = EX.render(doc, os.path.join(tmp_dir, "t.png"), transparent=True)
        assert not _png_has_alpha_pixels(opaque["output"])
        assert _png_has_alpha_pixels(clear["output"])

    def test_png_embed_diagram(self, tmp_dir):
        doc = _architecture(P.new_document())
        r = EX.render(doc, os.path.join(tmp_dir, "e.png"), embed_diagram=True)
        plain = EX.render(doc, os.path.join(tmp_dir, "p.png"))
        with open(r["output"], "rb") as f:
            data = f.read()
        # draw.io stores the diagram in a compressed zTXt chunk keyed "mxGraphModel"
        assert b"zTXtmxGraphModel" in data and r["file_size"] > plain["file_size"]

    def test_svg_contains_labels(self, tmp_dir):
        doc = _architecture(P.new_document())
        out = os.path.join(tmp_dir, "arch.svg")
        EX.render(doc, out)
        txt = open(out, encoding="utf-8").read()
        assert "<svg" in txt
        for label in ("Web Client", "API Gateway", "Postgres", "Redis Cache", "publish"):
            assert label in txt, label
        print(f"\n  SVG: {out}")

    def test_pdf_single_and_all_pages(self, tmp_dir):
        doc = _architecture(P.new_document())
        for n in ("Detail A", "Detail B"):
            PG.add_page(doc, n)
            SH.add_shape(doc, doc.page(n), label=n)
        one = EX.render(doc, os.path.join(tmp_dir, "one.pdf"))
        allp = EX.render(doc, os.path.join(tmp_dir, "all.pdf"), all_pages=True)
        assert one["verification"]["pages"] == 1
        assert allp["verification"]["pages"] == 3
        print(f"\n  PDF: {allp['output']} ({allp['file_size']:,} bytes, 3 pages)")

    def test_jpg(self, tmp_dir):
        r = EX.render(_architecture(P.new_document()), os.path.join(tmp_dir, "a.jpg"), quality=80)
        assert r["verification"]["valid"] and r["format"] == "jpg"

    def test_vsdx(self, tmp_dir):
        r = EX.render(_architecture(P.new_document()), os.path.join(tmp_dir, "a.vsdx"))
        assert r["verification"]["valid"] and r["verification"]["pages"] == 1
        print(f"\n  VSDX: {r['output']}")

    def test_page_selection_differs(self, tmp_dir):
        doc = P.new_document()
        SH.add_shape(doc, doc.page(0), label="small", width=50, height=50)
        PG.add_page(doc, "Big")
        SH.add_shape(doc, doc.page(1), label="wide", width=600, height=100)
        a = EX.render(doc, os.path.join(tmp_dir, "p0.png"), page=0)
        b = EX.render(doc, os.path.join(tmp_dir, "p1.png"), page="Big")
        assert _png_size(a["output"])[0] < _png_size(b["output"])[0]
        assert b["page"] == 1

    def test_errors(self, tmp_dir):
        doc = P.new_document()
        with pytest.raises(P.DrawioError):
            EX.render(doc, os.path.join(tmp_dir, "x.png"), page=7)
        with pytest.raises(ValueError):
            EX.render(doc, os.path.join(tmp_dir, "x.png"), all_pages=True)
        with pytest.raises(ValueError):
            EX.render(doc, os.path.join(tmp_dir, "x.bmp"))
        out = os.path.join(tmp_dir, "exists.png")
        open(out, "w").close()
        with pytest.raises(P.DrawioError, match="exists"):
            EX.render(doc, out)

    def test_extension_mismatch_respects_format(self, tmp_dir):
        # draw.io would derive format from the extension; we force the requested format
        r = EX.render(_architecture(P.new_document()), os.path.join(tmp_dir, "diagram.out"), fmt="png")
        _png_size(r["output"])


# ── workflows ─────────────────────────────────────────────────────────────────

class TestWorkflows:
    def test_flowchart_pdf(self, tmp_dir):
        doc = P.new_document()
        pg = doc.page()
        SH.add_shape(doc, pg, "ellipse", "Start", cell_id="start", theme="green")
        SH.add_shape(doc, pg, "rectangle", "Receive order", cell_id="recv")
        SH.add_shape(doc, pg, "diamond", "In stock?", cell_id="dec", width=100, height=100, theme="yellow")
        SH.add_shape(doc, pg, "rectangle", "Ship", cell_id="ship", theme="blue")
        SH.add_shape(doc, pg, "rectangle", "Back-order", cell_id="bo", theme="red")
        SH.add_shape(doc, pg, "ellipse", "End", cell_id="end")
        CN.add_connector(doc, pg, "start", "recv"); CN.add_connector(doc, pg, "recv", "dec")
        CN.add_connector(doc, pg, "dec", "ship", "yes"); CN.add_connector(doc, pg, "dec", "bo", "no")
        CN.add_connector(doc, pg, "ship", "end"); CN.add_connector(doc, pg, "bo", "end")
        LY.tree_layout(doc, pg, root_id="start")
        pdf = EX.render(doc, os.path.join(tmp_dir, "flow.pdf"))
        svg = EX.render(doc, os.path.join(tmp_dir, "flow.svg"))
        txt = open(svg["output"], encoding="utf-8").read()
        assert pdf["verification"]["pages"] == 1 and "yes" in txt and "Back-order" in txt
        print(f"\n  PDF: {pdf['output']}")

    def test_multipage_spec(self, tmp_dir):
        doc = P.new_document(page_name="Overview")
        PG.add_page(doc, "Details")
        PG.duplicate_page(doc, "Details", "Appendix")
        PG.move_page(doc, "Appendix", 0)
        PG.rename_page(doc, "Appendix", "Cover")
        for p in doc.pages:
            SH.add_shape(doc, p, "rounded", p.get("name"), theme="gray")
        assert [p.get("name") for p in doc.pages] == ["Cover", "Overview", "Details"]
        r = EX.render(doc, os.path.join(tmp_dir, "spec.pdf"), all_pages=True)
        assert r["verification"]["pages"] == 3

    def test_edit_gui_compressed_file(self, tmp_dir):
        """A compressed file as saved by the draw.io GUI (pages are deflate+base64)."""
        src = P.new_document()
        SH.add_shape(src, src.page(), "rectangle", "Legacy", cell_id="old")
        f = os.path.join(tmp_dir, "legacy.drawio")
        P.save(src, f, compressed=True)
        s = Session(); s.open(f)
        s.snapshot("edit")
        SH.relabel(s.doc, s.page(), "old", "Modernised")
        SH.set_style(s.doc, s.page(), "old", {"fillColor": "#dae8fc"})
        SH.set_data(s.doc, s.page(), "old", "owner", "platform")
        s.save_session()
        d = P.load(f)
        el = SH.find_cell(d, d.page(), "old")
        assert el.tag == "object" and el.get("owner") == "platform" and el.get("label") == "Modernised"
        svg = EX.render(d, os.path.join(tmp_dir, "legacy.svg"))
        assert "Modernised" in open(svg["output"], encoding="utf-8").read()

    def test_undo_redo_stress(self):
        s = Session(); s.set_project(P.new_document(), None)
        checkpoints = [s.doc.to_xml()]
        for i in range(30):
            s.snapshot(f"op{i}")
            if i % 3 == 0:
                SH.add_shape(s.doc, s.page(), label=f"n{i}", cell_id=f"n{i}")
            elif i % 3 == 1:
                SH.move(s.doc, s.page(), f"n{i - 1}", dx=10)
            else:
                SH.set_style(s.doc, s.page(), f"n{i - 2}", theme="blue")
            checkpoints.append(s.doc.to_xml())
        for i in range(30, 0, -1):
            assert s.doc.to_xml() == checkpoints[i]
            s.undo()
        assert s.doc.to_xml() == checkpoints[0]
        for i in range(30):
            s.redo()
        assert s.doc.to_xml() == checkpoints[30]
        s.snapshot("rm"); SH.remove_cell(s.doc, s.page(), "n0")
        s.snapshot("readd"); SH.add_shape(s.doc, s.page(), label="n0", cell_id="n0")
        assert len(SH.list_cells(s.doc, s.page())) == 10

    def test_preview_bundle(self, tmp_dir):
        doc = _architecture(P.new_document())
        f = os.path.join(tmp_dir, "arch.drawio")
        P.save(doc, f)
        r = PV.capture(doc, f, "quick")
        m = json.load(open(r["_manifest_path"]))
        assert m["protocol_version"] == "preview-bundle/v1" and m["software"] == "drawio"
        for k in ("bundle_id", "bundle_kind", "recipe", "status", "created_at", "generator",
                  "source", "artifacts", "summary_path"):
            assert k in m
        hero = r["artifacts"][0]["abs_path"]
        _png_size(hero)
        assert PV.capture(doc, f, "quick")["cached"] is True
        assert PV.latest(f)["bundle_id"] == r["bundle_id"]
        PG.add_page(doc, "P2")
        g = PV.capture(doc, f, "pages")
        assert len(g["artifacts"]) == 2
        print(f"\n  PREVIEW: {r['_bundle_dir']}")


# ── installed CLI ─────────────────────────────────────────────────────────────

class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-drawio")

    def _run(self, args, check=True):
        return subprocess.run(self.CLI_BASE + args, capture_output=True, text=True, check=check,
                              stdin=subprocess.DEVNULL, timeout=300)

    def _j(self, args):
        return json.loads(self._run(["--json"] + args).stdout)

    def test_help(self):
        r = self._run(["--help"])
        for g in ("project", "shape", "connector", "page", "layout", "export", "preview", "session"):
            assert g in r.stdout

    def test_version(self):
        assert "1.0.0" in self._run(["--version"]).stdout

    def test_project_new_json(self, tmp_dir):
        f = os.path.join(tmp_dir, "t.drawio")
        d = self._j(["project", "new", "-o", f, "--page-size", "16:9"])
        assert d["created"] and d["pages"][0]["page_width"] == 1600 and os.path.isfile(f)

    def test_autosave_dryrun_undo(self, tmp_dir):
        f = os.path.join(tmp_dir, "t.drawio")
        self._run(["project", "new", "-o", f])
        a = self._j(["-p", f, "shape", "add", "-l", "A"])["id"]
        assert a in open(f).read()  # auto-saved
        self._j(["-p", f, "--dry-run", "shape", "add", "-l", "Ghost"])
        assert "Ghost" not in open(f).read()
        self._j(["-p", f, "shape", "add", "-l", "B"])
        assert self._j(["-p", f, "session", "history"])["undo"] == ["add rectangle", "add rectangle"]
        self._j(["-p", f, "session", "undo"])
        txt = open(f).read()
        assert "B" not in [c["label"] for c in self._j(["-p", f, "shape", "list"])] and a in txt
        self._j(["-p", f, "session", "redo"])
        assert {"A", "B"} == {c["label"] for c in self._j(["-p", f, "shape", "list"])}

    def test_errors_exit_nonzero_with_json(self, tmp_dir):
        r = self._run(["--json", "-p", os.path.join(tmp_dir, "missing.drawio"), "project", "info"], check=False)
        assert r.returncode != 0 and "error" in json.loads(r.stdout)
        f = os.path.join(tmp_dir, "t.drawio")
        self._run(["project", "new", "-o", f])
        r = self._run(["--json", "-p", f, "shape", "move", "nope", "-x", "1"], check=False)
        assert r.returncode == 1 and "not found" in json.loads(r.stdout)["error"]
        r = self._run(["-p", f, "shape", "add", "--style", "fillColor=blue"], check=False)
        assert r.returncode == 1 and "Invalid color" in r.stderr

    def test_full_agent_pipeline(self, tmp_dir):
        f = os.path.join(tmp_dir, "pipeline.drawio")
        png = os.path.join(tmp_dir, "pipeline.png")
        pdf = os.path.join(tmp_dir, "pipeline.pdf")
        self._run(["project", "new", "-o", f])
        u = self._j(["-p", f, "shape", "add", "-s", "actor", "-l", "User"])["id"]
        app = self._j(["-p", f, "shape", "add", "-l", "App", "-t", "blue"])["id"]
        db = self._j(["-p", f, "shape", "add", "-s", "cylinder", "-l", "DB", "-t", "green"])["id"]
        self._j(["-p", f, "connector", "add", u, app, "-l", "uses"])
        self._j(["-p", f, "connector", "add", app, db, "-l", "SQL", "--dashed", "--end-arrow", "open"])
        self._j(["-p", f, "shape", "style", app, "fontStyle=1", "rounded=1"])
        self._j(["-p", f, "layout", "tree", "-d", "right"])
        self._j(["-p", f, "page", "add", "-n", "Notes"])
        self._j(["-p", f, "shape", "add", "-s", "note", "-l", "TODO", "--page", "Notes"])
        info = self._j(["-p", f, "project", "info"])
        assert info["total_shapes"] == 4 and info["total_connectors"] == 2 and info["page_count"] == 2
        r = self._j(["-p", f, "export", "render", png, "-s", "2"])
        assert r["verification"]["valid"] and r["verification"]["width"] > 300
        r = self._j(["-p", f, "export", "render", pdf, "--all-pages"])
        assert r["verification"]["pages"] == 2
        with open(png, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"
        print(f"\n  PNG: {png} ({os.path.getsize(png):,} bytes)\n  PDF: {pdf} ({os.path.getsize(pdf):,} bytes)")

    def test_preview_cli(self, tmp_dir):
        f = os.path.join(tmp_dir, "p.drawio")
        self._run(["project", "new", "-o", f])
        self._j(["-p", f, "shape", "add", "-l", "Hello"])
        r = self._j(["-p", f, "preview", "capture"])
        assert os.path.isfile(r["artifacts"][0]["abs_path"]) and r["cached"] is False
        assert self._j(["-p", f, "preview", "latest"])["bundle_id"] == r["bundle_id"]

    def test_export_check(self):
        d = self._j(["export", "check"])
        assert os.path.isfile(d["drawio"]) and "png" in d["formats"]

    def test_repl_scripted(self, tmp_dir):
        f = os.path.join(tmp_dir, "r.drawio")
        script = f"project new -o {f}\nshape add -l FromRepl --id r1\nproject save\nquit\n"
        r = subprocess.run(self.CLI_BASE, input=script, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        assert "FromRepl" in open(f).read()
