"""Color themes: single source of truth + shared stylesheet builders.

Previously the THEMES dict and apply_theme methods were duplicated across
~15 widget classes (model_selector_panels, chat_ai_helper, mcp_panel,
external_search_panel, uieg_capture_panel). This module owns the palette data
and the common QSS fragments so every panel stays in sync.

Palettes carry a three-step background ramp (``bg`` / ``bg2`` / ``bg3``) plus
explicit ``text`` / ``muted`` and semantic ``good`` / ``warn`` / ``bad`` roles,
so panels never have to invent their own colors. ``on_accent`` is derived from
each accent's luminance, which is what keeps label text legible on top of
accent-filled buttons, tabs, and dock titles regardless of palette.

Legacy keys (``fg``, ``panel_bg``, ``accent_hover``) are generated aliases; the
suite still reads them in a dozen modules, so they cannot be dropped without a
sweep, and generating them keeps them from drifting out of sync.
"""

from __future__ import annotations

from typing import Any, Dict

# Raw palettes. Keys: bg/bg2/bg3 (background ramp), text, muted, accent,
# accent2 (hover / brighter accent), border, good, warn, bad.
_BASE_THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#1e1e2e", "bg2": "#27293d", "bg3": "#2f3147",
        "text": "#e0e0ff", "muted": "#9a9ab0", "accent": "#4f8cff",
        "accent2": "#7aa2f7", "border": "#3a3d55", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "tng": {
        "bg": "#0f1a24", "bg2": "#14232f", "bg3": "#1a2d3d",
        "text": "#cfe6f0", "muted": "#7fa8bf", "accent": "#4aa3cf",
        "accent2": "#7cc4e0", "border": "#244459", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "tos": {
        "bg": "#17100a", "bg2": "#201710", "bg3": "#291d13",
        "text": "#f2e3c4", "muted": "#c8a97a", "accent": "#c9893c",
        "accent2": "#e0a45e", "border": "#4a341c", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "voyager": {
        "bg": "#101525", "bg2": "#151b2e", "bg3": "#1b2236",
        "text": "#d7def5", "muted": "#8a93b8", "accent": "#7a6fd0",
        "accent2": "#9b91e8", "border": "#2c3560", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "ds9": {
        "bg": "#1a1610", "bg2": "#221c14", "bg3": "#2b2319",
        "text": "#e8dcc4", "muted": "#a7956f", "accent": "#d4a24a",
        "accent2": "#e6bf6e", "border": "#453829", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "enterprise": {
        "bg": "#0c1218", "bg2": "#111a24", "bg3": "#17232f",
        "text": "#c8d6e0", "muted": "#77909f", "accent": "#3d9fe0",
        "accent2": "#6fc0ee", "border": "#1f3545", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "discovery": {
        "bg": "#161318", "bg2": "#1d1920", "bg3": "#26212a",
        "text": "#e8d8d0", "muted": "#a08a80", "accent": "#c0392b",
        "accent2": "#d9604f", "border": "#3c2a26", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    "picard": {
        "bg": "#101418", "bg2": "#151b21", "bg3": "#1c242c",
        "text": "#d4dde6", "muted": "#8897a8", "accent": "#6a9fd8",
        "accent2": "#8fbbe8", "border": "#2a3745", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
    # accent2 darkens rather than lightens here: on a white ground the mock-up's
    # paler #7a90f9 fell to 2.92:1, too washed out for header and tab labels.
    "light": {
        "bg": "#f5f6fa", "bg2": "#ffffff", "bg3": "#eef0f6",
        "text": "#20242e", "muted": "#6b7280", "accent": "#4f6ef7",
        "accent2": "#3b55d9", "border": "#d6dae5", "good": "#16a34a",
        "warn": "#b45309", "bad": "#dc2626",
    },
    "amber": {
        "bg": "#1a1a10", "bg2": "#232318", "bg3": "#2c2c1e",
        "text": "#f0e6c0", "muted": "#a8a06a", "accent": "#e8b839",
        "accent2": "#f5cf66", "border": "#4a431c", "good": "#7ee787",
        "warn": "#ffb86c", "bad": "#ff6b6b",
    },
}

_ON_DARK = "#0b0b0f"
_ON_LIGHT = "#ffffff"


def _channels(hex_color: str) -> tuple:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance in 0..1."""
    out = []
    for raw in _channels(hex_color):
        c = raw / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colors (1.0 = identical, 21 = max)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(background: str) -> str:
    """Pick near-black or white for text drawn on `background`."""
    if contrast_ratio(_ON_DARK, background) >= contrast_ratio(_ON_LIGHT, background):
        return _ON_DARK
    return _ON_LIGHT


def _expand(base: Dict[str, str]) -> Dict[str, str]:
    """Add derived + legacy-alias keys to a raw palette."""
    theme = dict(base)
    # Text drawn on an accent fill: chosen for contrast, not for the palette's
    # own text color, which is tuned for the window background instead.
    theme["on_accent"] = readable_on(base["accent"])
    theme["on_accent2"] = readable_on(base["accent2"])
    # Legacy aliases still read across the suite.
    theme["fg"] = base["text"]
    theme["panel_bg"] = base["bg2"]
    theme["accent_hover"] = base["accent2"]
    return theme


THEMES: Dict[str, Dict[str, str]] = {
    name: _expand(base) for name, base in _BASE_THEMES.items()
}


def theme_by_name(name: str) -> Dict[str, str]:
    """Palette lookup that never raises; unknown names fall back to dark."""
    return THEMES.get(name) or THEMES["dark"]


def main_stylesheet(theme: Dict[str, str]) -> str:
    """QSS for the main window frame (docks, toolbar, inputs)."""
    return f"""
        QMainWindow {{
            background-color: {theme['bg']};
            color: {theme['text']};
        }}
        QDockWidget {{
            background-color: {theme['bg2']};
            color: {theme['text']};
            border: 1px solid {theme['border']};
        }}
        QDockWidget::title {{
            background-color: {theme['accent']};
            color: {theme['on_accent']};
            padding: 5px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QSplitter::handle {{
            background-color: {theme['border']};
            width: 8px;
            height: 8px;
        }}
        QSplitter::handle:hover {{
            background-color: {theme['accent']};
        }}
        QFrame#SuiteNavPane, QFrame#SuiteToolsPane {{
            background-color: {theme['bg2']};
            border: 1px solid {theme['border']};
        }}
        QLabel#SuitePaneTitle {{
            background-color: {theme['accent']};
            color: {theme['on_accent']};
            padding: 6px 8px;
            font-weight: bold;
        }}
        QStatusBar {{
            background-color: {theme['bg2']};
            color: {theme['text']};
            border-top: 1px solid {theme['border']};
        }}
        QToolBar {{
            background-color: {theme['bg2']};
            border-bottom: 1px solid {theme['border']};
        }}
        QToolButton {{
            color: {theme['text']};
            background-color: transparent;
            padding: 4px 8px;
            border-radius: 4px;
        }}
        QToolButton:hover {{
            background-color: {theme['accent2']};
            color: {theme['on_accent2']};
        }}
        QComboBox, QLineEdit, QSpinBox {{
            background-color: {theme['bg']};
            color: {theme['text']};
            border: 1px solid {theme['border']};
            padding: 5px;
            border-radius: 4px;
        }}
        QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{
            border-color: {theme['accent']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {theme['bg2']};
            color: {theme['text']};
            selection-background-color: {theme['accent']};
            selection-color: {theme['on_accent']};
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QScrollArea {{
            border: none;
            background-color: {theme['bg2']};
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: {theme['bg2']};
        }}
    """


def widget_stylesheet(theme: Dict[str, str]) -> str:
    """QSS for a plain widget container (background + text color)."""
    return f"""
        QWidget {{
            background-color: {theme['bg']};
            color: {theme['text']};
        }}
    """


def base_controls_stylesheet(theme: Dict[str, str]) -> str:
    """QSS for editors, buttons, and labels (dialogs/panels)."""
    return f"""
        QTextEdit, QPlainTextEdit {{
            background-color: {theme['bg2']};
            color: {theme['text']};
            border: 1px solid {theme['border']};
            border-radius: 4px;
            selection-background-color: {theme['accent']};
            selection-color: {theme['on_accent']};
        }}
        QPushButton {{
            background-color: {theme['accent']};
            color: {theme['on_accent']};
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {theme['accent2']};
            color: {theme['on_accent2']};
        }}
        QPushButton:disabled {{
            background-color: {theme['bg3']};
            color: {theme['muted']};
        }}
        QLabel {{
            color: {theme['text']};
            background-color: transparent;
        }}
    """


def dialog_stylesheet(theme: Dict[str, str]) -> str:
    """QSS for dialogs with lists/grids + buttons."""
    return f"""
        QDialog {{
            background-color: {theme['bg']};
            color: {theme['text']};
        }}
        QListWidget, QTreeWidget, QTableWidget {{
            background-color: {theme['bg2']};
            color: {theme['text']};
            border: 1px solid {theme['border']};
            border-radius: 4px;
            alternate-background-color: {theme['bg3']};
            gridline-color: {theme['border']};
        }}
        QListWidget::item:selected, QTreeWidget::item:selected,
        QTableWidget::item:selected {{
            background-color: {theme['accent']};
            color: {theme['on_accent']};
        }}
        QHeaderView::section {{
            background-color: {theme['bg3']};
            color: {theme['accent2']};
            border: none;
            border-bottom: 1px solid {theme['border']};
            padding: 6px;
        }}
        {base_controls_stylesheet(theme)}
    """


def tabs_stylesheet(theme: Dict[str, str]) -> str:
    """QSS for tabbed panels; selected tabs stay legible on the accent fill."""
    return f"""
        QTabWidget::pane {{
            border: 1px solid {theme['border']};
            background: {theme['bg2']};
        }}
        QTabBar::tab {{
            background: {theme['bg2']};
            color: {theme['muted']};
            padding: 8px 14px;
            margin-right: 2px;
            border: 1px solid {theme['border']};
        }}
        QTabBar::tab:selected {{
            background: {theme['accent']};
            color: {theme['on_accent']};
            font-weight: bold;
        }}
        QTabBar::tab:hover:!selected {{
            color: {theme['text']};
        }}
    """


def apply_theme_to(widget: Any, theme: Dict[str, str], scope: str = "auto") -> None:
    """Set a widget's stylesheet from the shared builders.

    scope: 'auto' picks the stylesheet by widget type; 'main' forces the main
    window sheet; 'dialog' forces the dialog sheet; 'widget' the plain sheet.
    """
    if scope == "main":
        css = main_stylesheet(theme)
    elif scope == "dialog":
        css = dialog_stylesheet(theme)
    elif scope == "widget":
        css = widget_stylesheet(theme)
    else:
        cls = widget.__class__.__name__
        if cls in ("QMainWindow", "MainWindow"):
            css = main_stylesheet(theme)
        elif cls in ("QDialog",) or cls.endswith("Dialog"):
            css = dialog_stylesheet(theme)
        else:
            css = widget_stylesheet(theme) + base_controls_stylesheet(theme)
    widget.setStyleSheet(css)
