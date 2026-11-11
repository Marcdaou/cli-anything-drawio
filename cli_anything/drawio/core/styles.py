"""mxGraph style strings, shape presets and color themes.

Presets are copied from draw.io's own sidebar (src/main/webapp/js/grapheditor/Sidebar.js)
so shapes created by this CLI are identical to those dragged from the GUI palette.
"""

import re

from .project import DrawioError

# name -> (style, default width, default height)
SHAPES = {
    "rectangle":     ("rounded=0;whiteSpace=wrap;html=1;", 120, 60),
    "rounded":       ("rounded=1;whiteSpace=wrap;html=1;", 120, 60),
    "ellipse":       ("ellipse;whiteSpace=wrap;html=1;", 120, 80),
    "circle":        ("ellipse;whiteSpace=wrap;html=1;aspect=fixed;", 80, 80),
    "diamond":       ("rhombus;whiteSpace=wrap;html=1;", 80, 80),
    "triangle":      ("triangle;whiteSpace=wrap;html=1;", 60, 80),
    "hexagon":       ("shape=hexagon;perimeter=hexagonPerimeter2;whiteSpace=wrap;html=1;fixedSize=1;", 120, 80),
    "parallelogram": ("shape=parallelogram;perimeter=parallelogramPerimeter;whiteSpace=wrap;html=1;fixedSize=1;", 120, 60),
    "trapezoid":     ("shape=trapezoid;perimeter=trapezoidPerimeter;whiteSpace=wrap;html=1;fixedSize=1;", 120, 60),
    "cylinder":      ("shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;", 60, 80),
    "cloud":         ("ellipse;shape=cloud;whiteSpace=wrap;html=1;", 120, 80),
    "document":      ("shape=document;whiteSpace=wrap;html=1;boundedLbl=1;", 120, 80),
    "process":       ("shape=process;whiteSpace=wrap;html=1;backgroundOutline=1;", 120, 60),
    "step":          ("shape=step;perimeter=stepPerimeter;whiteSpace=wrap;html=1;fixedSize=1;", 120, 80),
    "note":          ("shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;darkOpacity=0.05;", 80, 100),
    "card":          ("shape=card;whiteSpace=wrap;html=1;", 80, 100),
    "actor":         ("shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;", 30, 60),
    "double-ellipse": ("ellipse;shape=doubleEllipse;whiteSpace=wrap;html=1;", 100, 60),
    "arrow":         ("shape=singleArrow;whiteSpace=wrap;html=1;", 100, 60),
    "text":          ("text;html=1;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;", 60, 30),
    "container":     ("swimlane;whiteSpace=wrap;html=1;", 200, 200),
    "swimlane":      ("swimlane;horizontal=0;whiteSpace=wrap;html=1;", 400, 150),
}

# name -> style for connectors
EDGES = {
    "orthogonal": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;",
    "rounded":    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;",
    "straight":   "endArrow=classic;html=1;",
    "curved":     "edgeStyle=orthogonalEdgeStyle;curved=1;orthogonalLoop=1;jettySize=auto;html=1;",
    "elbow":      "edgeStyle=elbowEdgeStyle;elbow=horizontal;html=1;",
    "entity":     "edgeStyle=entityRelationEdgeStyle;fontSize=12;html=1;endArrow=ERmany;startArrow=ERone;",
    "isometric":  "edgeStyle=isometricEdgeStyle;endArrow=none;html=1;",
}

ARROWS = ("classic", "classicThin", "block", "blockThin", "open", "openThin", "oval",
          "diamond", "diamondThin", "box", "halfCircle", "dash", "cross", "circle",
          "circlePlus", "async", "openAsync", "ERone", "ERmany", "ERmandOne",
          "ERoneToMany", "ERzeroToOne", "ERzeroToMany", "none")

# draw.io's default palette (Format panel "quick colors")  name -> (fill, stroke)
THEMES = {
    "blue":   ("#dae8fc", "#6c8ebf"),
    "green":  ("#d5e8d4", "#82b366"),
    "orange": ("#ffe6cc", "#d79b00"),
    "yellow": ("#fff2cc", "#d6b656"),
    "red":    ("#f8cecc", "#b85450"),
    "purple": ("#e1d5e7", "#9673a6"),
    "gray":   ("#f5f5f5", "#666666"),
    "dark":   ("#647687", "#314354"),
    "white":  ("#ffffff", "#000000"),
}

_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|none|default)$")


def parse_style(style: str | None) -> dict:
    """'rounded=1;html=1;ellipse;' -> {'rounded':'1','html':'1','ellipse':None}.

    Bare tokens (e.g. 'ellipse', 'text', 'swimlane') are base-style names; kept with value None.
    """
    out = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        else:
            out[part] = None
    return out


def format_style(d: dict) -> str:
    parts = []
    for k, v in d.items():
        parts.append(k if v is None else f"{k}={v}")
    return ";".join(parts) + (";" if parts else "")


def validate_color(c: str) -> str:
    if not _COLOR_RE.match(c):
        raise DrawioError(f"Invalid color '{c}'. Use #RGB, #RRGGBB, 'none' or 'default'")
    return c


def shape_style(shape: str) -> tuple:
    if shape not in SHAPES:
        raise DrawioError(f"Unknown shape '{shape}'. Choose: {', '.join(SHAPES)}")
    return SHAPES[shape]


def edge_style(kind: str) -> str:
    if kind not in EDGES:
        raise DrawioError(f"Unknown connector style '{kind}'. Choose: {', '.join(EDGES)}")
    return EDGES[kind]


def apply_theme(style: dict, theme: str) -> dict:
    if theme not in THEMES:
        raise DrawioError(f"Unknown theme '{theme}'. Choose: {', '.join(THEMES)}")
    fill, stroke = THEMES[theme]
    style["fillColor"] = fill
    style["strokeColor"] = stroke
    return style


def parse_kv_pairs(pairs) -> dict:
    """['fillColor=#fff', 'dashed=1'] -> dict. Validates obvious color keys."""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise DrawioError(f"Style property must be key=value, got '{p}'")
        k, v = p.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            raise DrawioError(f"Empty style key in '{p}'")
        if k.lower().endswith("color") and v:
            validate_color(v)
        out[k] = v
    return out
