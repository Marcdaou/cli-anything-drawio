# cli-anything-drawio — Test Plan & Results

## Test Inventory Plan

| File | Layer | Planned tests |
|------|-------|---------------|
| `test_core.py` | Unit tests: synthetic data, no draw.io needed | ~55 |
| `test_full_e2e.py` | Native-file E2E, real draw.io render E2E, installed-CLI subprocess | ~30 |

## Unit Test Plan (`test_core.py`)

| Module | Functions | Edge cases | ~Count |
|--------|-----------|------------|-------|
| `project.py` | `new_document`, `load`, `save`, `info`, `compress_diagram`/`decompress_diagram`, `Document.page` | compressed pages written by real draw.io, bare `<mxGraphModel>` root, non-mxfile root, invalid XML, missing file, page lookup by index/name/id, out-of-range index, unknown page size, landscape swap | 14 |
| `styles.py` | `parse_style`, `format_style`, `apply_theme`, `parse_kv_pairs`, `validate_color` | bare tokens (`ellipse;`), values containing `=`, bad colors, missing `=`, unknown theme/shape/edge | 8 |
| `shapes.py` | `add_shape`, `list_cells`, `find_by_label`, `remove_cell`, `move`, `resize`, `relabel`, `set_style`, `set_data`, `duplicate`, `reorder`, `add_layer`, `set_layer_visible` | duplicate ids, non-positive size, cascading delete of attached edges and children, root/only-layer protection, mxCell→`<object>` conversion that keeps the geometry, connector passed as parent | 16 |
| `connectors.py` | `add_connector`, `reconnect`, `connectors_of` | unknown arrows, an edge or a missing id as endpoint, style options (dashed, color, width) | 5 |
| `pages.py` | `add_page`, `remove_page`, `rename_page`, `duplicate_page`, `move_page`, `set_page_props` | removing the last page, empty name, bad index, background `none` | 6 |
| `layout.py` | `align`, `distribute`, `grid_layout`, `line_layout`, `tree_layout` | fewer than 2 or 3 shapes, bad mode, cyclic graph without a root, horizontal tree | 6 |
| `session.py` | snapshot/undo/redo, `save_session` + sidecar reload, fingerprint mismatch drops stale history, `_locked_save_json`, history cap | nothing to undo/redo, no path to save to | 6 |
| `export.py` | `verify_output` on synthetic PNG, PDF, SVG and XML bytes | invalid magic | 2 |

## E2E Test Plan (`test_full_e2e.py`)

**Native files.** Build diagrams through the core API, save them, re-parse the XML and check the structure: `mxfile/diagram/mxGraphModel/root` exists, cells 0 and 1 are present, edges point at existing vertices, and IDs are unique. Also check that a compressed save round-trips.

**Real draw.io backend (required; no skipping).** Render each format through draw.io Desktop and verify:
- PNG: the magic bytes, the IHDR width and height (which must grow when the scale is 2x), and a transparent-background flag.
- PDF: `%PDF-` and the page count. With `--all-pages` on a 3-page document, the PDF must have 3 pages.
- SVG: the root is `<svg`, and the labels appear in the text.
- JPG: the magic bytes.
- XML: `<mxfile`.
- Page selection: rendering page 1 and page 0 must give different outputs.

Each test prints its artifact path.

**Installed CLI via `_resolve_cli("cli-anything-drawio")`.** Run with no `cwd`. Covers `--help`, `--version`, `--json` project new and info, auto-save after one-shot mutations, `--dry-run` not saving, undo persisting across processes, errors exiting non-zero with a JSON `{"error"}` body, the full pipeline through PNG and PDF, and preview capture writing a valid `preview-bundle/v1` with cache reuse.

## Realistic Workflow Scenarios

1. **Microservice architecture diagram**
   - Simulates: a backend engineer documenting a system.
   - Operations: new project → client, gateway, three services, two databases, queue → themed styles → connectors (dashed async edge) → tree layout → PNG and SVG.
   - Verified: every label is in the SVG text, the PNG dimensions are plausible, and there are 7 shapes and 7 connectors.
2. **Flowchart with decision branches**
   - Simulates: a process or onboarding flow.
   - Operations: start ellipse → process steps → diamond decision → yes/no labelled edges → column layout → align center → PDF.
   - Verified: the PDF has 1 page, and the edge labels are in the SVG.
3. **Multi-page document**
   - Simulates: a spec with overview and detail pages.
   - Operations: add, rename, duplicate and move pages → shapes on each page → per-page PNG → all-pages PDF.
   - Verified: the page order and the PDF page count.
4. **Open and edit a compressed draw.io file**
   - Simulates: editing a file saved by the GUI.
   - Operations: a compressed fixture → open → relabel → restyle → set custom data → save → re-open.
   - Verified: the edits persist and the `<object>` wrapper renders.
5. **Undo/redo stress and iterative refinement**
   - Operations: 30 mutations → undo all → redo all → add, remove and re-add.
   - Verified: the XML is identical to a known-good snapshot at each checkpoint.
6. **Agent one-shot pipeline (subprocess)**
   - Operations: a sequence of separate CLI processes with `--json` → export.
   - Verified: the JSON outputs parse, IDs chain from one command to the next, and the final PNG is valid.

---

## Test Results

Run on 2026-11-11 (macOS, Python 3.14, draw.io Desktop 13.2.2) with:

```
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/drawio/tests -v --tb=no
```

```
platform darwin -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0 -- .venv/bin/python3.14
cli_anything/drawio/tests/test_core.py::TestProject::test_new_document_structure PASSED [  1%]
cli_anything/drawio/tests/test_core.py::TestProject::test_new_document_page_size_landscape PASSED [  2%]
cli_anything/drawio/tests/test_core.py::TestProject::test_unknown_page_size PASSED [  3%]
cli_anything/drawio/tests/test_core.py::TestProject::test_compress_roundtrip PASSED [  4%]
cli_anything/drawio/tests/test_core.py::TestProject::test_decompress_drawio_style_payload PASSED [  5%]
cli_anything/drawio/tests/test_core.py::TestProject::test_save_load_plain PASSED [  6%]
cli_anything/drawio/tests/test_core.py::TestProject::test_save_load_compressed PASSED [  7%]
cli_anything/drawio/tests/test_core.py::TestProject::test_load_bare_model PASSED [  8%]
cli_anything/drawio/tests/test_core.py::TestProject::test_load_wrong_root PASSED [  9%]
cli_anything/drawio/tests/test_core.py::TestProject::test_load_invalid_xml PASSED [ 10%]
cli_anything/drawio/tests/test_core.py::TestProject::test_load_missing PASSED [ 11%]
cli_anything/drawio/tests/test_core.py::TestProject::test_page_lookup PASSED [ 13%]
cli_anything/drawio/tests/test_core.py::TestProject::test_page_lookup_errors PASSED [ 14%]
cli_anything/drawio/tests/test_core.py::TestProject::test_info_counts PASSED [ 15%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_parse_format_roundtrip PASSED [ 16%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_parse_bare_tokens_and_equals_in_value PASSED [ 17%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_parse_empty PASSED [ 18%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_apply_theme PASSED [ 19%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_unknown_theme_shape_edge PASSED [ 20%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_validate_color PASSED [ 21%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_parse_kv_pairs PASSED [ 22%]
cli_anything/drawio/tests/test_core.py::TestStyles::test_parse_kv_pairs_errors PASSED [ 23%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_add_defaults PASSED [ 25%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_add_theme_and_extra PASSED [ 26%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_add_duplicate_id PASSED [ 27%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_add_bad_size PASSED [ 28%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_add_into_container PASSED [ 29%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_parent_cannot_be_edge PASSED [ 30%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_list_and_kind_filter PASSED [ 31%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_find_by_label PASSED [ 32%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_remove_cascades PASSED [ 33%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_remove_protections PASSED [ 34%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_move_abs_and_rel PASSED [ 35%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_resize PASSED   [ 36%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_relabel_and_style PASSED [ 38%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_set_data_converts_to_object PASSED [ 39%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_duplicate PASSED [ 40%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_reorder PASSED  [ 41%]
cli_anything/drawio/tests/test_core.py::TestShapes::test_layers PASSED   [ 42%]
cli_anything/drawio/tests/test_core.py::TestConnectors::test_add PASSED  [ 43%]
cli_anything/drawio/tests/test_core.py::TestConnectors::test_bad_endpoints PASSED [ 44%]
cli_anything/drawio/tests/test_core.py::TestConnectors::test_bad_arrow PASSED [ 45%]
cli_anything/drawio/tests/test_core.py::TestConnectors::test_reconnect PASSED [ 46%]
cli_anything/drawio/tests/test_core.py::TestConnectors::test_connectors_of PASSED [ 47%]
cli_anything/drawio/tests/test_core.py::TestPages::test_add_list PASSED  [ 48%]
cli_anything/drawio/tests/test_core.py::TestPages::test_remove PASSED    [ 50%]
cli_anything/drawio/tests/test_core.py::TestPages::test_rename PASSED    [ 51%]
cli_anything/drawio/tests/test_core.py::TestPages::test_duplicate_is_deep PASSED [ 52%]
cli_anything/drawio/tests/test_core.py::TestPages::test_move PASSED      [ 53%]
cli_anything/drawio/tests/test_core.py::TestPages::test_set_props PASSED [ 54%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_align PASSED    [ 55%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_align_errors PASSED [ 56%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_distribute PASSED [ 57%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_grid_row_column PASSED [ 58%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_tree PASSED     [ 59%]
cli_anything/drawio/tests/test_core.py::TestLayout::test_tree_cycle_needs_root PASSED [ 60%]
cli_anything/drawio/tests/test_core.py::TestSession::test_undo_redo PASSED [ 61%]
cli_anything/drawio/tests/test_core.py::TestSession::test_new_snapshot_clears_redo PASSED [ 63%]
cli_anything/drawio/tests/test_core.py::TestSession::test_history_cap PASSED [ 64%]
cli_anything/drawio/tests/test_core.py::TestSession::test_save_and_sidecar_reload PASSED [ 65%]
cli_anything/drawio/tests/test_core.py::TestSession::test_stale_sidecar_ignored PASSED [ 66%]
cli_anything/drawio/tests/test_core.py::TestSession::test_locked_save_json_and_require PASSED [ 67%]
cli_anything/drawio/tests/test_core.py::TestVerify::test_png_pdf_svg PASSED [ 68%]
cli_anything/drawio/tests/test_core.py::TestVerify::test_invalid PASSED  [ 69%]
cli_anything/drawio/tests/test_full_e2e.py::TestNativeFile::test_structure_integrity PASSED [ 70%]
cli_anything/drawio/tests/test_full_e2e.py::TestNativeFile::test_compressed_roundtrip PASSED [ 71%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_drawio_installed PASSED [ 72%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_png PASSED [ 73%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_png_scale_doubles PASSED [ 75%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_png_transparent PASSED [ 76%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_png_embed_diagram PASSED [ 77%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_svg_contains_labels PASSED [ 78%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_pdf_single_and_all_pages PASSED [ 79%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_jpg PASSED [ 80%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_vsdx PASSED [ 81%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_page_selection_differs PASSED [ 82%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_errors PASSED [ 83%]
cli_anything/drawio/tests/test_full_e2e.py::TestBackend::test_extension_mismatch_respects_format PASSED [ 84%]
cli_anything/drawio/tests/test_full_e2e.py::TestWorkflows::test_flowchart_pdf PASSED [ 85%]
cli_anything/drawio/tests/test_full_e2e.py::TestWorkflows::test_multipage_spec PASSED [ 86%]
cli_anything/drawio/tests/test_full_e2e.py::TestWorkflows::test_edit_gui_compressed_file PASSED [ 88%]
cli_anything/drawio/tests/test_full_e2e.py::TestWorkflows::test_undo_redo_stress PASSED [ 89%]
cli_anything/drawio/tests/test_full_e2e.py::TestWorkflows::test_preview_bundle PASSED [ 90%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_help PASSED [ 91%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_version PASSED [ 92%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_project_new_json PASSED [ 93%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_autosave_dryrun_undo PASSED [ 94%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_errors_exit_nonzero_with_json PASSED [ 95%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_full_agent_pipeline PASSED [ 96%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_preview_cli PASSED [ 97%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_export_check PASSED [ 98%]
cli_anything/drawio/tests/test_full_e2e.py::TestCLISubprocess::test_repl_scripted PASSED [100%]
======================== 92 passed in 107.60s (0:01:47) ========================
```

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total tests | 92 (64 unit, 28 E2E) |
| Passed | 92 (100%) |
| Execution time | ~108 s; almost all of it is draw.io Desktop start-up, about 3–5 s per render |
| Backend | Real draw.io Desktop for every PNG, SVG, PDF, JPG and VSDX artifact |
| CLI resolution | The installed `cli-anything-drawio`, forced with `CLI_ANYTHING_FORCE_INSTALLED=1` |

## Coverage Notes

- **Output checks.** Each render is verified by its magic bytes, PNG IHDR dimensions, the alpha channel decoded pixel by pixel (transparency), PDF page counts, label text inside the SVG, the VSDX ZIP layout, and the embedded-diagram `zTXt` chunk.
- **Backend quirks found while testing** (see `DRAWIO.md`). `-f xml` writes a PDF, and `-g` page ranges always produce one page. Neither is exposed. The output extension overrides `-f`; the backend works around it with a temporary file name.
- **Gaps:**
  - No round-trip check opens the generated files in the draw.io GUI. The structural XML tests and draw.io's own headless renderer stand in for it.
  - The REPL is tested through a piped stdin script. Interactive prompt_toolkit features such as history and colours are not tested.
  - Linux and Windows paths in `find_drawio` are not exercised on this machine.
  - Previews implement static `capture`/`latest` only. There is no `preview live` or `preview diff`.
