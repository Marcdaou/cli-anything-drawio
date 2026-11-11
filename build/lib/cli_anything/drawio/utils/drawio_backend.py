"""Backend: invokes the real draw.io Desktop application for rendering/export.

draw.io Desktop (Electron) ships a headless export mode:
    draw.io -x -f <pdf|png|jpg|svg|vsdx> -o <out> [options] <input.drawio>

Quirks handled here (observed with draw.io 13.x):
  * The output *extension* wins over -f, so we always render to a temp name with the
    right extension and move it into place.
  * '-f xml' is not supported and silently emits a PDF; native XML is written by
    `project save` instead.
  * An out-of-range -p silently renders page 0; callers validate page indices first.
  * '-g FROM..TO' (PDF page range) always yields a single page, so it is not exposed.
"""

import os
import shutil
import subprocess

EXPORT_FORMATS = ("png", "svg", "pdf", "jpg", "vsdx")

_CANDIDATES = [
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    os.path.expanduser("~/Applications/draw.io.app/Contents/MacOS/draw.io"),
    "/opt/drawio/drawio",
    "/usr/bin/drawio",
    "/snap/bin/drawio",
    r"C:\Program Files\draw.io\draw.io.exe",
]

INSTALL_HINT = (
    "draw.io Desktop is required but was not found.\n"
    "  macOS:   brew install --cask drawio\n"
    "  Linux:   https://github.com/jgraph/drawio-desktop/releases (deb/rpm/AppImage/snap)\n"
    "  Windows: https://github.com/jgraph/drawio-desktop/releases\n"
    "Or set DRAWIO_BIN=/path/to/draw.io"
)


def find_drawio() -> str:
    """Locate the draw.io executable or raise RuntimeError with install help."""
    env = os.environ.get("DRAWIO_BIN")
    if env:
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env
        raise RuntimeError(f"DRAWIO_BIN={env} is not an executable file.\n" + INSTALL_HINT)
    for name in ("drawio", "draw.io"):
        p = shutil.which(name)
        if p:
            return p
    for p in _CANDIDATES:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    raise RuntimeError(INSTALL_HINT)


def version() -> str:
    exe = find_drawio()
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    return lines[-1] if lines else "unknown"


def export(input_path: str, output_path: str, fmt: str = "png", page_index: int | None = None,
           all_pages: bool = False, scale: float | None = None, width: int | None = None,
           height: int | None = None, border: int | None = None, transparent: bool = False,
           crop: bool = False, embed_diagram: bool = False, quality: int | None = None,
           timeout: int = 180) -> dict:
    """Render a .drawio file with the real draw.io Desktop. Returns a result dict."""
    fmt = fmt.lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported format '{fmt}'. Choose from: {', '.join(EXPORT_FORMATS)}")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input diagram not found: {input_path}")
    exe = find_drawio()
    out_abs = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)

    tmp_out = os.path.join(os.path.dirname(out_abs),
                           f".{os.path.basename(out_abs)}.{os.getpid()}.render.{fmt}")
    cmd = [exe, "-x", "-f", fmt, "-o", tmp_out]
    if all_pages:
        if fmt != "pdf":
            raise ValueError("--all-pages is only supported for pdf export")
        cmd.append("-a")
    elif page_index is not None:
        cmd += ["-p", str(int(page_index))]
    if scale is not None:
        cmd += ["-s", str(scale)]
    if width is not None:
        cmd += ["--width", str(int(width))]
    if height is not None:
        cmd += ["--height", str(int(height))]
    if border is not None:
        cmd += ["-b", str(int(border))]
    if transparent:
        if fmt != "png":
            raise ValueError("--transparent is only supported for png export")
        cmd.append("-t")
    if crop:
        cmd.append("--crop")
    if embed_diagram:
        if fmt != "png":
            raise ValueError("--embed-diagram is only supported for png export")
        cmd.append("-e")
    if quality is not None:
        cmd += ["-q", str(int(quality))]
    cmd.append(os.path.abspath(input_path))

    # Electron needs --no-sandbox when running as root (e.g. CI containers)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.insert(1, "--no-sandbox")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"draw.io export timed out after {timeout}s")
    if os.path.isfile(tmp_out) and os.path.getsize(tmp_out) > 0:
        os.replace(tmp_out, out_abs)
    else:
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        raise RuntimeError(
            f"draw.io export failed (exit {r.returncode}).\n"
            f"stdout: {r.stdout.strip()}\nstderr: {r.stderr.strip()}")
    return {
        "output": out_abs,
        "format": fmt,
        "file_size": os.path.getsize(out_abs),
        "method": "drawio-desktop-headless",
        "command": cmd,
    }
