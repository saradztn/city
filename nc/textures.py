# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# textures.py - registry front-end: generate(name, scale) -> PBR, deterministic per name.
import zlib
from . import texgen, texsign, textunnel      # noqa: F401  (importing registers every material)
from .texgen import REG


def seed_of(name):
    return zlib.crc32(name.encode()) % 100000


def generate(name, scale=1):
    sp = REG[name]
    h, w = int(sp['h'] * scale), int(sp['w'] * scale)
    return sp['fn'](h, w, seed_of(name))


def names():
    return sorted(REG)
