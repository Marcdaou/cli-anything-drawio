# draw.io: CLI harness SOP

## Codebase analysis (`drawio-dev/`)

| Concern | Where in the source | Notes |
|---------|---------------------|-------|
| Graph engine | mxGraph, bundled in `src/main/webapp/js/grapheditor/Graph.js` | Cells form a tree: `0` (root) → layers (parent `0`) → vertices and edges |
| Data model | `.drawio` = `<mxfile><diagram name>(mxGraphModel or compressed text)</diagram>…` | Each page is a `<diagram>`. The compressed form is `base64(deflateRaw(encodeURIComponent(xml)))` (`Graph.compress`) |
| Shape palette | `Sidebar.js`, `createVertexTemplateEntry(style, w, h, …)` | Preset styles were copied verbatim into `core/styles.py` |
| Styles | `key=value;` strings on `mxCell@style`, edited in `Format.js` | Bare tokens such as `ellipse;` name a base style |
| Custom data | `<object label=… key=…><mxCell …/></object>` (Edit > Edit Data) | `shape data` converts an `mxCell` into this wrapper |
| Undo | `mxUndoManager` / `Editor.js` | Mirrored by XML snapshots in `core/session.py` |
| Export | GUI: `EditorUi.js` export dialogs. Headless: the **draw.io Desktop** `-x` CLI | This is the rendering backend |

## GUI action → CLI mapping

| GUI | CLI |
|-----|-----|
| Drag a shape from the sidebar | `shape add -s <preset> -l text -x -y -w -h -t <theme>` |
| Format panel | `shape style ID key=value… [--remove k] [--theme t]` |
| Double-click to edit a label | `shape label ID "text"` |
| Edit > Edit Data | `shape data ID key value` |
| Hover arrow → connect | `connector add SRC TGT -k orthogonal --end-arrow open` |
| Arrange > Align / Distribute / Layout | `layout align|distribute|grid|row|column|tree` |
| Arrange > To Front / To Back | `shape order ID front|back` |
| Page tabs | `page add|rename|duplicate|move|remove|use` |
| File > Page Setup | `page set --page-size a4 --landscape --background #fff` |
| Layers dialog | `layer add|hide|show|list` |
| File > Export as | `export render out.png|svg|pdf|jpg|vsdx` |
| Edit > Undo / Redo | `session undo|redo` |

## Backend

`utils/drawio_backend.py` finds draw.io Desktop (checking `DRAWIO_BIN`, then `PATH`, then the standard install locations) and runs:

```
draw.io -x -f <fmt> -o <tmp.ext> [-p N | -a] [-s scale] [--width/--height] [-b border] [-t] [--crop] [-e] [-q] in.drawio
```

### Verified quirks (draw.io 13.2.2)

| Behaviour | How the harness handles it |
|-----------|----------------------------|
| The output **extension** overrides `-f` | The backend renders to a temp file with the right extension, then moves it into place |
| `-f xml` silently writes a PDF | Not offered as an export format. Native XML comes from `project save` |
| `-g FROM..TO` always yields one page | Not exposed. Use `--all-pages` or `--page` |
| An out-of-range `-p` renders page 0 | The harness validates page references before calling draw.io |
| `-e` embeds the diagram as a PNG `zTXt` chunk keyed `mxGraphModel` | Allowed for PNG only |

Every export is checked after rendering: magic bytes, PNG dimensions, PDF page count, the SVG root element, and the VSDX ZIP structure.

## Rendering gap

None. Every style key, shape, layer and custom attribute lives in the native file, and draw.io renders that file itself, so nothing the CLI writes can be dropped at render time. The layout commands only rewrite `mxGeometry`.
