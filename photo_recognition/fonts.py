"""System font detection so the Tk UI follows the desktop font."""
import configparser
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font

UI_FONT_PREFERENCE = (
    'Cantarell', 'Ubuntu Sans', 'Ubuntu', 'Noto Sans', 'Source Sans 3', 'DejaVu Sans',
    'Liberation Sans', 'Segoe UI', 'SF Pro Text', 'Helvetica Neue', 'Arial',
)
MONO_FONT_PREFERENCE = (
    'JetBrains Mono', 'Cascadia Mono', 'Cascadia Code', 'Ubuntu Mono', 'Noto Sans Mono',
    'Source Code Pro', 'DejaVu Sans Mono', 'Liberation Mono', 'Consolas', 'Menlo', 'monospace',
)
NAMED_FONTS = (
    'TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'TkMenuFont', 'TkCaptionFont',
    'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont', 'TkFixedFont',
)


def _normalize(name):
    return re.sub(r'\s+', '', name).casefold()


def _match_family(candidate, families):
    key = _normalize(candidate or '')
    if not key:
        return None
    for family in families:
        normalized = _normalize(family)
        if normalized == key or key in normalized or normalized in key:
            return family
    return None


def _parse_font_description(text):
    """Parse 'Cantarell 11' style descriptions into (family, size)."""
    text = text.strip().strip("'\"")
    match = re.match(r'^(.*?)[,\s]+(\d+(?:\.\d+)?)\s*$', text)
    if match:
        return match.group(1).strip(), int(float(match.group(2)))
    return text, None


def _gsettings_font(key):
    try:
        result = subprocess.run(
            ('gsettings', 'get', 'org.gnome.desktop.interface', key),
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if result.returncode != 0:
        return None, None
    return _parse_font_description(result.stdout)


def _kde_ui_font():
    config = configparser.ConfigParser()
    try:
        config.read(Path.home() / '.config' / 'kdeglobals')
        raw = config.get('General', 'font')
    except (configparser.Error, OSError):
        return None, None
    parts = raw.split(',')
    try:
        return parts[0].strip() or None, int(parts[1])
    except (IndexError, ValueError):
        return parts[0].strip() or None, None


def _fc_match(kind):
    try:
        result = subprocess.run(
            ('fc-match', '--format=%{family}', kind),
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.split(',', 1)[0].strip() or None


def _detect_linux_ui_font(families):
    for getter in (lambda: _gsettings_font('font-name'), _kde_ui_font,
                   lambda: (_fc_match('sans-serif'), None)):
        family, size = getter()
        if family:
            matched = _match_family(family, families)
            if matched:
                return matched, size
    for preferred in UI_FONT_PREFERENCE + MONO_FONT_PREFERENCE:
        matched = _match_family(preferred, families)
        if matched:
            return matched, None
    default = font.nametofont('TkDefaultFont').actual('family')
    if default == 'fixed':
        for family in families:
            if family != 'fixed':
                return family, None
    return default, None


def _detect_linux_mono_font(families):
    matched = _match_family(_gsettings_font('monospace-font-name')[0] or '', families)
    if matched:
        return matched
    matched = _match_family(_fc_match('monospace') or '', families)
    if matched:
        return matched
    for preferred in MONO_FONT_PREFERENCE:
        matched = _match_family(preferred, families)
        if matched:
            return matched
    return font.nametofont('TkFixedFont').actual('family')


def detect_system_fonts():
    """Return (ui_family, mono_family, ui_size) using fonts Tk can render."""
    families = tuple(font.families())
    if sys.platform.startswith('linux'):
        ui_family, ui_size = _detect_linux_ui_font(families)
        mono_family = _detect_linux_mono_font(families)
        return ui_family, mono_family, ui_size
    return (font.nametofont('TkDefaultFont').actual('family'),
            font.nametofont('TkFixedFont').actual('family'), None)


def set_named_fonts(ui_family, mono_family, ui_size=None):
    """Point Tk's named fonts at the given families.

    Every ttk widget inherits these named fonts, so the whole app follows the
    desktop font without per-widget configuration. Reconfiguring a named font
    updates existing widgets live and survives theme changes.
    """
    for name in NAMED_FONTS:
        try:
            named = font.nametofont(name)
        except tk.TclError:
            continue
        options = {'family': mono_family if name == 'TkFixedFont' else ui_family}
        if ui_size and name in ('TkDefaultFont', 'TkTextFont'):
            options['size'] = ui_size
        named.configure(**options)


def apply_system_fonts():
    """Detect the desktop fonts and apply them to Tk's named fonts.

    Returns (ui_family, mono_family, ui_size) so callers can re-apply them,
    for example after switching themes.
    """
    ui_family, mono_family, ui_size = detect_system_fonts()
    set_named_fonts(ui_family, mono_family, ui_size)
    return ui_family, mono_family, ui_size
