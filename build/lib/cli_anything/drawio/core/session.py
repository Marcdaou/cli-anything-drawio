"""Stateful session: current document, file path, undo/redo history.

The project file itself is the native .drawio file. Undo history persists across
one-shot invocations in a sidecar JSON next to it: `.<name>.drawio-session.json`.
"""

import json
import os
import time

from . import project as P

MAX_HISTORY = 50


def _locked_save_json(path, data, **dump_kwargs) -> None:
    """Atomically write JSON with exclusive file locking."""
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")
    with f:
        _locked = False
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def sidecar_path(project_path: str) -> str:
    d, n = os.path.split(os.path.abspath(project_path))
    return os.path.join(d, f".{n}.drawio-session.json")


class Session:
    def __init__(self):
        self.doc: P.Document | None = None
        self.project_path: str | None = None
        self.undo_stack: list = []   # [(label, xml)]
        self.redo_stack: list = []
        self.current_page = None      # page ref (index/name/id) or None
        self._modified = False
        self.compressed = False

    # lifecycle
    def has_project(self) -> bool:
        return self.doc is not None

    def require(self) -> P.Document:
        if self.doc is None:
            raise P.DrawioError("No diagram open. Use 'project new -o FILE' or 'project open FILE' "
                                "(or pass --project FILE).")
        return self.doc

    def set_project(self, doc: P.Document, path: str | None):
        self.doc = doc
        self.project_path = os.path.abspath(path) if path else None
        self.undo_stack, self.redo_stack = [], []
        self.current_page = None
        self._modified = False
        self._load_sidecar()

    def open(self, path: str):
        self.set_project(P.load(path), path)
        return self.doc

    def close(self):
        self.__init__()

    # history
    def snapshot(self, label: str):
        doc = self.require()
        self.undo_stack.append((label, doc.to_xml()))
        self.undo_stack = self.undo_stack[-MAX_HISTORY:]
        self.redo_stack.clear()
        self._modified = True

    def undo(self) -> str:
        doc = self.require()
        if not self.undo_stack:
            raise P.DrawioError("Nothing to undo")
        label, xml = self.undo_stack.pop()
        self.redo_stack.append((label, doc.to_xml()))
        self.doc = P.from_xml(xml)
        self._modified = True
        return label

    def redo(self) -> str:
        doc = self.require()
        if not self.redo_stack:
            raise P.DrawioError("Nothing to redo")
        label, xml = self.redo_stack.pop()
        self.undo_stack.append((label, doc.to_xml()))
        self.doc = P.from_xml(xml)
        self._modified = True
        return label

    def history(self) -> dict:
        return {"undo": [l for l, _ in self.undo_stack], "redo": [l for l, _ in self.redo_stack]}

    def page(self, ref=None):
        return self.require().page(ref if ref is not None else self.current_page)

    # persistence
    def save_session(self, path: str | None = None, compressed: bool | None = None) -> dict:
        doc = self.require()
        path = path or self.project_path
        if not path:
            raise P.DrawioError("No output path. Use 'project save -o FILE'.")
        if compressed is not None:
            self.compressed = compressed
        res = P.save(doc, path, compressed=self.compressed)
        self.project_path = os.path.abspath(path)
        _locked_save_json(sidecar_path(path), {
            "version": 1, "saved_at": time.time(), "project": self.project_path,
            "current_page": self.current_page,
            "undo": self.undo_stack, "redo": self.redo_stack,
            "fingerprint": doc.fingerprint(),
        })
        self._modified = False
        return res

    def _load_sidecar(self):
        if not self.project_path:
            return
        sp = sidecar_path(self.project_path)
        if not os.path.isfile(sp):
            return
        try:
            with open(sp) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        # only trust history if it was written for the file as it is now
        if data.get("fingerprint") != self.doc.fingerprint():
            return
        self.undo_stack = [tuple(x) for x in data.get("undo", [])]
        self.redo_stack = [tuple(x) for x in data.get("redo", [])]
        self.current_page = data.get("current_page")

    def status(self) -> dict:
        d = {"project": self.project_path, "open": self.has_project(), "modified": self._modified,
             "undo_depth": len(self.undo_stack), "redo_depth": len(self.redo_stack),
             "current_page": None}
        if self.doc is not None:
            p = self.page()
            d["current_page"] = {"index": self.doc.page_index(p), "name": p.get("name")}
            d["page_count"] = len(self.doc.pages)
        return d


_session: Session | None = None


def get_session() -> Session:
    global _session
    if _session is None:
        _session = Session()
    return _session


def reset_session():
    global _session
    _session = None
