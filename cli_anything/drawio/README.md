# cli-anything-drawio

A stateful command-line interface to **draw.io**. It edits native `.drawio` (mxGraph XML) files directly and renders them with the **real draw.io Desktop** in headless mode. Use it from a shell, from scripts, or from an AI agent, with `--json` output on every command.

## 1. Install the draw.io dependency (required)

The CLI calls draw.io Desktop for every PNG, SVG, PDF, JPG and VSDX export. It does not have a fallback renderer.

| OS | Command |
|----|---------|
| macOS | `brew install --cask drawio` |
| Linux | deb, rpm, AppImage or snap from <https://github.com/jgraph/drawio-desktop/releases> |
| Windows | installer from the same releases page |

Custom location: `export DRAWIO_BIN=/path/to/draw.io`. On a headless Linux server, run exports under `xvfb-run`.

Check the install with `cli-anything-drawio export check`.

## 2. Install the CLI

```bash
cd agent-harness
pip install -e .
which cli-anything-drawio
```

## 3. Usage

```bash
# One-shot mode: each mutating command auto-saves the --project file
cli-anything-drawio project new -o arch.drawio
cli-anything-drawio -p arch.drawio shape add -l "Web App" -t blue --id web
cli-anything-drawio -p arch.drawio shape add -s cylinder -l "Postgres" -t green --id db
cli-anything-drawio -p arch.drawio connector add web db -l SQL --dashed
cli-anything-drawio -p arch.drawio layout tree -d right
cli-anything-drawio -p arch.drawio export render arch.png -s 2
cli-anything-drawio -p arch.drawio export render arch.pdf --all-pages

# Try a change without saving it
cli-anything-drawio --dry-run -p arch.drawio shape remove db

# Undo works across separate invocations
cli-anything-drawio -p arch.drawio session undo

# Interactive REPL (the default when no subcommand is given)
cli-anything-drawio arch.drawio      # or: cli-anything-drawio repl arch.drawio
```

### Command groups

| Group | Commands |
|-------|----------|
| `project` | `new`, `open`, `save [--compressed]`, `info`, `xml`, `close` |
| `page` | `list`, `add`, `remove`, `rename`, `duplicate`, `move`, `use`, `set` (background, grid, size) |
| `shape` | `types`, `add`, `list`, `get`, `find`, `remove`, `move`, `resize`, `label`, `style`, `data`, `duplicate`, `order` |
| `connector` | `add`, `list [--of ID]`, `reconnect`, `remove` |
| `layer` | `list`, `add`, `hide`, `show` |
| `layout` | `align`, `distribute`, `grid`, `row`, `column`, `tree` |
| `export` | `render OUTPUT` (png/svg/pdf/jpg/vsdx; options `--scale`, `--transparent`, `--all-pages`, `--embed-diagram`, `--crop`, …), `check` |
| `preview` | `recipes`, `capture`, `latest` |
| `session` | `status`, `undo`, `redo`, `history` |

Global options are `--json`, `-p/--project FILE`, `--dry-run` and `--version`. Most editing commands also take `--page INDEX|NAME|ID`.

### State model

- The project file is the native `.drawio` file. It opens in the draw.io GUI and in diagrams.net, and the CLI can read files that the GUI saved compressed.
- Undo/redo history (up to 50 steps) and the current page are kept in a sidecar file, `.<file>.drawio-session.json`. The history is only reused if the `.drawio` file hasn't changed since it was written, so edits made in the GUI invalidate it safely.
- In one-shot mode, mutations auto-save. `--dry-run` skips the save. In the REPL, you save explicitly with `project save`.

### Previews

Previews follow the `preview-bundle/v1` protocol. This CLI produces them, and `cli-hub` views them:

```bash
cli-anything-drawio --json -p arch.drawio preview capture            # recipe: quick | hires | pages
cli-anything-drawio --json -p arch.drawio preview latest
cli-hub previews inspect <_bundle_dir>                               # human viewer (read-only)
```

Bundles are written to `<project dir>/.cli-anything/previews/drawio/<recipe>/<bundle_id>/` and contain `manifest.json`, `summary.json` and `artifacts/*.png`. Every artifact is rendered by draw.io Desktop, so a preview is a truthful view of the file. A capture is reused when the document fingerprint hasn't changed.

## 4. Tests

```bash
cd agent-harness
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/drawio/tests/ -v -s
```

The end-to-end tests call the real draw.io Desktop and fail if it isn't installed. See `tests/TEST.md` for the plan and the latest results.
