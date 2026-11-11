"""cli-anything-drawio — stateful CLI for draw.io diagrams.

One-shot:  cli-anything-drawio --project arch.drawio shape add -l "API" --theme blue
REPL:      cli-anything-drawio            (no subcommand)
Agents:    add --json to any command for machine-readable output.
"""

import json
import os
import shlex
import sys

import click

from .core import project as P
from .core import shapes as SH
from .core import connectors as CN
from .core import pages as PG
from .core import layout as LY
from .core import styles as ST
from .core import export as EX
from .core import preview as PV
from .core.session import get_session
from .utils import drawio_backend as backend

VERSION = "1.0.0"
_repl_mode = False
_json = False


# ── output helpers ────────────────────────────────────────────────────────────

def out(data, human=None):
    if _json:
        click.echo(json.dumps(data, indent=2, default=str))
    elif human is not None:
        human(data)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            click.echo(f"{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            click.echo(json.dumps(item, default=str) if not isinstance(item, str) else item)
    else:
        click.echo(str(data))


def fail(msg: str):
    if _json:
        click.echo(json.dumps({"error": msg}))
    else:
        click.echo(f"Error: {msg}", err=True)
    if _repl_mode:
        raise _ReplError(msg)
    sys.exit(1)


class _ReplError(Exception):
    pass


def guarded(fn):
    """Convert domain errors into clean messages + non-zero exit."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (P.DrawioError, ValueError, FileNotFoundError, RuntimeError) as e:
            fail(str(e))
    return wrapper


def mutate(label, fn):
    """Snapshot for undo, run fn; roll back the document if fn raises."""
    sess = get_session()
    sess.require()
    sess.snapshot(label)
    try:
        return fn()
    except Exception:
        _, xml = sess.undo_stack.pop()
        sess.doc = P.from_xml(xml)
        raise


def cell_table(cells):
    def h(rows):
        if not rows:
            click.echo("(none)")
        for c in rows:
            g = c.get("geometry")
            pos = f" @({g['x']:g},{g['y']:g} {g['width']:g}x{g['height']:g})" if g else ""
            link = f" {c['source']} -> {c['target']}" if c["type"] == "connector" else ""
            click.echo(f"{c['id']:<16} {c['type']:<10} {c['label']!r}{pos}{link}")
    return h


def _page_opt(f):
    return click.option("--page", "page_ref", default=None,
                        help="Page index, id or name (default: current page)")(f)


def _page(page_ref):
    return get_session().page(page_ref)


# ── root group ────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--project", "-p", "project_path", default=None, help="Path to .drawio file")
@click.option("--dry-run", "dry_run", is_flag=True, help="Run without saving changes to disk")
@click.version_option(VERSION, prog_name="cli-anything-drawio")
@click.pass_context
def cli(ctx, use_json, project_path, dry_run):
    """Stateful CLI for draw.io diagrams (rendered by real draw.io Desktop)."""
    global _json
    _json = use_json
    sess = get_session()
    if project_path:
        ap = os.path.abspath(project_path)
        if sess.project_path != ap:
            try:
                sess.open(project_path)
            except P.DrawioError as e:
                fail(str(e))
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.result_callback()
def auto_save_on_exit(result, use_json, project_path, dry_run, **kwargs):
    """Auto-save after one-shot mutations (skipped in REPL and with --dry-run)."""
    if _repl_mode or dry_run:
        return
    sess = get_session()
    if sess.has_project() and sess._modified and sess.project_path:
        try:
            sess.save_session()
        except Exception as e:  # pragma: no cover
            click.echo(f"Warning: Auto-save failed: {e}", err=True)


# ── project ───────────────────────────────────────────────────────────────────

@cli.group()
def project():
    """Create, open, save and inspect diagram files."""


@project.command("new")
@click.option("-o", "--output", default=None, help="Save to this .drawio path immediately")
@click.option("--page-name", default="Page-1")
@click.option("--page-size", type=click.Choice(list(P.PAGE_SIZES)), default="letter")
@click.option("--landscape", is_flag=True)
@click.option("--no-grid", is_flag=True)
@click.option("--background", default=None, help="Page background color, e.g. #ffffff")
@click.option("--overwrite", is_flag=True)
@guarded
def project_new(output, page_name, page_size, landscape, no_grid, background, overwrite):
    """Create a new diagram."""
    if output and os.path.exists(output) and not overwrite:
        raise P.DrawioError(f"{output} exists (use --overwrite)")
    if background:
        ST.validate_color(background)
    doc = P.new_document(page_name, page_size, landscape, not no_grid, background)
    sess = get_session()
    sess.set_project(doc, output)
    if output:
        sess.save_session(output)
    out(P.info(doc, output) | {"created": True})


@project.command("open")
@click.argument("path")
@guarded
def project_open(path):
    """Open an existing .drawio file (compressed or plain)."""
    doc = get_session().open(path)
    out(P.info(doc, path))


@project.command("save")
@click.option("-o", "--output", default=None, help="Save as (default: current path)")
@click.option("--compressed", is_flag=True, help="Store pages deflate-compressed like older draw.io")
@guarded
def project_save(output, compressed):
    """Save the diagram (plain XML by default)."""
    res = get_session().save_session(output, compressed=compressed)
    out(res, lambda r: click.echo(f"Saved {r['path']} ({r['bytes']} bytes)"))


@project.command("info")
@guarded
def project_info():
    """Summary of pages, shapes and connectors."""
    sess = get_session()
    data = P.info(sess.require(), sess.project_path)

    def h(d):
        click.echo(f"File: {d['path']}")
        for p in d["pages"]:
            click.echo(f"  [{p['index']}] {p['name']}: {p['shapes']} shapes, {p['connectors']} connectors, "
                       f"{p['page_width']}x{p['page_height']}")
    out(data, h)


@project.command("xml")
@click.option("--compressed", is_flag=True)
@guarded
def project_xml(compressed):
    """Print the document's mxfile XML."""
    xml = get_session().require().to_xml(compressed=compressed)
    out({"xml": xml}, lambda d: click.echo(d["xml"]))


@project.command("close")
@guarded
def project_close():
    """Close the current diagram (unsaved changes are discarded)."""
    get_session().close()
    out({"closed": True})


# ── page ──────────────────────────────────────────────────────────────────────

@cli.group()
def page():
    """Manage pages (tabs)."""


@page.command("list")
@guarded
def page_list():
    data = PG.list_pages(get_session().require())
    out(data, lambda rows: [click.echo(f"[{r['index']}] {r['name']} ({r['cells']} cells) id={r['id']}") for r in rows])


@page.command("add")
@click.option("-n", "--name", default=None)
@click.option("--page-size", type=click.Choice(list(P.PAGE_SIZES)), default="letter")
@click.option("--landscape", is_flag=True)
@guarded
def page_add(name, page_size, landscape):
    doc = get_session().require()
    out(mutate("page add", lambda: PG.add_page(doc, name, page_size, landscape)))


@page.command("remove")
@click.argument("ref")
@guarded
def page_remove(ref):
    sess = get_session()
    res = mutate("page remove", lambda: PG.remove_page(sess.doc, ref))
    sess.current_page = None
    out(res)


@page.command("rename")
@click.argument("ref")
@click.argument("name")
@guarded
def page_rename(ref, name):
    out(mutate("page rename", lambda: PG.rename_page(get_session().doc, ref, name)))


@page.command("duplicate")
@click.argument("ref")
@click.option("-n", "--name", default=None)
@guarded
def page_duplicate(ref, name):
    out(mutate("page duplicate", lambda: PG.duplicate_page(get_session().doc, ref, name)))


@page.command("move")
@click.argument("ref")
@click.argument("index", type=int)
@guarded
def page_move(ref, index):
    out(mutate("page move", lambda: PG.move_page(get_session().doc, ref, index)))


@page.command("use")
@click.argument("ref")
@guarded
def page_use(ref):
    """Set the current page for subsequent commands (persisted in the session)."""
    sess = get_session()
    p = sess.require().page(ref)
    sess.current_page = p.get("id")
    sess._modified = True  # persist selection to the sidecar
    out({"current_page": sess.doc.page_index(p), "name": p.get("name")})


@page.command("set")
@click.argument("ref", required=False)
@click.option("--background", default=None, help="#RRGGBB or 'none'")
@click.option("--grid/--no-grid", default=None)
@click.option("--page-size", type=click.Choice(list(P.PAGE_SIZES)), default=None)
@click.option("--landscape", is_flag=True)
@guarded
def page_set(ref, background, grid, page_size, landscape):
    """Page properties (File > Page Setup / Format panel)."""
    sess = get_session()
    ref = ref if ref is not None else sess.current_page
    out(mutate("page set", lambda: PG.set_page_props(sess.doc, ref, background, grid, page_size, landscape)))


# ── shape ─────────────────────────────────────────────────────────────────────

@cli.group()
def shape():
    """Add and edit shapes (vertices)."""


@shape.command("types")
def shape_types():
    """List shape presets, themes and connector styles."""
    data = {"shapes": {k: {"style": v[0], "width": v[1], "height": v[2]} for k, v in ST.SHAPES.items()},
            "themes": {k: {"fillColor": f, "strokeColor": s} for k, (f, s) in ST.THEMES.items()},
            "connector_styles": list(ST.EDGES), "arrows": list(ST.ARROWS)}

    def h(d):
        click.echo("Shapes:  " + ", ".join(d["shapes"]))
        click.echo("Themes:  " + ", ".join(d["themes"]))
        click.echo("Connectors: " + ", ".join(d["connector_styles"]))
        click.echo("Arrows:  " + ", ".join(d["arrows"]))
    out(data, h)


@shape.command("add")
@click.option("-s", "--shape", "shape_name", default="rectangle", help="Preset (see 'shape types')")
@click.option("-l", "--label", default="")
@click.option("-x", type=float, default=40)
@click.option("-y", type=float, default=40)
@click.option("-w", "--width", type=float, default=None)
@click.option("-h", "--height", type=float, default=None)
@click.option("-t", "--theme", type=click.Choice(list(ST.THEMES)), default=None)
@click.option("--style", "style_kv", multiple=True, help="Extra style key=value (repeatable)")
@click.option("--parent", default=None, help="Layer or container id")
@click.option("--id", "cell_id", default=None, help="Explicit cell id")
@_page_opt
@guarded
def shape_add(shape_name, label, x, y, width, height, theme, style_kv, parent, cell_id, page_ref):
    """Add a shape. Prints its id."""
    extra = ST.parse_kv_pairs(style_kv)
    res = mutate(f"add {shape_name}", lambda: SH.add_shape(
        get_session().doc, _page(page_ref), shape_name, label, x, y, width, height, theme, extra, parent, cell_id))
    out(res, lambda r: click.echo(f"Added {shape_name} {r['id']}"))


@shape.command("list")
@click.option("--kind", type=click.Choice(["all", "shape", "connector", "layer"]), default="all")
@_page_opt
@guarded
def shape_list(kind, page_ref):
    """List cells on the page."""
    out(SH.list_cells(get_session().require(), _page(page_ref), kind), cell_table(None))


@shape.command("get")
@click.argument("cell_id")
@_page_opt
@guarded
def shape_get(cell_id, page_ref):
    out(SH.cell_summary(SH.find_cell(get_session().require(), _page(page_ref), cell_id)))


@shape.command("find")
@click.argument("text")
@click.option("--exact", is_flag=True)
@_page_opt
@guarded
def shape_find(text, exact, page_ref):
    """Find cells by label text."""
    out(SH.find_by_label(get_session().require(), _page(page_ref), text, exact), cell_table(None))


@shape.command("remove")
@click.argument("cell_ids", nargs=-1, required=True)
@_page_opt
@guarded
def shape_remove(cell_ids, page_ref):
    """Delete shapes/connectors (attached connectors and children go too)."""
    def go():
        removed = []
        for cid in cell_ids:
            removed += SH.remove_cell(get_session().doc, _page(page_ref), cid)["removed"]
        return {"removed": removed, "count": len(removed)}
    out(mutate("remove", go))


@shape.command("move")
@click.argument("cell_id")
@click.option("-x", type=float, default=None)
@click.option("-y", type=float, default=None)
@click.option("--dx", type=float, default=None)
@click.option("--dy", type=float, default=None)
@_page_opt
@guarded
def shape_move(cell_id, x, y, dx, dy, page_ref):
    out(mutate("move", lambda: SH.move(get_session().doc, _page(page_ref), cell_id, x, y, dx, dy)))


@shape.command("resize")
@click.argument("cell_id")
@click.option("-w", "--width", type=float, default=None)
@click.option("-h", "--height", type=float, default=None)
@_page_opt
@guarded
def shape_resize(cell_id, width, height, page_ref):
    out(mutate("resize", lambda: SH.resize(get_session().doc, _page(page_ref), cell_id, width, height)))


@shape.command("label")
@click.argument("cell_id")
@click.argument("text")
@_page_opt
@guarded
def shape_label(cell_id, text, page_ref):
    """Set the label of a shape or connector (HTML allowed)."""
    out(mutate("label", lambda: SH.relabel(get_session().doc, _page(page_ref), cell_id, text)))


@shape.command("style")
@click.argument("cell_id")
@click.argument("props", nargs=-1)
@click.option("-t", "--theme", type=click.Choice(list(ST.THEMES)), default=None)
@click.option("--remove", "remove_keys", multiple=True, help="Style key to remove (repeatable)")
@click.option("--replace", default=None, help="Replace entire style string")
@_page_opt
@guarded
def shape_style(cell_id, props, theme, remove_keys, replace, page_ref):
    """Edit style: shape style ID fillColor=#ff0000 fontStyle=1 dashed=1"""
    kv = ST.parse_kv_pairs(props)
    out(mutate("style", lambda: SH.set_style(get_session().doc, _page(page_ref), cell_id, kv,
                                               remove_keys, theme, replace)))


@shape.command("data")
@click.argument("cell_id")
@click.argument("key")
@click.argument("value", required=False)
@click.option("--delete", is_flag=True)
@_page_opt
@guarded
def shape_data(cell_id, key, value, delete, page_ref):
    """Set a custom property (Edit > Edit Data)."""
    if value is None and not delete:
        raise P.DrawioError("Provide VALUE or --delete")
    out(mutate("data", lambda: SH.set_data(get_session().doc, _page(page_ref), cell_id, key,
                                             None if delete else value)))


@shape.command("duplicate")
@click.argument("cell_id")
@click.option("--dx", type=float, default=20)
@click.option("--dy", type=float, default=20)
@_page_opt
@guarded
def shape_duplicate(cell_id, dx, dy, page_ref):
    out(mutate("duplicate", lambda: SH.duplicate(get_session().doc, _page(page_ref), cell_id, dx, dy)))


@shape.command("order")
@click.argument("cell_id")
@click.argument("where", type=click.Choice(["front", "back"]))
@_page_opt
@guarded
def shape_order(cell_id, where, page_ref):
    """Bring to front / send to back."""
    out(mutate(f"to {where}", lambda: SH.reorder(get_session().doc, _page(page_ref), cell_id, where)))


# ── connector ─────────────────────────────────────────────────────────────────

@cli.group()
def connector():
    """Connect shapes with edges."""


@connector.command("add")
@click.argument("source")
@click.argument("target")
@click.option("-l", "--label", default="")
@click.option("-k", "--kind", type=click.Choice(list(ST.EDGES)), default="orthogonal")
@click.option("--end-arrow", default=None)
@click.option("--start-arrow", default=None)
@click.option("--dashed", is_flag=True)
@click.option("--color", default=None)
@click.option("--width", type=float, default=None)
@click.option("--style", "style_kv", multiple=True)
@click.option("--id", "cell_id", default=None)
@_page_opt
@guarded
def connector_add(source, target, label, kind, end_arrow, start_arrow, dashed, color, width,
                  style_kv, cell_id, page_ref):
    """Connect SOURCE to TARGET shape ids."""
    extra = ST.parse_kv_pairs(style_kv)
    res = mutate("connect", lambda: CN.add_connector(
        get_session().doc, _page(page_ref), source, target, label, kind, end_arrow, start_arrow,
        dashed, color, width, extra, cell_id))
    out(res, lambda r: click.echo(f"Connected {source} -> {target} ({r['id']})"))


@connector.command("list")
@click.option("--of", "of_shape", default=None, help="Only connectors attached to this shape")
@_page_opt
@guarded
def connector_list(of_shape, page_ref):
    doc = get_session().require()
    data = CN.connectors_of(doc, _page(page_ref), of_shape) if of_shape else \
        SH.list_cells(doc, _page(page_ref), "connector")
    out(data, cell_table(None))


@connector.command("reconnect")
@click.argument("edge_id")
@click.option("--source", default=None)
@click.option("--target", default=None)
@_page_opt
@guarded
def connector_reconnect(edge_id, source, target, page_ref):
    out(mutate("reconnect", lambda: CN.reconnect(get_session().doc, _page(page_ref), edge_id, source, target)))


@connector.command("remove")
@click.argument("edge_id")
@_page_opt
@guarded
def connector_remove(edge_id, page_ref):
    def go():
        el = SH.find_cell(get_session().doc, _page(page_ref), edge_id)
        if not SH.is_edge(el):
            raise P.DrawioError(f"'{edge_id}' is not a connector")
        return SH.remove_cell(get_session().doc, _page(page_ref), edge_id)
    out(mutate("remove connector", go))


# ── layer ─────────────────────────────────────────────────────────────────────

@cli.group()
def layer():
    """Manage layers."""


@layer.command("list")
@_page_opt
@guarded
def layer_list(page_ref):
    out(SH.list_cells(get_session().require(), _page(page_ref), "layer"), cell_table(None))


@layer.command("add")
@click.argument("name")
@_page_opt
@guarded
def layer_add(name, page_ref):
    out(mutate("add layer", lambda: SH.add_layer(get_session().doc, _page(page_ref), name)))


@layer.command("hide")
@click.argument("layer_id")
@_page_opt
@guarded
def layer_hide(layer_id, page_ref):
    out(mutate("hide layer", lambda: SH.set_layer_visible(get_session().doc, _page(page_ref), layer_id, False)))


@layer.command("show")
@click.argument("layer_id")
@_page_opt
@guarded
def layer_show(layer_id, page_ref):
    out(mutate("show layer", lambda: SH.set_layer_visible(get_session().doc, _page(page_ref), layer_id, True)))


# ── layout ────────────────────────────────────────────────────────────────────

@cli.group()
def layout():
    """Arrange shapes: align, distribute, grid/row/column/tree."""


@layout.command("align")
@click.argument("mode", type=click.Choice(["left", "center", "right", "top", "middle", "bottom"]))
@click.argument("ids", nargs=-1)
@_page_opt
@guarded
def layout_align(mode, ids, page_ref):
    """Align shapes (all top-level shapes if no ids)."""
    out(mutate("align", lambda: LY.align(get_session().doc, _page(page_ref), ids, mode)))


@layout.command("distribute")
@click.argument("axis", type=click.Choice(["horizontal", "vertical"]))
@click.argument("ids", nargs=-1)
@_page_opt
@guarded
def layout_distribute(axis, ids, page_ref):
    out(mutate("distribute", lambda: LY.distribute(get_session().doc, _page(page_ref), ids, axis)))


@layout.command("grid")
@click.argument("ids", nargs=-1)
@click.option("-c", "--columns", type=int, default=3)
@click.option("--spacing", type=float, default=40)
@_page_opt
@guarded
def layout_grid(ids, columns, spacing, page_ref):
    out(mutate("grid layout", lambda: LY.grid_layout(get_session().doc, _page(page_ref), ids, columns, spacing)))


@layout.command("row")
@click.argument("ids", nargs=-1)
@click.option("--spacing", type=float, default=40)
@_page_opt
@guarded
def layout_row(ids, spacing, page_ref):
    out(mutate("row layout", lambda: LY.line_layout(get_session().doc, _page(page_ref), ids, "row", spacing)))


@layout.command("column")
@click.argument("ids", nargs=-1)
@click.option("--spacing", type=float, default=40)
@_page_opt
@guarded
def layout_column(ids, spacing, page_ref):
    out(mutate("column layout", lambda: LY.line_layout(get_session().doc, _page(page_ref), ids, "column", spacing)))


@layout.command("tree")
@click.option("--root", "root_id", default=None)
@click.option("-d", "--direction", type=click.Choice(["down", "right"]), default="down")
@click.option("--level-gap", type=float, default=80)
@click.option("--sibling-gap", type=float, default=40)
@_page_opt
@guarded
def layout_tree(root_id, direction, level_gap, sibling_gap, page_ref):
    """Layered tree following connectors."""
    out(mutate("tree layout", lambda: LY.tree_layout(get_session().doc, _page(page_ref), root_id, direction,
                                                       level_gap, sibling_gap)))


# ── export ────────────────────────────────────────────────────────────────────

@cli.group()
def export():
    """Render with draw.io Desktop (png, svg, pdf, jpg, vsdx)."""


@export.command("render")
@click.argument("output")
@click.option("-f", "--format", "fmt", type=click.Choice(list(backend.EXPORT_FORMATS) + ["jpeg"]), default=None,
              help="Defaults to OUTPUT's extension")
@click.option("--all-pages", is_flag=True, help="PDF only: all pages in one file")
@click.option("-s", "--scale", type=float, default=None)
@click.option("--width", type=int, default=None)
@click.option("--height", type=int, default=None)
@click.option("-b", "--border", type=int, default=None)
@click.option("-t", "--transparent", is_flag=True, help="PNG only")
@click.option("--crop", is_flag=True, help="PDF only: crop to diagram")
@click.option("-e", "--embed-diagram", is_flag=True, help="PNG only: embed editable diagram")
@click.option("-q", "--quality", type=int, default=None, help="JPG quality")
@click.option("--overwrite", is_flag=True)
@_page_opt
@guarded
def export_render(output, fmt, all_pages, scale, width, height, border, transparent, crop,
                  embed_diagram, quality, overwrite, page_ref):
    """Render the current diagram to OUTPUT."""
    sess = get_session()
    page_ref = page_ref if page_ref is not None else sess.current_page
    res = EX.render(sess.require(), output, fmt, page_ref, all_pages, scale, width, height, border,
                    transparent, crop, embed_diagram, quality, overwrite)
    out(res, lambda r: click.echo(f"Exported {r['output']} ({r['file_size']:,} bytes, {r['format']})"))


@export.command("check")
@guarded
def export_check():
    """Verify that draw.io Desktop is installed."""
    exe = backend.find_drawio()
    out({"drawio": exe, "version": backend.version(), "formats": list(backend.EXPORT_FORMATS)})


# ── preview ───────────────────────────────────────────────────────────────────

@cli.group()
def preview():
    """Publish preview-bundle/v1 snapshots (inspect with `cli-hub previews ...`)."""


@preview.command("recipes")
def preview_recipes():
    out(PV.RECIPES)


@preview.command("capture")
@click.option("-r", "--recipe", type=click.Choice(list(PV.RECIPES)), default="quick")
@click.option("--force", is_flag=True, help="Render even if an identical bundle exists")
@_page_opt
@guarded
def preview_capture(recipe, force, page_ref):
    """Render a preview bundle of the current state."""
    sess = get_session()
    page_ref = page_ref if page_ref is not None else sess.current_page
    res = PV.capture(sess.require(), sess.project_path, recipe, page_ref,
                     command=" ".join(["cli-anything-drawio"] + sys.argv[1:]), force=force)
    out(res, lambda r: click.echo(f"Preview: {r['artifacts'][0]['abs_path']}{' (cached)' if r['cached'] else ''}"))


@preview.command("latest")
@click.option("-r", "--recipe", default=None)
@guarded
def preview_latest(recipe):
    """Return the newest existing bundle (does not render)."""
    out(PV.latest(get_session().project_path, recipe))


# ── session ───────────────────────────────────────────────────────────────────

@cli.group()
def session():
    """Undo/redo and status."""


@session.command("status")
def session_status():
    out(get_session().status())


@session.command("undo")
@guarded
def session_undo():
    out({"undone": get_session().undo()})


@session.command("redo")
@guarded
def session_redo():
    out({"redone": get_session().redo()})


@session.command("history")
@guarded
def session_history():
    out(get_session().history())


# ── REPL ──────────────────────────────────────────────────────────────────────

REPL_HELP = {
    "project new|open|save|info|xml|close": "Diagram files",
    "page list|add|remove|rename|duplicate|move|use|set": "Pages",
    "shape types|add|list|get|find|remove|move|resize|label|style|data|duplicate|order": "Shapes",
    "connector add|list|reconnect|remove": "Connectors",
    "layer list|add|hide|show": "Layers",
    "layout align|distribute|grid|row|column|tree": "Arrange",
    "export render|check": "Render via draw.io Desktop",
    "preview recipes|capture|latest": "Preview bundles",
    "session status|undo|redo|history": "History",
    "help / quit": "This help / exit",
}


@cli.command()
@click.argument("project_path", required=False)
def repl(project_path):
    """Interactive mode (default when no command is given)."""
    global _repl_mode
    from .utils.repl_skin import ReplSkin
    _repl_mode = True
    skin = ReplSkin("drawio", version=VERSION)
    sess = get_session()
    if project_path:
        try:
            sess.open(project_path)
        except P.DrawioError as e:
            skin.error(str(e))
    skin.print_banner()
    pt = skin.create_prompt_session()
    while True:
        name = os.path.basename(sess.project_path) if sess.project_path else ""
        try:
            line = skin.get_input(pt, project_name=name, modified=sess._modified)
        except (EOFError, KeyboardInterrupt):
            break
        line = (line or "").strip()
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line in ("help", "?"):
            skin.help(REPL_HELP)
            continue
        try:
            args = shlex.split(line)
        except ValueError as e:
            skin.error(str(e))
            continue
        try:
            cli.main(args, standalone_mode=False, prog_name="drawio")
        except _ReplError:
            pass
        except click.exceptions.UsageError as e:
            skin.error(e.format_message())
        except click.exceptions.Abort:
            pass
        except SystemExit:
            pass
        except Exception as e:  # keep REPL alive
            skin.error(f"{type(e).__name__}: {e}")
    if sess._modified:
        skin.warning("Unsaved changes discarded (use 'project save' next time)")
    skin.print_goodbye()
    _repl_mode = False


def main():
    cli()


if __name__ == "__main__":
    main()
