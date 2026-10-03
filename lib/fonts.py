"""Portable font selection for procedural textures and signs.

DejaVu fonts are present on many Linux development machines, but their paths are
not portable. Prefer an installed system font (including Windows' bundled Arial)
and fall back to Pillow's built-in font so asset generation never depends on one
absolute font path.
"""
import os
from PIL import ImageFont


_WINDOWS_FONTS = os.path.join(os.environ.get('WINDIR', os.environ.get('SystemRoot', 'C:\\Windows')), 'Fonts')


def _first_existing(paths):
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def _font_paths(env_name, windows_names, unix_names, mac_names):
    override = os.environ.get(env_name)
    candidates = [override] if override else []
    candidates.extend(os.path.join(_WINDOWS_FONTS, name) for name in windows_names)
    candidates.extend(unix_names)
    candidates.extend(mac_names)
    return candidates


FONT_B = _first_existing(_font_paths(
    'NC_FONT_BOLD',
    ('arialbd.ttf', 'segoeuib.ttf', 'DejaVuSans-Bold.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
     '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
    ('/System/Library/Fonts/Supplemental/Arial Bold.ttf',
     '/Library/Fonts/Arial Bold.ttf'),
)) or 'Arial Bold.ttf'

FONT_R = _first_existing(_font_paths(
    'NC_FONT_REGULAR',
    ('arial.ttf', 'segoeui.ttf', 'DejaVuSans.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
     '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
    ('/System/Library/Fonts/Supplemental/Arial.ttf',
     '/Library/Fonts/Arial.ttf'),
)) or 'Arial.ttf'

FONT_M = _first_existing(_font_paths(
    'NC_FONT_MONO',
    ('consolab.ttf', 'courbd.ttf', 'lucon.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
     '/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf'),
    ('/System/Library/Fonts/Menlo.ttc',
     '/System/Library/Fonts/Supplemental/Courier New Bold.ttf'),
)) or 'DejaVuSansMono-Bold.ttf'


def load_font(font, size):
    """Load a requested TrueType font, falling back to Pillow's bundled font."""
    size = max(1, int(size))
    if font:
        try:
            return ImageFont.truetype(font, size)
        except (OSError, TypeError, ValueError):
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow versions predating the scalable built-in font.
        return ImageFont.load_default()
