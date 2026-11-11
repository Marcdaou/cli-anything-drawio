"""preview-bundle/v1 producer. Artifacts are rendered by real draw.io Desktop.

Bundles live in <project_dir>/.cli-anything/previews/drawio/<recipe>/<bundle_id>/.
View them with `cli-hub previews inspect|html|open <bundle_dir>`.
"""

import datetime as dt
import glob
import hashlib
import json
import os

from . import project as P
from .export import render

PROTOCOL = "preview-bundle/v1"
HARNESS_VERSION = "1.0.0"

RECIPES = {
    "quick":  {"description": "Current page as PNG at 1x scale", "scale": 1.0, "pages": "current"},
    "hires":  {"description": "Current page as PNG at 2x scale", "scale": 2.0, "pages": "current"},
    "pages":  {"description": "One PNG per page (gallery)", "scale": 1.0, "pages": "all"},
}


def _root(project_path):
    if project_path:
        return os.path.join(os.path.dirname(os.path.abspath(project_path)), ".cli-anything", "previews", "drawio")
    return os.path.expanduser("~/.cli-anything/previews/drawio")


def capture(doc: P.Document, project_path=None, recipe="quick", page=None, command=None,
            force=False) -> dict:
    if recipe not in RECIPES:
        raise P.DrawioError(f"Unknown recipe '{recipe}'. Choose: {', '.join(RECIPES)}")
    r = RECIPES[recipe]
    fp = doc.fingerprint()
    page_obj = doc.page(page)
    key = hashlib.sha256(f"{fp}|{recipe}|{doc.page_index(page_obj)}|{HARNESS_VERSION}|{PROTOCOL}".encode()).hexdigest()[:8]
    base = os.path.join(_root(project_path), recipe)
    if not force:
        for existing in sorted(glob.glob(os.path.join(base, f"*_{key}_{recipe}"))):
            mp = os.path.join(existing, "manifest.json")
            if os.path.isfile(mp):
                return _result(existing, cached=True)
    now = dt.datetime.now(dt.timezone.utc)
    bundle_id = f"{now:%Y%m%dT%H%M%SZ}_{key}_{recipe}"
    bdir = os.path.join(base, bundle_id)
    os.makedirs(os.path.join(bdir, "artifacts"), exist_ok=True)

    targets = list(enumerate(doc.pages)) if r["pages"] == "all" else [(doc.page_index(page_obj), page_obj)]
    artifacts = []
    for n, (idx, pg) in enumerate(targets):
        rel = f"artifacts/{'hero' if n == 0 else f'page_{idx:02d}'}.png"
        res = render(doc, os.path.join(bdir, rel), "png", page=idx, scale=r["scale"], border=10,
                     overwrite=True)
        v = res["verification"]
        artifacts.append({"artifact_id": "hero" if n == 0 else f"page_{idx}", "role": "hero" if n == 0 else "gallery",
                          "kind": "image", "label": f"Page {idx}: {pg.get('name')}",
                          "media_type": "image/png", "path": rel, "width": v.get("width"),
                          "height": v.get("height"), "bytes": res["file_size"]})
    info = P.info(doc, project_path)
    manifest = {
        "protocol_version": PROTOCOL, "bundle_id": bundle_id, "bundle_kind": "capture",
        "software": "drawio", "recipe": recipe, "status": "ok",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {"entry_point": "cli-anything-drawio", "harness_version": HARNESS_VERSION,
                      "command": command, "backend": "draw.io desktop (headless -x export)"},
        "source": {"project_path": os.path.abspath(project_path) if project_path else None,
                   "project_fingerprint": fp},
        "context": {"page_index": doc.page_index(page_obj), "page_name": page_obj.get("name")},
        "metrics": {"pages": info["page_count"], "shapes": info["total_shapes"],
                    "connectors": info["total_connectors"]},
        "summary_path": "summary.json", "artifacts": artifacts,
    }
    summary = {
        "headline": f"Rendered {len(artifacts)} page image(s) with draw.io ({recipe})",
        "facts": {"recipe": recipe, "pages": info["page_count"], "shapes": info["total_shapes"],
                  "connectors": info["total_connectors"],
                  "hero_size": f"{artifacts[0]['width']}x{artifacts[0]['height']}"},
        "warnings": [],
        "next_actions": ["Inspect hero.png for overlaps or clipped labels",
                         "Run 'export render' for final output once layout looks right"],
    }
    with open(os.path.join(bdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(bdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return _result(bdir, cached=False)


def latest(project_path=None, recipe=None) -> dict:
    pattern = os.path.join(_root(project_path), recipe or "*", "*", "manifest.json")
    found = sorted(glob.glob(pattern), key=lambda p: os.path.basename(os.path.dirname(p)))
    if not found:
        raise P.DrawioError("No preview bundles yet. Run 'preview capture' first.")
    return _result(os.path.dirname(found[-1]), cached=True)


def _result(bdir, cached) -> dict:
    with open(os.path.join(bdir, "manifest.json")) as f:
        m = json.load(f)
    return {"_bundle_dir": bdir, "_manifest_path": os.path.join(bdir, "manifest.json"),
            "summary_path": os.path.join(bdir, "summary.json"), "bundle_id": m["bundle_id"],
            "recipe": m["recipe"], "cached": cached, "status": m["status"],
            "artifacts": [dict(a, abs_path=os.path.join(bdir, a["path"])) for a in m["artifacts"]],
            "viewer_hints": {"inspect": f"cli-hub previews inspect {bdir}",
                             "html": f"cli-hub previews html {bdir}",
                             "open": f"cli-hub previews open {bdir}"}}
