# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# bld.py - building archetypes.  Every function returns (Mesh, Col, meta).  Local frame: origin = footprint centre at
#          street level, z up.  Deterministic per seed.  Facades use floor / bay aligned UVs (see bldkit.facade).
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, TAU, unit
from . import parts as P
from . import bldkit as K
from .bldkit import FLOOR_H, POD_H, rect, chamfer, regular, offset_poly

STRIP = ['nc_strip_cyan', 'nc_strip_white', 'nc_strip_cyan']
GLASSES = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_d', 'nc_glass_e', 'nc_glass_f', 'nc_glass_g', 'nc_glass_h']
LEDCOL = {'nc_strip_cyan': P.CYA, 'nc_strip_white': P.COOL, 'nc_light_magenta': P.MAG, 'nc_light_amber': (1.0, 0.55, 0.1)}


def glow_band(M, poly, z, h=0.55, mat='nc_strip_cyan', out=0.25, lights=0, rng=None):
    """emissive LED band around a tier top"""
    off = offset_poly(poly, out)
    M.extrude(off, z, z + h, mat, mat, tile=(2, 1), emis=1.0)
    col = LEDCOL.get(mat, P.COOL)
    for i in range(lights):
        p = off[i % len(off)]
        M.light((p[0], p[1], z + 0.5), col, 1.0, 22.0)


def crown(M, C, poly, z, style, rng, mat_led='nc_strip_cyan'):
    poly = np.asarray(poly, float)
    lo, hi = poly.min(0), poly.max(0)
    ctr = poly.mean(0)
    K.parapet(M, poly, z, 1.2)
    if style == 'flat':
        K.roof_clutter(M, rng, poly, z, n_ac=int(rng.integers(3, 7)), n_tank=1, n_ant=2, n_dish=1, n_stack=1, n_hvac=2)
    elif style == 'spire':
        s0 = offset_poly(poly, -1.0)
        s1 = ctr + (s0 - ctr) * 0.45
        n = len(poly)
        M.loft(s0, z + 0.4, s1, z + 14.0, 'nc_metal_dark', 'nc_metal_dark', tile=(4, 4))
        glow_band(M, poly, z, 0.5, mat_led, 0.35, lights=2)
        M.merge(P.antenna(float(rng.uniform(22, 36)), True), (ctr[0], ctr[1], z + 14.0))
        K.roof_clutter(M, rng, poly, z, n_ac=2, n_ant=0, n_hvac=1, edge=1.5)
    elif style == 'ring':
        glow_band(M, poly, z, 0.7, mat_led, 0.4, lights=3)
        s0 = offset_poly(poly, -1.5)
        M.extrude(s0, z, z + 5.0, 'nc_wall_metal', 'nc_roof', tile=(4, 4))
        glow_band(M, s0, z + 5.0, 0.4, 'nc_strip_white', 0.2)
        glow_band(M, s0, z + 2.4, 0.35, mat_led, 0.12)
        M.merge(P.antenna(float(rng.uniform(14, 24)), True), (ctr[0], ctr[1], z + 5.0))
        K.roof_clutter(M, rng, poly, z, n_ac=2, n_ant=0, n_hvac=1, edge=1.5)
    elif style == 'prongs':
        for p in poly[:4] if len(poly) >= 4 else poly:
            q = ctr + (p - ctr) * 0.86
            M.loft(regular(4, 1.3, q[0], q[1], np.pi / 4), z, regular(4, 0.35, q[0], q[1], np.pi / 4), z + 16.0, 'nc_metal_dark', 'nc_metal_dark', tile=(2, 2))
            P.beacon_light(M, (q[0] - 0.15, q[1] - 0.15, z + 16.0))
        glow_band(M, poly, z, 0.5, mat_led, 0.3, lights=2)
        K.roof_clutter(M, rng, poly, z, n_ac=3, n_ant=0, n_hvac=1, n_dish=1, edge=3.0)
    elif style == 'dish':
        K.roof_clutter(M, rng, poly, z, n_ac=3, n_ant=1, n_hvac=1, edge=3.0)
        M.merge(P.dish(2.6), (ctr[0], ctr[1], z), rz=float(rng.uniform(0, 360)))
        glow_band(M, poly, z, 0.5, mat_led, 0.3, lights=2)


def _meta(kind, w, d, h, floors, dist=600.0, **kw):
    m = dict(kind=kind, w=float(w), d=float(d), h=float(h), floors=int(floors), dist=float(dist))
    m.update(kw)
    return m


# ---------------------------------------------------------------------------------------------
# skyscrapers
# ---------------------------------------------------------------------------------------------
def tower_setback(w, d, floors, mat, seed, crown_style='spire', steps=2, scale_top=0.62, pod=1, fin=0, signs=2, led='nc_strip_cyan', octo=False):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    zp = 0.0
    kinds = [('retail', 'club', 'food'), ('retail', 'retail', 'club')]
    for k in range(pod):
        K.podium(M, C, w + 6, d + 6, rng, kinds=kinds[k % 2], z0=zp, canopy=(k == pod - 1))
        zp += POD_H
    z = zp + 0.35
    fl_tot = max(8, floors)
    shares = np.array([1.0 / (steps + 1)] * (steps + 1))
    shares = shares * np.linspace(1.5, 0.6, steps + 1)
    shares = shares / shares.sum()
    scale = np.linspace(1.0, scale_top, steps + 1)
    poly = None
    for i in range(steps + 1):
        nf = max(3, int(round(fl_tot * shares[i])))
        c = 2.4 if octo else 0.0
        poly = chamfer(w * scale[i], d * scale[i], c) if octo else rect(w * scale[i], d * scale[i])
        z1 = z + nf * FLOOR_H
        K.tier(M, C, poly, z, z1, mat, rng, emis=0.9, ledge_every=int(rng.choice([4, 6, 8])), fin_every=(2 if (fin and i == 0) else 0))
        if i < steps:
            # terrace slab where the next tier steps back + glowing edge strip
            K.ledge(M, poly, z1, z1 + 0.5, 0.5)
            glow_band(M, poly, z1 + 0.5, 0.3, led, 0.5, lights=2)
            C.box((poly[:, 0].min(), poly[:, 1].min(), z1), (poly[:, 0].max(), poly[:, 1].max(), z1 + 0.5))
            z1 += 0.5
        z = z1
    # mechanical floor band + vents on the top tier
    crown(M, C, poly, z, crown_style, rng, led)
    # big screens and neon on the tower lower facade
    w0, d0 = w, d
    sides = [(rect(w0, d0)[i], rect(w0, d0)[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    zs = zp + 0.35
    for j in range(min(signs, 4)):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        K.wall_sign(M, a, b, zs + 9.0 + 1.5 * j, 'ad' if j % 2 == 0 else 'led', int(rng.integers(0, 8)), min(L * 0.6, 16.0), 9.0, along=0.5)
    for j in range(2):
        a, b = sides[order[(j + 2) % 4]]
        K.wall_sign(M, a, b, zs + 3.0, 'h', int(rng.integers(0, 32)), 6.0, 1.5, along=float(rng.uniform(0.25, 0.75)))
    H = z + 24.0
    return M, C, _meta('tower', w + 6, d + 6, H, floors, 800.0, mat=mat)


def tower_cyl(r, floors, mat, seed, ring_every=8, n=24, led='nc_strip_cyan', crown_style='ring', pod=1):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    # round podium with shop band (polygon sides = bays)
    zp = POD_H
    pr = r + 3.5
    poly_p = regular(n, pr)
    chord = 2 * pr * np.sin(np.pi / n)
    kind = ('retail', 'club', 'food')[int(rng.integers(3))]
    M.extrude(poly_p, 0, zp, 'nc_shop_' + kind, 'nc_concrete_dark', tile=(chord * 4, POD_H), emis=0.85, smooth=False)
    for i in range(n // 3):
        a = poly_p[(3 * i) % n]
        c = [P.WARMW, P.MAG, P.CYA][int(rng.integers(3))]
        M.light((a[0] * 0.9, a[1] * 0.9, 2.5), c, 0.8, 10.0, n=(a[0], a[1], 0))
    M.extrude(offset_poly(poly_p, 0.8), zp, zp + 0.35, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 1), bottom_mat='nc_concrete_dark')
    C.box((-pr, -pr, 0), (pr, pr, zp + 0.35))
    z = zp + 0.35
    nf = max(10, floors)
    poly = regular(n, r)
    chord = 2 * r * np.sin(np.pi / n)
    z1 = z + nf * FLOOR_H
    M.extrude(poly, z, z1, mat, 'nc_roof', tile=(chord * 4, FLOOR_H * 8), smooth=True, emis=0.9, uvoff=(0.0, z / (FLOOR_H * 8)))
    for k in range(ring_every, nf, ring_every):
        zz = z + k * FLOOR_H
        M.extrude(offset_poly(poly, 0.55), zz - 0.3, zz + 0.3, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 1))
        glow_band(M, poly, zz + 0.3, 0.3, led, 0.5, lights=1)
    C.box((-r, -r, z), (r, r, z1))
    crown(M, C, poly, z1, crown_style, rng, led)
    return M, C, _meta('tower', pr * 2, pr * 2, z1 + 24, floors, 800.0, mat=mat)


def tower_twin(w, d, floors, gap, mat, seed, led='nc_strip_cyan'):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    W = 2 * w + gap
    K.podium(M, C, W + 6, d + 6, rng, kinds=('retail', 'club', 'food'))
    z0 = POD_H + 0.35
    nf = max(14, floors)
    zt = z0 + nf * FLOOR_H
    for sx in (-1, 1):
        cx = sx * (gap / 2 + w / 2)
        poly = rect(w, d, cx, 0)
        K.tier(M, C, poly, z0, zt, mat, rng, ledge_every=6, fin_every=2)
        K.ledge(M, poly, zt, zt + 0.5, 0.45)
        crown(M, C, poly, zt + 0.5, 'prongs' if sx > 0 else 'ring', rng, led)
    # sky bridge: glass tube between the towers (2 storeys), lit
    zb = z0 + int(nf * 0.58) * FLOOR_H
    bh = FLOOR_H * 2
    M.box((-gap / 2 - 0.2, -d * 0.18, zb), (gap / 2 + 0.2, d * 0.18, zb + bh), 'nc_glass_e', tile=(3.2 * 4, bh * 4), emis=0.95, skip=('+x', '-x'), uvoff=(0, 0.25))
    M.box((-gap / 2 - 0.2, -d * 0.18 - 0.2, zb - 0.9), (gap / 2 + 0.2, d * 0.18 + 0.2, zb), 'nc_metal_dark', tile=(2, 2))
    M.box((-gap / 2 - 0.2, -d * 0.18 - 0.2, zb + bh), (gap / 2 + 0.2, d * 0.18 + 0.2, zb + bh + 0.5), 'nc_metal_dark', tile=(2, 2))
    M.box((-gap / 2, -d * 0.18, zb + bh + 0.5), (gap / 2, d * 0.18, zb + bh + 0.56), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((0, 0, zb + bh / 2), P.COOL, 1.4, 30.0)
    C.box((-gap / 2, -d * 0.18 - 0.2, zb - 0.9), (gap / 2, d * 0.18 + 0.2, zb + bh + 0.5))
    for j in range(2):
        a, b = rect(W, d)[j * 2], rect(W, d)[(j * 2 + 1) % 4]
        K.wall_sign(M, a, b, POD_H + 10, 'ad', int(rng.integers(0, 8)), 16.0, 8.0)
    return M, C, _meta('tower', W + 6, d + 6, zt + 40, floors, 800.0, mat=mat)


def arcology(w, floors, seed, mat='nc_glass_e'):
    """hero: stepped pyramid megastructure"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w + 8, w + 8, rng, kinds=('retail', 'club', 'food'), h=POD_H)
    z = POD_H + 0.35
    steps = 6
    scale = np.linspace(1.0, 0.22, steps)
    nfs = [int(round(floors * s)) for s in np.array([0.26, 0.22, 0.18, 0.14, 0.12, 0.08])]
    poly = None
    for i in range(steps):
        poly = chamfer(w * scale[i], w * scale[i], 3.0 * scale[i] + 1.0)
        nf = max(4, nfs[i])
        z1 = z + nf * FLOOR_H
        K.tier(M, C, poly, z, z1, mat if i % 2 == 0 else 'nc_glass_c', rng, ledge_every=4, fin_every=2 if i < 3 else 0, corners=True)
        K.ledge(M, poly, z1, z1 + 0.6, 0.7)
        glow_band(M, poly, z1 + 0.6, 0.35, 'nc_strip_cyan' if i % 2 == 0 else 'nc_strip_white', 0.7, lights=3)
        C.box((poly[:, 0].min(), poly[:, 1].min(), z1), (poly[:, 0].max(), poly[:, 1].max(), z1 + 0.6))
        z = z1 + 0.6
    crown(M, C, poly, z, 'spire', rng, 'nc_strip_white')
    for j in range(4):
        a, b = rect(w, w)[j], rect(w, w)[(j + 1) % 4]
        K.wall_sign(M, a, b, POD_H + 14, 'led', j, 22.0, 12.0, along=0.5)
        K.wall_sign(M, a, b, POD_H + 32, 'ad', j + 2, 18.0, 9.0, along=0.3)
    return M, C, _meta('tower', w + 8, w + 8, z + 40, floors, 900.0, mat=mat, hero=True)


# ---------------------------------------------------------------------------------------------
# mid and low rise
# ---------------------------------------------------------------------------------------------
def midrise(w, d, floors, mat, seed, signs=3, led='nc_strip_white'):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng)
    z0 = POD_H + 0.35
    nf = max(4, floors)
    poly = rect(w - 1.2, d - 1.2)
    z1 = z0 + nf * FLOOR_H
    K.tier(M, C, poly, z0, z1, mat, rng, ledge_every=int(rng.choice([2, 3, 4])), fin_every=int(rng.choice([0, 0, 2])))
    crown(M, C, poly, z1, str(rng.choice(['flat', 'flat', 'ring', 'prongs'])), rng, led)
    sides = [(poly[i], poly[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    for j in range(min(signs, 4)):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        kind = ['led', 'ad', 'led', 'ad'][j % 4]
        K.wall_sign(M, a, b, z0 + 7.0 + 3.0 * (j % 2), kind, int(rng.integers(0, 8)), min(L * 0.55, 14.0), min(9.0, 4.0 + nf * 0.4), along=float(rng.uniform(0.35, 0.65)))
    for j in range(3):
        a, b = sides[order[(j + 1) % 4]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.15, 0.85))
        K.blade_sign(M, p, nrm, POD_H + 2.5 + float(rng.uniform(0, 3)), 'v', int(rng.integers(0, 32)), 1.3, 4.2)
    return M, C, _meta('mid', w, d, z1 + 10, floors, 520.0, mat=mat)


def tenement(w, d, floors, mat, seed, escapes=2):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('food', 'club', 'retail'), canopy=True)
    z0 = POD_H + 0.35
    nf = max(4, floors)
    poly = rect(w - 1.0, d - 1.0)
    z1 = z0 + nf * 3.3
    K.tier(M, C, poly, z0, z1, mat, rng, emis=0.62, ledge_every=0, bays_tile=4, floors_tile=4, bay_w=3.0, floor_h=3.3, corners=True)
    K.ledge(M, poly, z1, z1 + 0.45, 0.35)
    K.parapet(M, poly, z1 + 0.45, 1.0)
    K.roof_clutter(M, rng, poly, z1 + 0.45, n_ac=int(rng.integers(3, 8)), n_tank=int(rng.integers(1, 3)), n_ant=int(rng.integers(1, 3)), n_dish=int(rng.integers(1, 3)), n_stack=2, n_hvac=1)
    sides = [(poly[i], poly[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    for j in range(escapes):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.3, 0.7))
        M.merge(P.fire_escape(min(4, nf - 1), 3.3, 2.6), (p[0], p[1], z0 + 0.0), rz=P.yaw_facing(nrm[0], nrm[1]))
    # air conditioners bolted on the facades
    for j in range(int(nf * 1.6)):
        a, b = sides[int(rng.integers(4))]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.08, 0.92)) + nrm * 0.02
        z = z0 + 0.8 + 3.3 * int(rng.integers(0, nf)) + 0.3
        M.merge(P.ac_unit(), (p[0], p[1], z), rz=P.yaw_facing(nrm[0], nrm[1]))
    # vertical neon blades + a flush sign
    for j in range(int(rng.integers(2, 4))):
        a, b = sides[order[(j + 1) % 4]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.1, 0.9))
        K.blade_sign(M, p, nrm, POD_H + 3.5 + float(rng.uniform(0, 5)), 'v', int(rng.integers(0, 32)), 1.2, 3.8)
    a, b = sides[order[0]]
    K.wall_sign(M, a, b, POD_H + 0.35 + 1.2, 'h', int(rng.integers(0, 32)), 5.0, 1.8, along=float(rng.uniform(0.3, 0.7)))
    # awnings on the shops
    for j in range(int(rng.integers(1, 3))):
        a, b = sides[int(rng.integers(4))]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a - nrm * 0.0 + e * L * float(rng.uniform(0.2, 0.8)) + nrm * 0.62
        M.merge(P.awning(3.0, 1.4, 0.5), (p[0] - nrm[0] * 0.6, p[1] - nrm[1] * 0.6, 3.6), rz=P.yaw_facing(nrm[0], nrm[1]))
    return M, C, _meta('tenement', w, d, z1 + 12, floors, 420.0, mat=mat)


def slab(w, d, floors, mat, seed, balcony=True):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('retail', 'food'), canopy=True)
    z0 = POD_H + 0.35
    nf = max(8, floors)
    poly = rect(w - 1.2, d - 1.2)
    z1 = z0 + nf * FLOOR_H
    K.tier(M, C, poly, z0, z1, mat, rng, emis=0.78, ledge_every=0, corners=True)
    if balcony:
        # continuous balcony bands on the two long faces (south: outside = -y, north: outside = +y)
        x0, x1 = poly[:, 0].min() + 0.3, poly[:, 0].max() - 0.3
        ys, yn = poly[:, 1].min(), poly[:, 1].max()
        for k in range(2, nf):
            zz = z0 + k * FLOOR_H
            for ya, yb, yr in ((ys - 1.5, ys, ys - 1.46), (yn, yn + 1.5, yn + 1.46)):
                M.box((x0, ya, zz - 0.18), (x1, yb, zz), 'nc_concrete', tile=(4, 1))
                M.box((x0, min(yr, yr + 0.04) - 0.02, zz), (x1, max(yr, yr + 0.04) + 0.02, zz + 1.05), 'nc_glass_a', tile=(3.2, 3.2), emis=0.45)
                M.box((x0, min(yr, yr + 0.04) - 0.03, zz + 1.02), (x1, max(yr, yr + 0.04) + 0.03, zz + 1.08), 'nc_strip_white', tile=(1, 1), emis=0.9)
        C.box((x0, ys - 1.5, z0), (x1, ys, z0 + 0.4))
    K.ledge(M, poly, z1, z1 + 0.45, 0.35)
    K.parapet(M, poly, z1 + 0.45, 1.0)
    K.roof_clutter(M, rng, poly, z1 + 0.45, n_ac=4, n_tank=2, n_ant=2, n_dish=2, n_stack=1, n_hvac=2)
    a, b = poly[0], poly[1]
    K.wall_sign(M, a, b, z0 + nf * FLOOR_H * 0.6, 'ad', int(rng.integers(0, 8)), min(14.0, w * 0.4), 8.0)
    return M, C, _meta('slab', w, d, z1 + 12, floors, 520.0, mat=mat)


def megablock(w, d, floors, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('food', 'retail', 'club'))
    z = POD_H + 0.35
    scale = [1.0, 0.82, 0.62]
    nfs = [int(floors * 0.4), int(floors * 0.33), int(floors * 0.27)]
    poly = None
    for i in range(3):
        poly = rect((w - 1.0) * scale[i], (d - 1.0) * scale[i])
        nf = max(3, nfs[i])
        z1 = z + nf * 3.3
        K.tier(M, C, poly, z, z1, 'nc_wall_brutal' if i != 1 else 'nc_wall_tenement_b', rng, emis=0.6, bays_tile=4, floors_tile=4, bay_w=3.0, floor_h=3.3)
        K.ledge(M, poly, z1, z1 + 0.5, 0.6)
        # terrace edge planters
        sides = [(poly[j], poly[(j + 1) % 4]) for j in range(4)]
        for a, b in sides:
            L = np.linalg.norm(b - a)
            e = (b - a) / L
            for k in range(int(L // 6)):
                p = a + e * (3 + 6 * k) + np.array([e[1], -e[0]]) * 1.0
                M.merge(P.planter(3.0, 0.9), (p[0], p[1], z1 + 0.5), rz=P.yaw_facing(e[1], -e[0]))
        z = z1 + 0.5
        for j in range(int(nf * 0.8)):
            a, b = sides[int(rng.integers(4))]
            L = np.linalg.norm(b - a)
            e = (b - a) / L
            nrm = np.array([e[1], -e[0]])
            p = a + e * L * float(rng.uniform(0.08, 0.92)) + nrm * 0.02
            M.merge(P.ac_unit(), (p[0], p[1], z - 0.5 - 3.3 * int(rng.integers(1, nf)) + 0.3), rz=P.yaw_facing(nrm[0], nrm[1]))
    crown(M, C, poly, z, 'flat', rng)
    a, b = rect(w, d)[0], rect(w, d)[1]
    K.wall_sign(M, a, b, POD_H + 12, 'led', int(rng.integers(0, 4)), min(16.0, w * 0.45), 10.0)
    for j in range(3):
        a, b = rect(w, d)[(j + 1) % 4], rect(w, d)[(j + 2) % 4]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        K.blade_sign(M, a + e * L * float(rng.uniform(0.2, 0.8)), nrm, POD_H + 4 + 3 * j, 'v', int(rng.integers(0, 32)), 1.3, 4.0)
    return M, C, _meta('mega', w, d, z + 12, floors, 560.0)


# ---------------------------------------------------------------------------------------------
# industrial
# ---------------------------------------------------------------------------------------------
def warehouse(w, d, h, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    poly = rect(w - 1.0, d - 1.0)
    M.extrude(poly, 0, 1.2, 'nc_concrete_dark', None, tile=(4, 4))
    for i in range(4):
        a, b = poly[i], poly[(i + 1) % 4]
        L = np.linalg.norm(b - a)
        M.wall(a, b, 1.2, h, 'nc_wall_corrug', tile=(L / max(1, round(L / 2.0)) * 0 + 4.0, 4.0), uoff=float(rng.random()))
    # roof: shallow gable
    x0, x1, y0, y1 = poly[0][0], poly[2][0], poly[0][1], poly[2][1]
    rh = 2.2
    ym = (y0 + y1) / 2
    M.quad((x0 - 0.4, y0 - 0.4, h), (x1 + 0.4, y0 - 0.4, h), (x1 + 0.4, ym, h + rh), (x0 - 0.4, ym, h + rh), 'nc_roof', tile=(4, 4))
    M.quad((x1 + 0.4, y1 + 0.4, h), (x0 - 0.4, y1 + 0.4, h), (x0 - 0.4, ym, h + rh), (x1 + 0.4, ym, h + rh), 'nc_roof', tile=(4, 4))
    M.quad((x1, y0, h), (x1, ym, h + rh), (x1, y1, h), (x1, y0, h), 'nc_wall_corrug', tile=(4, 4))
    M.quad((x0, y1, h), (x0, ym, h + rh), (x0, y0, h), (x0, y1, h), 'nc_wall_corrug', tile=(4, 4))
    for k in range(int(w // 14)):
        x = x0 + 8 + k * 14
        M.box((x - 0.6, ym - 0.6, h + rh), (x + 0.6, ym + 0.6, h + rh + 0.9), 'nc_metal_light', tile=(1, 1))
    C.box((x0, y0, 0), (x1, y1, h + rh))
    # loading docks on the long south wall with lamps
    nd = max(2, int(w // 12))
    for k in range(nd):
        x = x0 + (k + 0.5) * (x1 - x0) / nd
        M.box((x - 2.2, y0 - 0.5, 0.0), (x + 2.2, y0, 4.2), 'nc_metal_dark', tile=(2, 2), skip=('+y',))
        M.box((x - 0.25, y0 - 0.9, 5.0), (x + 0.25, y0 - 0.4, 5.4), 'nc_metal_dark', tile=(1, 1))
        M.hquad(x - 0.2, y0 - 0.85, x + 0.2, y0 - 0.45, 4.995, 'nc_light_warm', tile=(1, 1), emis=1.0, up=False)
        M.light((x, y0 - 1.5, 4.6), P.SODIUM, 1.1, 14.0, n=(0, -1, 0))
    # side pipe rack + tank
    for k in range(int(d // 10)):
        M.merge(P.floodlight_mast(14.0), (x1 + 3, y0 + 6 + k * 10), rz=90.0) if k % 3 == 0 else None
    return M, C, _meta('warehouse', w, d, h + rh, 0, 420.0)


def factory(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    # main hall
    hw, hd, hh = w * 0.62, d * 0.55, 16.0
    cx, cy = -w * 0.15, -d * 0.18
    poly = rect(hw, hd, cx, cy)
    M.extrude(poly, 0, 1.2, 'nc_concrete_dark', None, tile=(4, 4))
    for i in range(4):
        M.wall(poly[i], poly[(i + 1) % 4], 1.2, hh, 'nc_wall_corrug', tile=(4.0, 4.0), uoff=float(rng.random()))
    M.poly([(p[0], p[1], hh) for p in poly], 'nc_roof', (4, 4))
    K.parapet(M, poly, hh, 0.8)
    C.box((cx - hw / 2, cy - hd / 2, 0), (cx + hw / 2, cy + hd / 2, hh))
    # side annex
    ap = rect(w * 0.28, d * 0.4, w * 0.34, -d * 0.2)
    M.extrude(ap, 0, 9.0, 'nc_wall_metal', 'nc_roof', tile=(4, 4))
    C.box((ap[:, 0].min(), ap[:, 1].min(), 0), (ap[:, 0].max(), ap[:, 1].max(), 9.0))
    # smoke stacks with red beacons and steam
    for k, sx in enumerate((0.25, 0.38, 0.51)):
        x, y = w * (sx - 0.1), d * 0.3
        sh = 52.0 + 12 * k
        M.cone((x, y), 2.4, 1.5, 0, sh, 14, 'nc_concrete_dark', tile=(4, 6), top_mat='nc_concrete_dark')
        for z in (sh * 0.45, sh * 0.8):
            M.cyl((x, y), 2.4 - (2.4 - 1.5) * z / sh + 0.12, z, z + 1.4, 14, 'nc_metal_rust', tile=(4, 2))
        P.beacon_light(M, (x - 0.2, y - 0.2, sh))
        for dz, s in ((6.0, 12.0), (14.0, 18.0)):
            P.steam_puff(M, (x, y, sh + dz), s, (0.62, 0.52, 0.66))
        C.box((x - 2.4, y - 2.4, 0), (x + 2.4, y + 2.4, sh))
    # cooling tower
    tx, ty = w * 0.22, d * 0.3 - 1
    M.loft(regular(20, 9.0, tx, ty), 0, regular(20, 6.5, tx, ty), 22.0, 'nc_concrete_dark', None, tile=(6, 6))
    M.loft(regular(20, 6.5, tx, ty), 22.0, regular(20, 7.6, tx, ty), 30.0, 'nc_concrete_dark', None, tile=(6, 6))
    for dz, s in ((8.0, 18.0), (18.0, 26.0)):
        P.steam_puff(M, (tx, ty, 31 + dz), s, (0.62, 0.52, 0.66))
    C.box((tx - 9, ty - 9, 0), (tx + 9, ty + 9, 30))
    # pipe rack along the front
    y = -d / 2 + 1.5
    for z in (4.0, 5.2, 6.4):
        P.pipe_run(M, [(-w / 2 + 2, y, z), (w / 2 - 2, y, z)], 0.18, P.MR)
    for k in range(int(w // 8)):
        x = -w / 2 + 3 + k * 8
        M.box((x - 0.15, y - 0.15, 0), (x + 0.15, y + 0.15, 6.8), 'nc_steel', tile=(1, 1))
    # flare
    fx = -w / 2 + 6
    M.cyl((fx, d * 0.35), 0.35, 0, 38.0, 8, 'nc_steel', tile=(2, 2), top_mat='nc_steel')
    for z in (6, 14, 22, 30):
        M.box((fx - 0.7, d * 0.35 - 0.04, z), (fx + 0.7, d * 0.35 + 0.04, z + 0.06), 'nc_steel', tile=(1, 1))
    M.cone((fx, d * 0.35), 0.5, 0.05, 38.0, 41.5, 8, 'nc_light_amber', emis=1.0)
    M.light((fx, d * 0.35, 40), (1.0, 0.45, 0.1), 3.0, 60.0)
    P.glow_sprite(M, (fx, d * 0.35, 40.0), 14.0, (1.0, 0.5, 0.12))
    C.box((fx - 0.6, d * 0.35 - 0.6, 0), (fx + 0.6, d * 0.35 + 0.6, 38.0))
    for k in range(3):
        M.merge(P.floodlight_mast(15.0), (-w / 2 + 8 + k * w / 3, -d / 2 - 1.5))
    return M, C, _meta('factory', w, d, 62.0, 0, 560.0)


def tank_farm(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    M.extrude(rect(w - 0.6, d - 0.6), 0, 0.9, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 4))       # bund slab
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, 0.9))
    nx, ny = max(1, int(w // 24)), max(1, int(d // 24))
    cells = [(i, j) for i in range(nx) for j in range(ny)]
    for i, j in cells:
        x = -w / 2 + (i + 0.5) * w / nx
        y = -d / 2 + (j + 0.5) * d / ny
        r = float(rng.uniform(8.0, min(11.0, w / nx / 2 - 1.5, d / ny / 2 - 1.5)))
        h = float(rng.uniform(12, 18))
        M.cyl((x, y), r, 0.9, 0.9 + h, 20, 'nc_tank', tile=(6, 3), top_mat='nc_metal_light', smooth=True)
        M.cone((x, y), r, r * 0.12, 0.9 + h, 0.9 + h + 1.6, 20, 'nc_metal_light', tile=(4, 4))
        M.cyl((x, y), r + 0.12, 0.9 + h - 1.2, 0.9 + h - 1.0, 20, 'nc_steel', tile=(4, 1), top_mat='nc_steel')          # walkway ring
        M.cyl((x, y), r + 0.06, 0.9 + h * 0.5, 0.9 + h * 0.5 + 0.12, 20, 'nc_steel', tile=(4, 1))
        a = rng.uniform(0, TAU)
        P.beacon_light(M, (x - 0.15, y - 0.15, 0.9 + h + 1.6))
        C.box((x - r, y - r, 0.9), (x + r, y + r, 0.9 + h + 1.6))
        # pipe to the next tank
        P.pipe_run(M, [(x + r * 0.7, y - r * 0.7, 1.4), (x + r * 0.7 + 2.5, y - r * 0.7, 1.4), (x + r * 0.7 + 2.5, y - r * 0.7 - 2.0, 1.4)], 0.22, P.MR)
        M.cyl((x + r * 0.7, y - r * 0.7), 0.4, 0.9, 1.5, 8, 'nc_metal_rust', tile=(1, 1), top_mat='nc_metal_rust')
    for k in range(2):
        M.merge(P.floodlight_mast(18.0), (-w / 2 + 3 + k * (w - 6), -d / 2 + 3), rz=45.0)
    return M, C, _meta('tanks', w, d, 36.0, 0, 520.0)


def container_yard(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    M.extrude(rect(w - 0.4, d - 0.4), 0, 0.3, 'nc_concrete_dark', 'nc_alley', tile=(4, 4))
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, 0.3))
    mats = ['nc_container_a', 'nc_container_b', 'nc_container_c']
    L, W, H = 12.2, 2.45, 2.6
    nx = max(1, int((w - 8) // (L + 2)))
    ny = max(1, int((d - 6) // (W * 2 + 2.5)))
    for i in range(nx):
        for j in range(ny):
            hgt = int(rng.integers(1, 5))
            x = -w / 2 + 5 + L / 2 + i * (L + 2.0)
            for jj in range(2):
                y = -d / 2 + 4 + W / 2 + j * (W * 2 + 2.5) + jj * W
                for k in range(hgt):
                    m = mats[int(rng.integers(3))]
                    M.box((x - L / 2, y - W / 2, 0.3 + k * H), (x + L / 2, y + W / 2, 0.3 + (k + 1) * H), m, tile=(6.0, 2.6), uvoff=(float(rng.random()), 0))
                C.box((x - L / 2, y - W / 2, 0.3), (x + L / 2, y + W / 2, 0.3 + hgt * H))
    for k in range(3):
        M.merge(P.floodlight_mast(20.0), (-w / 2 + 6 + k * (w - 12) / 2, -d / 2 + 1.5))
    return M, C, _meta('yard', w, d, 0.3 + 4 * H + 20, 0, 480.0)


def garage(w, d, levels, seed):
    """open multi-storey car park structure - kept EMPTY (this city has no vehicles); lit ceilings, LED edge bars"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    lh = 3.2
    for k in range(levels + 1):
        z = k * lh
        M.box((-w / 2, -d / 2, z), (w / 2, d / 2, z + 0.35), 'nc_concrete', tile=(4, 4), skip=())
        if k < levels:
            for cx in np.arange(-w / 2 + 3, w / 2, 9.0):
                for cy in (-d / 2 + 1.0, d / 2 - 1.0, 0.0):
                    M.box((cx - 0.35, cy - 0.35, z + 0.35), (cx + 0.35, cy + 0.35, z + lh), 'nc_concrete', tile=(1, 1))
            # parapet + LED bar on the facade sides
            for (x0, y0, x1, y1) in ((-w / 2, -d / 2, w / 2, -d / 2 + 0.3), (-w / 2, d / 2 - 0.3, w / 2, d / 2), (-w / 2, -d / 2, -w / 2 + 0.3, d / 2), (w / 2 - 0.3, -d / 2, w / 2, d / 2)):
                M.box((x0, y0, z + 0.35), (x1, y1, z + 1.2), 'nc_concrete_dark', tile=(2, 2))
            M.box((-w / 2 + 0.3, -d / 2 - 0.04, z + 1.2), (w / 2 - 0.3, -d / 2 + 0.02, z + 1.28), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('-z', '+z', '+x', '-x', '+y'))
            M.box((-w / 2 + 0.3, d / 2 - 0.02, z + 1.2), (w / 2 - 0.3, d / 2 + 0.04, z + 1.28), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('-z', '+z', '+x', '-x', '-y'))
            # ceiling light strips
            for cx in np.arange(-w / 2 + 6, w / 2 - 3, 9.0):
                M.box((cx - 0.12, -d / 2 + 3, z + lh - 0.04), (cx + 0.12, d / 2 - 3, z + lh), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('+z',))
            M.light((0, 0, z + lh - 0.5), P.COOL, 1.1, max(w, d) * 0.8)
    top = levels * lh + 0.35
    K.roof_clutter(M, rng, rect(w, d), top, n_ac=2, n_ant=1, n_hvac=1, edge=3.0)
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, top))
    K.wall_sign(M, rect(w, d)[0], rect(w, d)[1], levels * lh - 1.0, 'h', int(rng.integers(0, 32)), 9.0, 2.6)
    return M, C, _meta('garage', w, d, top + 14, 0, 420.0)


def plaza_gate(w, h, seed):
    """hero landmark: a giant gate (two piers + beam) carrying huge LED screens on both faces"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    pw, pd = 7.0, 9.0
    for sx in (-1, 1):
        cx = sx * (w / 2 - pw / 2)
        poly = rect(pw, pd, cx, 0)
        K.tier(M, C, poly, 0, h, 'nc_glass_f', rng, emis=0.9, corners=True, ledge_every=6)
        glow_band(M, poly, h, 0.5, 'nc_strip_cyan', 0.3, lights=1)
        K.ledge(M, poly, h - 0.5, h, 0.4)
    bz = h - 22.0
    M.box((-w / 2, -pd / 2, bz), (w / 2, pd / 2, h), 'nc_metal_dark', tile=(4, 4), skip=('+y', '-y'))
    for sy in (-1, 1):
        a, b = (np.array([w / 2 - 1, sy * pd / 2]), np.array([-w / 2 + 1, sy * pd / 2])) if sy > 0 else (np.array([-w / 2 + 1, sy * pd / 2]), np.array([w / 2 - 1, sy * pd / 2]))
        M.merge(P.led_panel(int(rng.integers(0, 4)), w - 8, 15.0), (0, sy * (pd / 2 + 0.2), bz + 11), rz=0.0 if sy > 0 else 180.0)
        M.merge(P.neon_sign('h', int(rng.integers(0, 32)), 14.0, 3.0), (0, sy * (pd / 2 + 0.3), bz + 2.0), rz=0.0 if sy > 0 else 180.0)
    M.box((-w / 2, -pd / 2, h), (w / 2, pd / 2, h + 0.6), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((0, 0, h + 1.0), P.CYA, 3.0, 60.0)
    C.box((-w / 2, -pd / 2, bz), (w / 2, pd / 2, h))
    return M, C, _meta('gate', w, pd, h + 1, 0, 700.0, hero=True)


# ---------------------------------------------------------------------------------------------
# American neighborhood / roadside architecture
# ---------------------------------------------------------------------------------------------
def _triangle(M, pts, mat, emis=0.0):
    P_ = np.asarray(pts, np.float64)
    n = unit(np.cross(P_[1] - P_[0], P_[2] - P_[0]))
    uv = np.stack([P_[:, 0] / 4.0, -P_[:, 2] / 4.0], axis=1)
    M.add(P_, np.tile(n, (3, 1)), uv, np.array([[0, 1, 2]], np.int64), mat, emis)


def family_house(w, d, seed, style=0, garage=True):
    """One- or two-storey detached American house with a garage, front porch and pitched shingle roof."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    style = int(style) % 4
    stories = 2 if style == 3 else 1
    eave = 3.55 if stories == 1 else 6.45
    roof_h = (2.35, 1.95, 2.70, 2.55)[style]
    garage_w = min(6.3, w * 0.34) if garage else 0.0
    main_w = w - garage_w * 0.78
    wallmat = ('nc_house_siding', 'nc_brick', 'nc_house_siding', 'nc_brick')[style]
    roofmat = 'nc_roof' if style == 2 else 'nc_roof_shingle'
    x0, x1 = -main_w / 2, main_w / 2
    y0, y1 = -d / 2, d / 2
    poly = rect(main_w, d)
    M.extrude(poly, 0.0, 0.28, 'nc_concrete_dark', 'nc_concrete', tile=(3, 3))
    for i in range(4):
        M.wall(poly[i], poly[(i + 1) % 4], 0.28, eave, wallmat, tile=(4, 3.2), emis=0.025)
    # gable roof, with a clear ridge line and visible fascia/eaves
    ridge_y = 0.0
    peak = eave + roof_h
    M.quad((x0 - 0.5, y0 - 0.35, eave), (x1 + 0.5, y0 - 0.35, eave),
           (x1 + 0.5, ridge_y, peak), (x0 - 0.5, ridge_y, peak), roofmat, tile=(4, 4))
    M.quad((x1 + 0.5, y1 + 0.35, eave), (x0 - 0.5, y1 + 0.35, eave),
           (x0 - 0.5, ridge_y, peak), (x1 + 0.5, ridge_y, peak), roofmat, tile=(4, 4))
    _triangle(M, [(x0, y0, eave), (x1, y0, eave), (0.0, y0, peak)], wallmat)
    _triangle(M, [(x1, y1, eave), (x0, y1, eave), (0.0, y1, peak)], wallmat)
    if style == 2:  # Craftsman gable braces and exposed rafter tails.
        for yy in (y0 - 0.08, y1 + 0.08):
            for sx in (-1, 1):
                M.tube(np.array([[sx * (main_w * 0.36), yy, eave + 0.22], [0.0, yy, peak - 0.18]]),
                       0.065, 5, 'nc_concrete_dark', tile=(2, 1), caps=False)
    M.box((x0 - 0.55, y0 - 0.40, eave - 0.10), (x1 + 0.55, y1 + 0.40, eave + 0.08), 'nc_concrete', tile=(4, 1))
    C.box((x0, y0, 0.0), (x1, y1, eave))
    C.box((x0 - 0.55, y0 - 0.40, eave - 0.10), (x1 + 0.55, y1 + 0.40, peak))

    # Main frontage faces south (local -y); double-hung windows, wood trim and a recessed entry.
    front_y = y0 - 0.10
    front_centres = (-main_w * 0.30, main_w * 0.20)
    for wx in front_centres:
        zc = 1.45 if stories == 1 else 2.05
        for zz in ((zc,) if stories == 1 else (zc, zc + 3.1)):
            M.box((wx - 1.05, front_y - 0.05, zz), (wx + 1.05, front_y + 0.04, zz + 1.28), 'nc_metal_light', tile=(1, 1))
            M.box((wx - 0.84, front_y - 0.065, zz + 0.14), (wx + 0.84, front_y + 0.055, zz + 1.12), 'nc_glass_a', tile=(1, 1))
            M.box((wx - 0.88, front_y - 0.10, zz + 0.63), (wx + 0.88, front_y - 0.07, zz + 0.69), 'nc_concrete', tile=(1, 1))
    door_x = -main_w * 0.06
    M.box((door_x - 0.60, front_y - 0.07, 0.28), (door_x + 0.60, front_y + 0.08, 2.55), 'nc_brick' if style == 1 else 'nc_metal_dark', tile=(1, 2))
    M.box((door_x - 0.42, front_y - 0.085, 1.40), (door_x + 0.30, front_y + 0.095, 2.28), 'nc_glass_b', tile=(1, 1))
    M.cyl((door_x + 0.38, front_y - 0.12), 0.045, 1.1, 1.22, 8, 'nc_metal_light', tile=(1, 1), top_mat='nc_metal_light')
    # Front and side window placements; the house remains a closed, solid game object.
    for sy in (-1, 1):
        y = sy * (d / 2 + 0.04)
        for xx in (-main_w * 0.20, main_w * 0.20):
            for zc in ((1.4,) if stories == 1 else (1.4, 4.55)):
                M.box((xx - 0.82, y - 0.05, zc), (xx + 0.82, y + 0.05, zc + 1.32), 'nc_metal_light', tile=(1, 1))
                M.box((xx - 0.66, y - 0.07, zc + 0.15), (xx + 0.66, y + 0.07, zc + 1.17), 'nc_glass_b', tile=(1, 1))
    for sx in (-1, 1):
        x = sx * (main_w / 2 + 0.04)
        for yy in (-d * 0.23, d * 0.22):
            M.box((x - 0.05, yy - 0.78, 1.45), (x + 0.05, yy + 0.78, 2.75), 'nc_metal_light', tile=(1, 1))
            M.box((x - 0.07, yy - 0.62, 1.60), (x + 0.07, yy + 0.62, 2.60), 'nc_glass_b', tile=(1, 1))
    # Small porch canopy, posts and front steps
    porch_w = min(8.5 if style == 2 else 7.0, main_w * (0.56 if style == 2 else 0.48))
    porch_depth = 3.0 if style == 2 else 2.35
    porch_x = -main_w * 0.10
    M.box((porch_x - porch_w / 2, y0 - porch_depth, 0.24), (porch_x + porch_w / 2, y0 + 0.2, 0.42), 'nc_concrete', tile=(2, 2))
    M.box((porch_x - porch_w / 2 - 0.20, y0 - porch_depth - 0.2, 2.9), (porch_x + porch_w / 2 + 0.20, y0 + 0.25, 3.12), roofmat, tile=(3, 2))
    for sx in (-1, 1):
        xx = porch_x + sx * (porch_w / 2 - 0.25)
        M.box((xx - 0.10, y0 - porch_depth, 0.42), (xx + 0.10, y0 + 0.12, 2.9), 'nc_concrete', tile=(1, 2))
    M.box((door_x - 0.95, y0 - porch_depth - 0.55, 0.05), (door_x + 0.95, y0 - porch_depth + 0.35, 0.20), 'nc_concrete', tile=(2, 1))
    # Attached one-car garage and a short driveway to the local street.
    if garage:
        gx0, gx1 = main_w * 0.34, w / 2
        gy0, gy1 = -d * 0.50, d * 0.28
        M.box((gx0, gy0, 0.25), (gx1, gy1, 3.1), wallmat, tile=(3, 3))
        M.box((gx0 + 0.30, gy0 - 0.10, 0.45), (gx1 - 0.30, gy0 + 0.06, 2.72), 'nc_metal_light', tile=(2, 1))
        for z in (0.92, 1.38, 1.84, 2.30):
            M.box((gx0 + 0.36, gy0 - 0.13, z), (gx1 - 0.36, gy0 - 0.09, z + 0.045), 'nc_metal_dark', tile=(1, 1))
        M.box((gx0 + 0.35, gy0 - 7.0, 0.015), (gx1 - 0.35, gy0 - 0.05, 0.04), 'nc_asphalt', tile=(3, 6))
        C.box((gx0, gy0, 0.25), (gx1, gy1, 3.1))
        C.box((gx0 + 0.35, gy0 - 7.0, 0.0), (gx1 - 0.35, gy0 - 0.05, 0.04))
    # A chimney / roof vent provides silhouette variation without oversized signage.
    if style in (1, 2):
        M.box((x0 + 1.0, y1 - 3.6, eave + 0.1), (x0 + 2.0, y1 - 2.4, eave + 2.3), 'nc_brick', tile=(1, 2))
    else:
        M.merge(P.hvac_box(1.7, 1.4, 0.9), (x0 + 2.0, y1 - 3.0, peak - 0.4), rz=0.0)
    return M, C, _meta('house', w, d + 7.0, peak + 1.0, stories, 420.0, style=style)


def estate_house(w, d, seed, style=2):
    """Upscale suburban home with a long private drive, privacy walls, landscaped yard and pool."""
    w, d = float(w), float(d)
    style = int(style) % 4
    M, C, base = family_house(w, d, seed, style, garage=True)
    lot_w, front_y, back_y = w + 14.0, -d / 2 - 14.0, d / 2 + 8.0
    wall_h, wall_t = 1.45, 0.38
    left, right = -lot_w / 2, lot_w / 2
    # Stone privacy walls and regularly spaced piers bound the property without hiding the roofline.
    M.box((left, front_y, 0.0), (left + wall_t, back_y, wall_h), 'nc_concrete_dark', tile=(3, 2))
    M.box((right - wall_t, front_y, 0.0), (right, back_y, wall_h), 'nc_concrete_dark', tile=(3, 2))
    M.box((left, back_y - wall_t, 0.0), (right, back_y, wall_h), 'nc_concrete_dark', tile=(4, 2))
    C.box((left, front_y, 0.0), (left + wall_t, back_y, wall_h))
    C.box((right - wall_t, front_y, 0.0), (right, back_y, wall_h))
    C.box((left, back_y - wall_t, 0.0), (right, back_y, wall_h))
    for x in np.arange(left + 5.0, right - 1.0, 7.0):
        M.box((x - 0.18, back_y - 0.42, 0.0), (x + 0.18, back_y, wall_h + 0.35), 'nc_concrete', tile=(1, 2))
        C.box((x - 0.18, back_y - 0.42, 0.0), (x + 0.18, back_y, wall_h + 0.35))
    # Align the gate opening to the attached garage and keep the long asphalt drive clear.
    garage_w = min(6.3, w * 0.34)
    main_w = w - garage_w * 0.78
    gx0, gx1 = main_w * 0.34, w / 2
    gate0, gate1 = gx0 - 0.55, gx1 + 0.55
    M.box((left, front_y, 0.0), (gate0, front_y + wall_t, wall_h), 'nc_concrete_dark', tile=(3, 2))
    M.box((gate1, front_y, 0.0), (right, front_y + wall_t, wall_h), 'nc_concrete_dark', tile=(3, 2))
    for x in (gate0, gate1):
        M.box((x - 0.42, front_y - 0.25, 0.0), (x + 0.42, front_y + wall_t + 0.25, wall_h + 0.55), 'nc_concrete', tile=(1, 2))
        C.box((x - 0.42, front_y - 0.25, 0.0), (x + 0.42, front_y + wall_t + 0.25, wall_h + 0.55))
    drive_lo, drive_hi = gx0 + 0.35, gx1 - 0.35
    M.box((drive_lo, front_y + wall_t, 0.015), (drive_hi, -d / 2 - 6.85, 0.04), 'nc_asphalt', tile=(3, 7), skip=('-z',))
    C.box((drive_lo, front_y + wall_t, 0.0), (drive_hi, -d / 2 - 6.85, 0.04))
    # Small rear swimming pool, stone patio and two low landscape planters.
    pool_y0, pool_y1 = d / 2 + 1.5, d / 2 + 7.0
    M.box((-6.6, pool_y0 - 0.35, 0.015), (6.6, pool_y1 + 0.35, 0.20), 'nc_concrete', tile=(3, 3))
    M.box((-5.9, pool_y0, 0.04), (5.9, pool_y1, 0.12), 'nc_glass_c', tile=(3, 3))
    C.box((-6.6, pool_y0 - 0.35, 0.0), (6.6, pool_y1 + 0.35, 0.20))
    for x in (-lot_w * 0.36, lot_w * 0.36):
        M.merge(P.street_tree(5.8, 1), (x, front_y + 7.0, 0.0), rz=180.0)
        M.merge(P.planter(3.0, 1.2), (x, back_y - 2.1, 0.0), rz=180.0)
        C.box((x - 0.28, front_y + 6.72, 0.0), (x + 0.28, front_y + 7.28, 2.9))
    return M, C, _meta('estate_house', lot_w, d + 22.0, base['h'] + 1.0, base['floors'], 480.0, style=style, pool=True)


def strip_mall(w, d, seed, shops=4):
    """Low-rise strip retail with varied shop bays and a parking court in front."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    h = 6.1
    kinds = ('retail', 'food', 'retail', 'retail', 'food')
    K.podium(M, C, w, d, rng, kinds=kinds[:max(2, min(5, int(shops)))], h=h, mat_base='nc_concrete', canopy=False)
    poly = rect(w, d)
    M.box((-w / 2, -d / 2, h), (w / 2, d / 2, h + 0.55), 'nc_concrete', tile=(3, 1))
    K.parapet(M, poly, h + 0.55, 0.65, mat='nc_concrete_dark')
    K.roof_clutter(M, rng, poly, h + 0.55, n_ac=3, n_tank=0, n_ant=0, n_hvac=2, edge=3.0)
    # A single subdued fascia sign and canvas canopies on the street-facing side.
    front = rect(w, d)
    K.wall_sign(M, front[0], front[1], h - 1.0, 'h', int(rng.integers(0, 32)), min(w * 0.45, 16.0), 1.15)
    M.box((-w * 0.42, -d / 2 - 1.0, 3.7), (w * 0.42, -d / 2 + 0.15, 3.92), 'nc_metal_light', tile=(3, 1))
    C.box((-w / 2, -d / 2, h), (w / 2, d / 2, h + 1.2))
    return M, C, _meta('strip_mall', w, d, h + 2.0, 1, 440.0, shops=shops)


def roadside_shop(w, d, seed, kind='diner'):
    """Compact US roadside diner, quick-service restaurant or glass showroom."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    kind = str(kind)
    h = 6.8 if kind in ('diner', 'fast_food') else 8.0
    wall = 'nc_shop_food' if kind in ('diner', 'fast_food') else 'nc_shop_retail'
    poly = rect(w - 1.0, d - 1.0)
    M.extrude(poly, 0.0, 0.28, 'nc_concrete_dark', 'nc_concrete', tile=(4, 4))
    for i in range(4):
        M.wall(poly[i], poly[(i + 1) % 4], 0.28, h, wall, tile=(4.0, 1.8), emis=0.05)
    M.box((-w / 2, -d / 2, h), (w / 2, d / 2, h + 0.45), 'nc_concrete', tile=(4, 3))
    K.parapet(M, poly, h + 0.45, 0.55, mat='nc_concrete_dark')
    # Warm front windows and a narrow restrained sign band.
    K.wall_sign(M, poly[0], poly[1], h - 1.1, 'h', int(rng.integers(0, 32)), min(13.0, w * 0.46), 1.45)
    front_y = -d / 2 - 0.12
    for x in (-w * 0.28, w * 0.28):
        M.box((x - 2.4, front_y - 0.05, 1.0), (x + 2.4, front_y + 0.04, h - 1.7), 'nc_glass_b', tile=(2, 2))
    M.box((-w * 0.42, -d / 2 - 1.5, 3.2), (w * 0.42, -d / 2 + 0.2, 3.45), 'nc_metal_light', tile=(2, 1))
    K.roof_clutter(M, rng, poly, h + 0.45, n_ac=2, n_tank=0, n_ant=0, n_hvac=2, edge=2.5)
    C.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, h + 1.2))
    return M, C, _meta(kind, w, d, h + 1.2, 1, 450.0)


def gas_station(w, d, seed):
    """Corner fuel stop: convenience shop, canopy, four pumps and a restrained highway sign."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    # Store occupies the rear half of the parcel.
    sw, sd, cy, sh = min(19.0, w * 0.45), min(15.0, d * 0.40), d * 0.24, 5.8
    p = rect(sw, sd, 0.0, cy)
    M.extrude(p, 0.0, 0.25, 'nc_concrete_dark', 'nc_concrete', tile=(3, 3))
    for i in range(4):
        M.wall(p[i], p[(i + 1) % 4], 0.25, sh, 'nc_shop_retail' if i != 0 else 'nc_shop_food', tile=(3, 1.5), emis=0.05)
    M.box((-sw / 2, cy - sd / 2, sh), (sw / 2, cy + sd / 2, sh + 0.55), 'nc_concrete', tile=(3, 2))
    C.box((-sw / 2, cy - sd / 2, 0), (sw / 2, cy + sd / 2, sh + 0.7))
    # Flat canopy facing the street.
    canopy_w, canopy_d = min(w * 0.72, 31.0), min(d * 0.47, 18.0)
    y0, y1, cz = -d * 0.38, -d * 0.38 + canopy_d, 5.0
    M.box((-canopy_w / 2, y0, cz), (canopy_w / 2, y1, cz + 0.38), 'nc_concrete', tile=(4, 3))
    M.box((-canopy_w / 2 - 0.2, y0 - 0.08, cz + 0.30), (canopy_w / 2 + 0.2, y1 + 0.08, cz + 0.48), 'nc_metal_light', tile=(4, 1))
    for x in (-canopy_w * 0.42, canopy_w * 0.42):
        for y in (y0 + 0.7, y1 - 0.7):
            M.box((x - 0.16, y - 0.16, 0.0), (x + 0.16, y + 0.16, cz), 'nc_metal_light', tile=(1, 2))
            C.box((x - 0.22, y - 0.22, 0.0), (x + 0.22, y + 0.22, cz))
    # Four modern pump islands; no vehicles are baked into the scene.
    for x in (-canopy_w * 0.18, canopy_w * 0.18):
        for y in (y0 + canopy_d * 0.33, y0 + canopy_d * 0.69):
            M.box((x - 1.1, y - 1.5, 0.0), (x + 1.1, y + 1.5, 0.18), 'nc_concrete', tile=(1, 1))
            M.box((x - 0.48, y - 0.40, 0.18), (x + 0.48, y + 0.40, 1.70), 'nc_metal_light', tile=(1, 2))
            M.box((x - 0.31, y - 0.43, 1.17), (x + 0.31, y - 0.40, 1.45), 'nc_glass_a', tile=(1, 1))
            M.box((x + 0.48, y - 0.08, 0.60), (x + 0.70, y + 0.08, 1.35), 'nc_metal_dark', tile=(1, 2))
            C.box((x - 0.50, y - 0.42, 0.18), (x + 0.50, y + 0.42, 1.70))
    # Restrained fascia lights and a pole sign visible from the arterial.
    M.box((-canopy_w / 2 + 0.2, y0 - 0.04, cz + 0.48), (canopy_w / 2 - 0.2, y0 + 0.02, cz + 0.54), 'nc_light_amber', tile=(2, 1), emis=0.35)
    sign_x, sign_y = -w * 0.34, -d * 0.28
    M.cyl((sign_x, sign_y), 0.18, 0, 8.5, 10, 'nc_metal_light', tile=(1, 2), top_mat='nc_metal_light')
    M.box((sign_x - 2.8, sign_y - 0.25, 5.3), (sign_x + 2.8, sign_y + 0.25, 7.6), 'nc_concrete_dark', tile=(2, 2))
    K.wall_sign(M, np.array([sign_x - 2.5, sign_y - 0.26]), np.array([sign_x + 2.5, sign_y - 0.26]), 6.5,
                'h', int(rng.integers(0, 32)), 4.5, 1.5)
    C.box((sign_x - 0.25, sign_y - 0.25, 0), (sign_x + 0.25, sign_y + 0.25, 8.5))
    C.box((-canopy_w / 2, y0, cz), (canopy_w / 2, y1, cz + 0.48))
    return M, C, _meta('gas_station', w, d, 9.0, 1, 450.0)


def supermarket(w, d, seed):
    """Single-storey neighborhood grocery with a broad forecourt and marked surface parking."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    store_w, store_d = min(w - 8.0, 46.0), min(d * 0.48, 32.0)
    h, cy = 8.0, d * 0.18
    poly = rect(store_w, store_d, 0.0, cy)
    M.extrude(poly, 0.0, 0.30, 'nc_concrete_dark', 'nc_concrete', tile=(4, 4))
    for i in range(4):
        wall = 'nc_shop_retail' if i != 0 else 'nc_shop_food'
        M.wall(poly[i], poly[(i + 1) % 4], 0.30, h, wall, tile=(5.0, 2.0), emis=0.025)
    M.box((-store_w / 2, cy - store_d / 2, h), (store_w / 2, cy + store_d / 2, h + 0.65), 'nc_concrete', tile=(5, 4))
    K.parapet(M, poly, h + 0.65, 0.45, mat='nc_concrete_dark')
    # Long glazed entrance facade, a sheltered loading-side door, and restrained sign bands.
    front_y = cy - store_d / 2
    for x in (-store_w * 0.32, -store_w * 0.10, store_w * 0.18, store_w * 0.38):
        M.box((x - 2.7, front_y - 0.08, 0.85), (x + 2.7, front_y + 0.06, 5.65), 'nc_glass_b', tile=(2, 2))
    M.box((-1.35, front_y - 0.10, 0.45), (1.35, front_y + 0.08, 6.6), 'nc_metal_dark', tile=(1, 2))
    M.box((-store_w * 0.46, front_y - 2.2, 5.7), (store_w * 0.46, front_y + 0.35, 5.98), 'nc_metal_light', tile=(4, 1))
    K.wall_sign(M, poly[0], poly[1], 6.9, 'h', int(rng.integers(0, 32)), min(17.0, store_w * 0.42), 1.25)
    # Parking stalls in two rows, sized for ordinary passenger cars rather than oversized vehicles.
    lot_x0, lot_x1 = -w / 2 + 4.0, w / 2 - 4.0
    n_stalls = max(4, int((lot_x1 - lot_x0) // 2.7))
    for row_y in (front_y - 12.0, front_y - 24.0):
        row_end = row_y + 7.0
        for k in range(n_stalls + 1):
            x = lot_x0 + k * (lot_x1 - lot_x0) / n_stalls
            M.box((x - 0.045, row_y, 0.02), (x + 0.045, row_end, 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
        M.box((lot_x0, row_end - 0.045, 0.02), (lot_x1, row_end + 0.045, 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
    # A small cart shelter and screened rear loading enclosure keep the big-box parcel legible at city scale.
    M.box((-w * 0.39, front_y - 7.0, 0.18), (-w * 0.22, front_y - 5.5, 2.1), 'nc_metal_dark', tile=(1, 2))
    M.box((store_w * 0.31, cy + store_d / 2 + 0.2, 0.3), (store_w * 0.45, cy + store_d / 2 + 3.8, 2.5), 'nc_concrete_dark', tile=(2, 2))
    K.roof_clutter(M, rng, poly, h + 0.65, n_ac=4, n_tank=0, n_ant=0, n_hvac=3, edge=3.0)
    C.box((-store_w / 2, cy - store_d / 2, 0.0), (store_w / 2, cy + store_d / 2, h + 1.1))
    C.box((-w * 0.40, front_y - 7.2, 0.0), (-w * 0.21, front_y - 5.3, 2.2))
    return M, C, _meta('supermarket', w, d, h + 2.0, 1, 480.0, parking_stalls=2 * n_stalls)


def dealership(w, d, seed):
    """Low modern auto showroom with glazed display wall, flags, and a striped forecourt."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    show_w, show_d = min(w * 0.58, 38.0), min(d * 0.32, 22.0)
    cy, h = d * 0.25, 8.6
    poly = rect(show_w, show_d, 0.0, cy)
    M.extrude(poly, 0.0, 0.24, 'nc_concrete_dark', 'nc_concrete', tile=(4, 3))
    for i in range(4):
        M.wall(poly[i], poly[(i + 1) % 4], 0.24, h, 'nc_glass_b' if i == 0 else 'nc_shop_retail',
               tile=(5.0, 2.4), emis=0.035)
    # Red-metal piers and a deep aluminum canopy frame the showroom's street-facing glass.
    front_y = cy - show_d / 2
    for x in (-show_w * 0.43, show_w * 0.43):
        M.box((x - 0.34, front_y - 0.28, 0.25), (x + 0.34, front_y + 0.12, h), 'nc_metal_dark', tile=(1, 3))
    M.box((-show_w / 2 - 1.2, front_y - 2.4, 7.35), (show_w / 2 + 1.2, front_y + 0.55, 7.75), 'nc_metal_light', tile=(5, 1))
    M.box((-show_w / 2, cy - show_d / 2, h), (show_w / 2, cy + show_d / 2, h + 0.6), 'nc_concrete_dark', tile=(4, 3))
    K.parapet(M, poly, h + 0.6, 0.45, mat='nc_metal_dark')
    K.wall_sign(M, poly[0], poly[1], 6.45, 'h', int(rng.integers(0, 32)), min(14.0, show_w * 0.50), 1.35)
    # Three display pads and fine white stall lines reserve the foreground for MTA's own vehicles.
    lot_x0, lot_x1 = -w / 2 + 4.0, w / 2 - 4.0
    pad_y = front_y - 13.0
    pad_w = min(8.0, (lot_x1 - lot_x0) / 5.0)
    for k in range(3):
        x = (k - 1) * (pad_w + 4.0)
        M.box((x - pad_w / 2, pad_y - 5.0, 0.02), (x + pad_w / 2, pad_y + 5.0, 0.11), 'nc_concrete', tile=(2, 2))
        M.box((x - pad_w / 2, pad_y - 5.08, 0.11), (x + pad_w / 2, pad_y + 5.08, 0.16), 'nc_metal_light', tile=(2, 1))
    stall_y0, stall_y1 = front_y - 25.0, front_y - 18.0
    stalls = max(4, int((lot_x1 - lot_x0) // 3.0))
    for k in range(stalls + 1):
        x = lot_x0 + k * (lot_x1 - lot_x0) / stalls
        M.box((x - 0.045, stall_y0, 0.02), (x + 0.045, stall_y1, 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
    M.box((lot_x0, stall_y1 - 0.045, 0.02), (lot_x1, stall_y1 + 0.045, 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
    # Taller pole sign and two fabric flags identify this as a dealer rather than another retail box.
    sx, sy = -w * 0.38, -d * 0.13
    M.cyl((sx, sy), 0.17, 0.0, 11.0, 10, 'nc_metal_light', tile=(1, 2), top_mat='nc_metal_light')
    M.box((sx - 2.5, sy - 0.24, 7.2), (sx + 2.5, sy + 0.24, 9.7), 'nc_concrete_dark', tile=(2, 2))
    for fx in (-w * 0.44, w * 0.44):
        M.cyl((fx, -d * 0.18), 0.075, 0.0, 7.0, 8, 'nc_metal_light', tile=(1, 2), top_mat='nc_metal_light')
        M.quad((fx, -d * 0.18, 6.6), (fx + 1.8, -d * 0.18, 6.25), (fx + 1.8, -d * 0.18, 5.0), (fx, -d * 0.18, 5.35),
               'nc_light_amber', emis=0.12)
    C.box((-show_w / 2, cy - show_d / 2, 0.0), (show_w / 2, cy + show_d / 2, h + 0.8))
    C.box((sx - 0.23, sy - 0.23, 0.0), (sx + 0.23, sy + 0.23, 11.0))
    return M, C, _meta('dealership', w, d, 12.0, 1, 480.0, display_pads=3)


def motel(w, d, seed):
    """Two-storey roadside motel with exterior galleries and a stair tower."""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    w, d = float(w), float(d)
    poly = rect(w - 1.0, d - 1.0)
    z0, floor_h, floors = 0.25, 3.25, 2
    K.tier(M, C, poly, z0, z0 + floors * floor_h, 'nc_wall_tenement_a', rng, emis=0.05,
           bays_tile=4, floors_tile=4, bay_w=3.0, floor_h=floor_h, corners=False, roof=False)
    roof_z = z0 + floors * floor_h
    M.box((-w / 2, -d / 2, roof_z), (w / 2, d / 2, roof_z + 0.55), 'nc_concrete', tile=(4, 4))
    K.parapet(M, poly, roof_z + 0.55, 0.75, mat='nc_concrete_dark')
    # Exterior access galleries, repeated door bays and guardrails.
    for floor in range(floors):
        z = z0 + (floor + 1) * floor_h
        M.box((-w / 2 + 0.5, -d / 2 - 1.6, z), (w / 2 - 0.5, -d / 2 + 0.4, z + 0.14), 'nc_concrete', tile=(3, 1))
        M.box((-w / 2 + 0.5, -d / 2 - 1.62, z + 1.0), (w / 2 - 0.5, -d / 2 - 1.50, z + 1.05), 'nc_metal_dark', tile=(2, 1))
        npost = max(3, int(w // 5))
        for k in range(npost + 1):
            x = -w / 2 + 0.7 + k * (w - 1.4) / npost
            M.box((x - 0.04, -d / 2 - 1.62, z + 0.1), (x + 0.04, -d / 2 - 1.50, z + 1.0), 'nc_metal_dark', tile=(1, 2))
        for k in range(max(2, int(w // 4))):
            x = -w / 2 + 2.0 + k * (w - 4.0) / max(1, int(w // 4) - 1)
            M.box((x - 0.52, -d / 2 - 0.06, z - 2.5), (x + 0.52, -d / 2 + 0.08, z - 0.55), 'nc_glass_b', tile=(1, 2))
    # Exterior stair flights at each end.
    for sx in (-1, 1):
        x = sx * (w / 2 - 2.5)
        for k in range(12):
            zz = 0.35 + k * 0.52
            yy = -d / 2 - 1.2 + k * 0.12
            M.box((x - 0.55, yy - 0.35, zz), (x + 0.55, yy + 0.35, zz + 0.10), 'nc_concrete', tile=(1, 1))
        P.bar(M, (x - 0.65, -d / 2 - 1.5, 0.8), (x - 0.65, -d / 2 + 0.1, roof_z), 0.08, 'nc_metal_dark')
        P.bar(M, (x + 0.65, -d / 2 - 1.5, 0.8), (x + 0.65, -d / 2 + 0.1, roof_z), 0.08, 'nc_metal_dark')
    K.wall_sign(M, poly[0], poly[1], 6.0, 'h', int(rng.integers(0, 32)), min(12.0, w * 0.28), 1.5)
    K.roof_clutter(M, rng, poly, roof_z + 0.55, n_ac=4, n_hvac=2, n_ant=0, edge=3)
    C.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, roof_z + 1.0))
    C.box((-w / 2, -d / 2 - 1.7, z0), (w / 2, -d / 2 + 0.4, roof_z + 0.15))
    return M, C, _meta('motel', w, d + 4.0, roof_z + 2.0, floors, 480.0)


# registry used by the plan / builder
ARCH = {
    'tower_setback': tower_setback, 'tower_cyl': tower_cyl, 'tower_twin': tower_twin, 'arcology': arcology,
    'midrise': midrise, 'tenement': tenement, 'slab': slab, 'megablock': megablock,
    'warehouse': warehouse, 'factory': factory, 'tank_farm': tank_farm, 'container_yard': container_yard, 'garage': garage,
    'plaza_gate': plaza_gate, 'family_house': family_house, 'estate_house': estate_house, 'strip_mall': strip_mall,
    'roadside_shop': roadside_shop, 'gas_station': gas_station, 'supermarket': supermarket,
    'dealership': dealership, 'motel': motel,
}
