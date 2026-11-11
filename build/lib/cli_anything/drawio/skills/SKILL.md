---
name: >-
  cli-anything-drawio
description: >-
  Create and edit draw.io / diagrams.net diagrams (.drawio files) from the command line: shapes,
  connectors, pages, layers, styles and auto-layout. Renders PNG, SVG, PDF, JPG and VSDX with the
  real draw.io Desktop. Use for architecture diagrams, flowcharts, org charts, or any request to
  draw, diagram or export a .drawio file.
---

# cli-anything-drawio

A stateful CLI for draw.io. It edits native `.drawio` files (mxGraph XML) directly, so the output opens unchanged in the draw.io GUI. Every image and document export is rendered by the **real draw.io Desktop** in headless mode.

## Prerequisites

- Python 3.10+, then `pip install -e <drawio-dev>/agent-harness`. The package is `cli-anything-drawio`.
- **draw.io Desktop is required.** Install it with `brew install --cask drawio` (macOS) or from the drawio-desktop releases page. You can also set `DRAWIO_BIN`.
- Check the setup with `cli-anything-drawio --json export check`.

## Syntax

```
cli-anything-drawio [--json] [-p FILE.drawio] [--dry-run] <group> <command> [args]
```

Global options go **before** the group. Most editing commands also accept `--page INDEX|NAME|ID`; without it they use the current page.

## Command groups

| Group | Commands | Purpose |
|-------|----------|---------|
| `project` | `new -o F`, `open F`, `save [-o F] [--compressed]`, `info`, `xml`, `close` | Diagram files |
| `page` | `list`, `add -n NAME`, `remove`, `rename REF NAME`, `duplicate`, `move REF IDX`, `use REF`, `set [--background #hex] [--page-size a4] [--landscape] [--grid/--no-grid]` | Pages (tabs) |
| `shape` | `types`, `add`, `list [--kind shape\|connector\|layer]`, `get ID`, `find TEXT`, `remove ID…`, `move ID -x -y \| --dx --dy`, `resize ID -w -h`, `label ID TEXT`, `style ID k=v… [--theme] [--remove k] [--replace S]`, `data ID KEY [VALUE] [--delete]`, `duplicate ID`, `order ID front\|back` | Shapes |
| `connector` | `add SRC TGT [-l label] [-k orthogonal\|rounded\|straight\|curved\|elbow\|entity] [--end-arrow A] [--start-arrow A] [--dashed] [--color] [--width]`, `list [--of ID]`, `reconnect ID [--source] [--target]`, `remove ID` | Edges |
| `layer` | `list`, `add NAME`, `hide ID`, `show ID` | Layers |
| `layout` | `align left\|center\|right\|top\|middle\|bottom [IDs]`, `distribute horizontal\|vertical [IDs]`, `grid [-c N]`, `row`, `column`, `tree [--root ID] [-d down\|right]` | Arrange |
| `export` | `render OUT [-f png\|svg\|pdf\|jpg\|vsdx] [-s SCALE] [--width] [--height] [-b BORDER] [-t] [--all-pages] [--crop] [-e] [-q] [--overwrite]`, `check` | Render via draw.io |
| `preview` | `recipes`, `capture [-r quick\|hires\|pages] [--force]`, `latest` | preview-bundle/v1 snapshots |
| `session` | `status`, `undo`, `redo`, `history` | History |

**Shape presets** (`-s`): rectangle, rounded, ellipse, circle, diamond, triangle, hexagon, parallelogram, trapezoid, cylinder, cloud, document, process, step, note, card, actor, double-ellipse, arrow, text, container, swimlane.

**Themes** (`-t`): blue, green, orange, yellow, red, purple, gray, dark, white.

Run `shape types --json` to list the exact styles and arrow names.

## Example: architecture diagram

```bash
F=/abs/path/arch.drawio
cli-anything-drawio --json project new -o $F --page-size 16:9
cli-anything-drawio --json -p $F shape add -l "Web Client" -s rounded -t blue --id web
cli-anything-drawio --json -p $F shape add -l "API" -s hexagon -t purple --id api
cli-anything-drawio --json -p $F shape add -l "Postgres" -s cylinder -t green --id db
cli-anything-drawio --json -p $F connector add web api -l HTTPS
cli-anything-drawio --json -p $F connector add api db -l SQL --dashed --end-arrow open
cli-anything-drawio --json -p $F shape style api fontStyle=1 strokeWidth=2
cli-anything-drawio --json -p $F layout tree -d right
cli-anything-drawio --json -p $F export render /abs/path/arch.png -s 2 --overwrite
cli-anything-drawio --json -p $F export render /abs/path/arch.pdf --all-pages --overwrite
```

## State and saving

- In one-shot mode with `-p FILE`, any mutating command **auto-saves** to FILE. Add `--dry-run` to see the result without writing.
- Undo/redo persists across invocations in the sidecar `.<file>.drawio-session.json`, which holds up to 50 steps. The history is discarded automatically if the `.drawio` file was changed elsewhere.
- In the REPL (`cli-anything-drawio [FILE]`), nothing is saved until you run `project save`.
- Use `page use NAME` to set the current page; it persists in the sidecar.

## Previews

The CLI publishes previews and `cli-hub` views them.

```bash
cli-anything-drawio --json -p $F preview capture          # → _bundle_dir, artifacts[0].abs_path (PNG)
cli-anything-drawio --json -p $F preview latest           # newest bundle, no re-render
cli-hub previews inspect <_bundle_dir>                    # viewing only; never renders
```

Bundles live in `<file dir>/.cli-anything/previews/drawio/<recipe>/<id>/`, each with `manifest.json`, `summary.json` and `artifacts/`. A capture is reused (`cached: true`) when the diagram hasn't changed. The images come from draw.io itself, so you can read `artifacts[0].abs_path` to check the layout visually.

## Agent guidance

1. **Always pass `--json`.** On success it prints one JSON object or array to stdout. On failure the exit code is 1 and stdout carries `{"error": "..."}`.
2. **Use `--id` for stable names.** `shape add` and `connector add` accept `--id`, so you can refer to cells later without parsing output. Otherwise read `id` from the JSON.
3. **Inspect before editing.** Use `project info`, `shape list`, `shape find TEXT` and `connector list --of ID`.
4. **Labels may contain HTML.** Shapes are created with `html=1`, so labels like `"<b>API</b><br>v2"` work.
5. **Verify exports.** `export render` returns a `verification` object (valid flag, PNG width and height, PDF page count) and fails if draw.io produced a bad file.
6. **Mind the backend limits.** PDF page *ranges* are not supported; use `--all-pages` or `--page`. Native XML output comes from `project save` or `project xml`, not from `export`. `--transparent` and `--embed-diagram` work only with PNG.
7. **Use absolute paths.** Each render takes about 3–5 s because draw.io Desktop has to start.

## Version

1.0.0
