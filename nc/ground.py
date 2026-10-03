# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# ground.py - one model per city cell: road surface with lane markings and crosswalks, kerbs, pavements, block pad,
#             street furniture and light pools.  A cell spans from street centre line to street centre line, so
#             neighbouring cells meet in the middle of every street.  Local origin = centre of the cell, z = 0 road level.
#
#             street classes:  A avenue (36 m: 24 m carriageway + 2 x 6 m pavement)
#                              S street (22 m: 14 m carriageway + 2 x 4 m pavement)
#                              N lane   (14 m:  8 m carriageway + 2 x 3 m pavement)
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, unit
from . import parts as P

CURB = 0.16
SW = {'A': 36.0, 'S': 22.0, 'N': 14.0}
CARR = {'A': 24.0, 'S': 14.0, 'N': 8.0}
SIDE = {'A': 6.0, 'S': 4.0, 'N': 3.0}
ROAD = {'A': 'nc_road_ave', 'S': 'nc_road_str', 'N': 'nc_road_local'}
CW_DEPTH = 4.0
PAD_TILE = {'nc_sidewalk': (3.6, 3.6), 'nc_plaza': (4.8, 4.8), 'nc_concrete': (4.0, 4.0), 'nc_alley': (6.0, 6.0),
            'nc_asphalt': (12.0, 12.0), 'nc_grass': (6.0, 6.0), 'nc_sand': (5.0, 5.0)}
RIVER_Z = -3.0          # water level below the road
BED_Z = -7.0
QUAY = 8.0


def cell_dims(bw, bd, cls):
    w, e, s, n = cls
    return bw + SW[w] / 2 + SW[e] / 2, bd + SW[s] / 2 + SW[n] / 2


def _strip(M, axis, a0, a1, c0, c1, cls, half, cw_both=True, crosswalk=True):
    """road strip.  axis 'x': spans x in [a0,a1], y in [c0,c1]; axis 'y': spans y in [a0,a1], x in [c0,c1].
    half = 'left' | 'right' (which half of the carriageway texture the cell owns, seen along +axis)"""
    u = (0.0, 0.5) if half == 'left' else (0.5, 1.0)
    mid = (c0 + c1) / 2
    hw = abs(c1 - c0) / 2
    L = a1 - a0
    if L < 1.0:
        return
    cwp = crosswalk if isinstance(crosswalk, tuple) else (crosswalk, crosswalk)
    cw0 = CW_DEPTH if (cwp[0] and L > 3 * CW_DEPTH) else 0.0
    cw1 = CW_DEPTH if (cwp[1] and L > 3 * CW_DEPTH) else 0.0
    m0, m1 = a0 + cw0, a1 - cw1
    if axis == 'x':
        path = [(m0, mid, 0.0), (m1, mid, 0.0)]
    else:
        path = [(mid, m0, 0.0), (mid, m1, 0.0)]
    M.ribbon(path, hw, ROAD[cls], tile_v=8.0, u=u, v0=0.0)
    for end, cw in ((0, cw0), (1, cw1)):
        if cw > 0:
            if axis == 'x':
                xa, xb = (a0, a0 + cw) if end == 0 else (a1 - cw, a1)
                ya, yb = min(c0, c1), max(c0, c1)
                # stripes run along x; stop line on the side away from the intersection
                stop_x = xb if end == 0 else xa
                P4 = [(xa, ya, 0), (xb, ya, 0), (xb, yb, 0), (xa, yb, 0)]
                # texture v: 1 = stop line end, 0 = stripe end -> v = 1 - distance/cw measured from the stop line
                UV = [[0.0, 1 - abs(xa - stop_x) / cw], [0.0, 1 - abs(xb - stop_x) / cw], [(yb - ya) / 4.0, 1 - abs(xb - stop_x) / cw], [(yb - ya) / 4.0, 1 - abs(xa - stop_x) / cw]]
                M.quads(np.array(P4)[None], 'nc_crosswalk', np.array(UV)[None])
            else:
                ya, yb = (a0, a0 + cw) if end == 0 else (a1 - cw, a1)
                xa, xb = min(c0, c1), max(c0, c1)
                stop_y = yb if end == 0 else ya
                # corners CCW from above: (xa,ya) (xb,ya) (xb,yb) (xa,yb); stripes run along y
                vv = lambda y: 1 - abs(y - stop_y) / cw
                UV = [[0.0, vv(ya)], [(xb - xa) / 4.0, vv(ya)], [(xb - xa) / 4.0, vv(yb)], [0.0, vv(yb)]]
                M.quads(np.array([(xa, ya, 0), (xb, ya, 0), (xb, yb, 0), (xa, yb, 0)])[None], 'nc_crosswalk', np.array(UV)[None])


def _octagon(x0, y0, x1, y1, cc):
    return np.array([(x0 + cc, y0), (x1 - cc, y0), (x1, y0 + cc), (x1, y1 - cc), (x1 - cc, y1), (x0 + cc, y1), (x0, y1 - cc), (x0, y0 + cc)], float)


def _paint_segment(M, p0, p1, width=0.12, z=0.025):
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    d = b - a
    n = unit(np.array([-d[1], d[0]])) * width / 2.0
    poly = [(a[0] - n[0], a[1] - n[1], z), (b[0] - n[0], b[1] - n[1], z),
            (b[0] + n[0], b[1] + n[1], z), (a[0] + n[0], a[1] + n[1], z)]
    M.poly(poly, 'nc_light_white', tile=(1, 1))


def _paint_left_arrow(M, center, travel, z=0.025):
    """Compact L-shaped left-turn arrow on an arterial approach."""
    d = unit(np.asarray(travel, float))
    left = np.array([-d[1], d[0]])
    c = np.asarray(center, float)
    bend = c - d * 0.68
    start = c - d * 2.55
    base = bend + left * 0.72
    tip = base + left * 0.72
    _paint_segment(M, start, bend, 0.24, z)
    _paint_segment(M, bend, base, 0.24, z)
    tri = [tuple(base - d * 0.56) + (z,), tuple(base + d * 0.56) + (z,), tuple(tip) + (z,)]
    M.poly(tri, 'nc_light_white', tile=(1, 1))


def _turn_pocket_markings(M, box, cls):
    """Paint short exclusive left-turn pockets/arrows on wide signalized approaches."""
    xl, xr, yb, yt, x0, x1, y0, y1 = box
    classes = {'A': (3, 2.0), 'S': (2, 0.0), 'N': (1, 0.0)}

    def geometry(road_cls):
        lanes, median = classes[road_cls]
        lane_w = (CARR[road_cls] - median - 0.7) / (2.0 * lanes)
        offset = median / 2.0 + lane_w / 2.0
        boundary = median / 2.0 + lane_w
        return offset, boundary

    cw_, ce_, cs_, cn_ = cls
    # Horizontal approaches: the south half travels east, the north half west.
    if cs_ in ('A', 'S'):
        off, line = geometry(cs_)
        yc = yb + off
        _paint_left_arrow(M, (x0 + 9.0, yc), (1, 0))
        _paint_left_arrow(M, (x1 - 9.0, yc), (-1, 0))
        if cs_ == 'A':
            yy = yb + line
            _paint_segment(M, (x0 + 4.2, yy), (min(x0 + 23.0, x1 - 10.0), yy))
            _paint_segment(M, (x1 - 4.2, yy), (max(x1 - 23.0, x0 + 10.0), yy))
    if cn_ in ('A', 'S'):
        off, line = geometry(cn_)
        yc = yt - off
        _paint_left_arrow(M, (x0 + 9.0, yc), (-1, 0))
        _paint_left_arrow(M, (x1 - 9.0, yc), (1, 0))
        if cn_ == 'A':
            yy = yt - line
            _paint_segment(M, (x0 + 4.2, yy), (min(x0 + 23.0, x1 - 10.0), yy))
            _paint_segment(M, (x1 - 4.2, yy), (max(x1 - 23.0, x0 + 10.0), yy))
    # Vertical approaches: the west half travels north, the east half south.
    if cw_ in ('A', 'S'):
        off, line = geometry(cw_)
        xc = xl + off
        _paint_left_arrow(M, (xc, y0 + 9.0), (0, 1))
        _paint_left_arrow(M, (xc, y1 - 9.0), (0, -1))
        if cw_ == 'A':
            xx = xl + line
            _paint_segment(M, (xx, y0 + 4.2), (xx, min(y0 + 23.0, y1 - 10.0)))
            _paint_segment(M, (xx, y1 - 4.2), (xx, max(y1 - 23.0, y0 + 10.0)))
    if ce_ in ('A', 'S'):
        off, line = geometry(ce_)
        xc = xr - off
        _paint_left_arrow(M, (xc, y0 + 9.0), (0, 1))
        _paint_left_arrow(M, (xc, y1 - 9.0), (0, -1))
        if ce_ == 'A':
            xx = xr - line
            _paint_segment(M, (xx, y0 + 4.2), (xx, min(y0 + 23.0, y1 - 10.0)))
            _paint_segment(M, (xx, y1 - 4.2), (xx, max(y1 - 23.0, y0 + 10.0)))


def _lamp_line(M, rng, p0, p1, arm_rz, spacing, style, start=0.0):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 8:
        return []
    n = max(1, int(round(L / spacing)))
    out = []
    for k in range(n):
        p = p0 + (p1 - p0) * ((k + 0.5) / n)
        sod = (style == 'ind') or (style in ('ent', 'commercial') and rng.random() < 0.18) or (style == 'market' and rng.random() < 0.25)
        lamp_h = 7.5 if style in ('res', 'suburb', 'hillside', 'park') else 9.0
        M.merge(P.street_lamp(lamp_h, 2.4 if lamp_h < 9 else 2.8, bool(sod), False), (p[0], p[1], CURB), rz=arm_rz)
        out.append(p)
    return out


def _slab_pieces(xl, yb, xr, yt, rects):
    """rectangles covering [xl, xr] x [yb, yt] minus the hole rectangles (x0, y0, x1, y1)"""
    pieces = [(xl, yb, xr, yt)]
    for (hx0, hy0, hx1, hy1) in rects:
        nxt = []
        for (a0, b0, a1, b1) in pieces:
            if hx1 <= a0 or hx0 >= a1 or hy1 <= b0 or hy0 >= b1:
                nxt.append((a0, b0, a1, b1))
                continue
            if hx0 > a0:
                nxt.append((a0, b0, hx0, b1))
            if hx1 < a1:
                nxt.append((hx1, b0, a1, b1))
            ix0, ix1 = max(a0, hx0), min(a1, hx1)
            if hy0 > b0:
                nxt.append((ix0, b0, ix1, hy0))
            if hy1 < b1:
                nxt.append((ix0, hy1, ix1, b1))
        pieces = nxt
    return pieces


def build_cell(spec):
    """spec: dict(bw, bd, cls=(w,e,s,n), style, pad, alley=None|('x'|'y', offset, width), seed, river=False) -> (Mesh, Col, meta)"""
    rng = np.random.default_rng(spec['seed'])
    bw, bd = spec['bw'], spec['bd']
    cls = spec['cls']
    cw_, ce_, cs_, cn_ = cls
    W, D = cell_dims(bw, bd, cls)
    M, C = Mesh(), Col()
    style = spec.get('style', 'core')
    pad = spec.get('pad', 'nc_sidewalk')
    terrain = float(spec.get('terrain', 0.0))
    river = bool(spec.get('river', False))
    xl, xr, yb, yt = -W / 2, W / 2, -D / 2, D / 2
    # edges of the raised region (outer edge of the pavements = inner edge of the carriageways)
    x0, x1 = xl + CARR[cw_] / 2, xr - CARR[ce_] / 2
    y0, y1 = yb + CARR[cs_] / 2, yt - CARR[cn_] / 2
    # block rectangle (inside the pavements)
    bx0, bx1 = xl + SW[cw_] / 2, xr - SW[ce_] / 2
    by0, by1 = yb + SW[cs_] / 2, yt - SW[cn_] / 2
    cc = 3.0
    # trench cut-outs of the carriageway halves (the river tunnel's open ramps): (side 'w' | 'e', y0, y1) in cell coordinates
    holes = tuple(spec.get('holes', ()))
    hole_rects = [((xl, h0, x0, h1) if sd == 'w' else (x1, h0, xr, h1)) for (sd, h0, h1) in holes]

    def cut_strip(ca, cb, cl_, hf, side):
        """west / east carriageway half along y; a trench cut-out leaves the crosswalk only at the intersection ends"""
        cuts = [(h0, h1) for (sd, h0, h1) in holes if sd == side]
        if not cuts:
            _strip(M, 'y', y0, y1, ca, cb, cl_, hf)
            return
        a = y0
        for k, (h0, h1) in enumerate(sorted(cuts)):
            _strip(M, 'y', a, h0, ca, cb, cl_, hf, crosswalk=(k == 0, False))
            a = h1
        _strip(M, 'y', a, y1, ca, cb, cl_, hf, crosswalk=(False, True))

    # ------------------------------------------------------------------ road level frame
    gaps = sorted(spec.get('gaps', ()))

    def intervals(a, b):
        out, cur = [], a
        for g0, g1 in gaps:
            if g0 > cur:
                out.append((cur, min(g0, b)))
            cur = max(cur, g1)
        if cur < b:
            out.append((cur, b))
        return [(p, q) for p, q in out if q - p > 0.5]

    if river:
        # bank streets run over the full width (except where a bridge model takes over), the river sits between the promenades
        for (p, q) in intervals(xl, xr):
            _strip(M, 'x', p, q, yb, y0, cs_, 'left', crosswalk=False)
            _strip(M, 'x', p, q, y1, yt, cn_, 'right', crosswalk=False)
    else:
        _strip(M, 'x', x0, x1, yb, y0, cs_, 'left')
        _strip(M, 'x', x0, x1, y1, yt, cn_, 'right')
        cut_strip(xl, x0, cw_, 'right', 'w')
        cut_strip(x1, xr, ce_, 'left', 'e')
        # intersection boxes (the rest of the west / east strips below / above the raised region)
        for (ax0, ay0, ax1, ay1) in ((xl, yb, x0, y0), (x1, yb, xr, y0), (xl, y1, x0, yt), (x1, y1, xr, yt)):
            M.hquad(ax0, ay0, ax1, ay1, 0.0, 'nc_asphalt', tile=(12.0, 12.0))
        for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
            pts = [(cx, cy, 0.0), (cx + sx * cc, cy, 0.0), (cx, cy + sy * cc, 0.0)]
            if sx * sy < 0:
                pts = [pts[0], pts[2], pts[1]]
            M.poly(pts, 'nc_asphalt', (12.0, 12.0))
    # ------------------------------------------------------------------ raised pavement + curbs
    if not river:
        oct_ = _octagon(x0, y0, x1, y1, cc)
        M.wall_strip(np.vstack([oct_, oct_[:1]]), 0.0, CURB, 'nc_curb', tile=(1.6, 1.6))
        o = oct_
        i0, i1, i2, i3 = (bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)
        pieces = [(o[0], o[1], i1, i0), (o[1], o[2], i1), (o[2], o[3], i2, i1), (o[3], o[4], i2), (o[4], o[5], i3, i2), (o[5], o[6], i3), (o[6], o[7], i0, i3), (o[7], o[0], i0)]
        for pc in pieces:
            M.poly([(p[0], p[1], CURB) for p in pc], 'nc_sidewalk', (3.6, 3.6))
        # block pad: landscaped lawns / gentle hillside parcels, a pedestrian alley, or a striped retail car park.
        al = spec.get('alley')
        if al is None and terrain > 0.0:
            # Smooth parcel mounds stay level with the sidewalks; hillside homes get subtly graded, flat building pads.
            houseplots = tuple(spec.get('houseplots', ()))
            nx = ny = 20 if houseplots else 12
            xs = np.linspace(bx0, bx1, nx + 1)
            ys = np.linspace(by0, by1, ny + 1)
            cxh, cyh = (bx0 + bx1) / 2, (by0 + by1) / 2
            hx, hy = max(1.0, (bx1 - bx0) / 2), max(1.0, (by1 - by0) / 2)
            pads = []
            for px, py, pw, pd in houseplots:
                qx = float(np.clip(cxh, px - pw / 2, px + pw / 2))
                qy = float(np.clip(cyh, py - pd / 2, py + pd / 2))
                ux, uy = (qx - cxh) / hx, (qy - cyh) / hy
                zpad = CURB + terrain * max(0.0, 1.0 - ux * ux) * max(0.0, 1.0 - uy * uy)
                pads.append((float(px), float(py), float(pw), float(pd), zpad))
            zcap = max((p[4] for p in pads), default=float('inf')) + 0.12
            heights = np.zeros((ny + 1, nx + 1), np.float64)
            for iy, yy in enumerate(ys):
                for ix, xx in enumerate(xs):
                    ux, uy = (xx - cxh) / hx, (yy - cyh) / hy
                    natural = CURB + terrain * max(0.0, 1.0 - ux * ux) * max(0.0, 1.0 - uy * uy)
                    z = min(natural, zcap)
                    for px, py, pw, pd, zpad in pads:
                        dx, dy = max(abs(xx - px) - pw / 2, 0.0), max(abs(yy - py) - pd / 2, 0.0)
                        distance = float(np.hypot(dx, dy))
                        if distance < 6.0:
                            t = distance / 6.0
                            blend = t * t * (3.0 - 2.0 * t)
                            z = zpad * (1.0 - blend) + z * blend
                    heights[iy, ix] = z
            vv = np.array([[(xx, yy, heights[iy, ix]) for ix, xx in enumerate(xs)] for iy, yy in enumerate(ys)], np.float64).reshape(-1, 3)
            ff = []
            for iy in range(ny):
                for ix in range(nx):
                    a0 = iy * (nx + 1) + ix
                    a1, b1, b0 = a0 + 1, a0 + nx + 2, a0 + nx + 1
                    M.quad(vv[a0], vv[a1], vv[b1], vv[b0], pad, tile=PAD_TILE.get(pad, (4, 4)))
                    ff.extend(((a0, a1, b1), (a0, b1, b0)))
            C.mesh(vv, np.asarray(ff, np.int64), 0)
        elif al is None:
            M.hquad(bx0, by0, bx1, by1, CURB, pad, tile=PAD_TILE.get(pad, (4, 4)))
        else:
            ax, off, aw = al
            if ax == 'x':
                ay = (by0 + by1) / 2 + off
                M.hquad(bx0, by0, bx1, ay - aw / 2, CURB, pad, tile=PAD_TILE.get(pad, (4, 4)))
                M.hquad(bx0, ay + aw / 2, bx1, by1, CURB, pad, tile=PAD_TILE.get(pad, (4, 4)))
                M.hquad(bx0, ay - aw / 2, bx1, ay + aw / 2, CURB, 'nc_alley', tile=(6.0, 6.0))
            else:
                axx = (bx0 + bx1) / 2 + off
                M.hquad(bx0, by0, axx - aw / 2, by1, CURB, pad, tile=PAD_TILE.get(pad, (4, 4)))
                M.hquad(axx + aw / 2, by0, bx1, by1, CURB, pad, tile=PAD_TILE.get(pad, (4, 4)))
                M.hquad(axx - aw / 2, by0, axx + aw / 2, by1, CURB, 'nc_alley', tile=(6.0, 6.0))
        if spec.get('parking'):
            # Two rows of realistically sized stalls, a 6.2 m aisle and a few planting islands.
            pw = bx1 - bx0
            nstalls = max(4, int(pw // 3.0))
            xs_stall = np.linspace(bx0 + 2.0, bx1 - 2.0, nstalls + 1)
            y_front = by0 + 3.8
            for row in range(2):
                ybase = y_front + row * 11.7
                for xx in xs_stall:
                    M.box((xx - 0.055, ybase, CURB + 0.02), (xx + 0.055, ybase + 5.0, CURB + 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
                M.box((bx0 + 2.0, ybase + 5.0, CURB + 0.02), (bx1 - 2.0, ybase + 5.10, CURB + 0.035), 'nc_light_white', tile=(1, 1), skip=('-z',))
            for xx in (bx0 + 8.0, bx1 - 8.0):
                island = np.array([[xx - 1.1, by0 + 1.0], [xx + 1.1, by0 + 1.0], [xx + 1.1, by1 - 1.0], [xx - 1.1, by1 - 1.0]])
                M.extrude(island, CURB, CURB + 0.08, 'nc_curb', 'nc_grass', tile=(3, 3))
        for (a0, b0, a1, b1) in _slab_pieces(xl, yb, xr, yt, hole_rects):
            C.box((a0, b0, -0.6), (a1, b1, 0.0))
        # the raised pavement is an octagon (3 m chamfered corners, the chamfers are plain road): three convex prisms cover it exactly
        for poly in ([(x0, y0 + cc), (x0 + cc, y0), (x0 + cc, y1), (x0, y1 - cc)],
                     [(x0 + cc, y0), (x1 - cc, y0), (x1 - cc, y1), (x0 + cc, y1)],
                     [(x1 - cc, y0), (x1, y0 + cc), (x1, y1 - cc), (x1 - cc, y1)]):
            C.slab(poly, 0.0, CURB)
    else:
        # promenades along both banks, quay walls, river bed (x intervals between the bridge gaps)
        pa = SIDE[cs_] + QUAY
        pb = SIDE[cn_] + QUAY
        ys0, ys1 = y0, y0 + pa
        yn0, yn1 = y1 - pb, y1
        M.hquad(xl, ys1, xr, yn0, BED_Z, 'nc_riverbed', tile=(6.0, 6.0))
        for (p, q) in intervals(xl, xr):
            M.hquad(p, ys0, q, ys1, CURB, 'nc_sidewalk', tile=(3.6, 3.6))
            M.hquad(p, yn0, q, yn1, CURB, 'nc_sidewalk', tile=(3.6, 3.6))
            # kerb faces towards the roads (travel +x: outside on the right = -y for the south bank, reversed for the north bank)
            M.wall(np.array([p, y0]), np.array([q, y0]), 0.0, CURB, 'nc_curb', tile=(1.6, 1.6))
            M.wall(np.array([q, y1]), np.array([p, y1]), 0.0, CURB, 'nc_curb', tile=(1.6, 1.6))
            # quay walls: the outside faces the water
            M.wall(np.array([q, ys1]), np.array([p, ys1]), BED_Z, CURB, 'nc_concrete_dark', tile=(4.0, 4.0))
            M.wall(np.array([p, yn0]), np.array([q, yn0]), BED_Z, CURB, 'nc_concrete_dark', tile=(4.0, 4.0))
            for (yy, sg) in ((ys1, 1), (yn0, -1)):
                M.box((p, yy - 0.12 if sg > 0 else yy, CURB), (q, yy if sg > 0 else yy + 0.12, CURB + 0.04), 'nc_strip_cyan', tile=(1, 1), emis=1.0, skip=('-z',))
                for x in np.arange(p + 6, q - 3, 12.0):
                    M.merge(P.bollard(), (x, yy - 0.7 * sg, CURB))
                M.box((p, yy - 0.3 * sg - 0.03, CURB + 1.0), (q, yy - 0.3 * sg + 0.03, CURB + 1.06), 'nc_metal_light', tile=(2, 2))
                for x in np.arange(p + 1, q, 5.0):
                    M.box((x - 0.04, yy - 0.3 * sg - 0.04, CURB), (x + 0.04, yy - 0.3 * sg + 0.04, CURB + 1.06), 'nc_metal_dark', tile=(1, 1))
            # collision: promenade slabs and quay walls
            C.box((p, ys0, 0.0), (q, ys1, CURB))
            C.box((p, yn0, 0.0), (q, yn1, CURB))
            C.box((p, ys1 - 0.8, BED_Z), (q, ys1, CURB))
            C.box((p, yn0, BED_Z), (q, yn0 + 0.8, CURB))
            if (q - p) > 20:
                for x in np.arange(p + 10, q - 5, 28.0):
                    for yy in (ys0 + SIDE[cs_] + 3.0, yn1 - SIDE[cn_] - 3.0):
                        M.merge(P.street_lamp(9.0, 2.8, False, False), (x, yy, CURB), rz=(180.0 if yy < 0 or yy < (ys0 + yn1) / 2 else 0.0))
        C.box((xl, yb, -0.6), (xr, ys0, 0.0))
        C.box((xl, yn1, -0.6), (xr, yt, 0.0))
        C.box((xl, ys1 - 1.0, BED_Z - 1.0), (xr, yn0 + 1.0, BED_Z))
    # ------------------------------------------------------------------ props
    lamp_pos = []
    if not river:
        off = 0.9
        sides = [((x0 + cc + 2, y0 + off), (x1 - cc - 2, y0 + off), 180.0),
                 ((x0 + cc + 2, y1 - off), (x1 - cc - 2, y1 - off), 0.0),
                 ((x0 + off, y0 + cc + 2), (x0 + off, y1 - cc - 2), 90.0),
                 ((x1 - off, y0 + cc + 2), (x1 - off, y1 - cc - 2), -90.0)]
        lamp_spacing = {'core': 34.0, 'ent': 38.0, 'market': 30.0, 'commercial': 38.0, 'res': 38.0,
                        'suburb': 46.0, 'hillside': 44.0, 'park': 52.0, 'waterfront': 42.0, 'ind': 48.0}.get(style, 40.0)
        for (p0, p1, rz) in sides:
            lamp_pos += _lamp_line(M, rng, p0, p1, rz, lamp_spacing, style)
        # American three-aspect signals with poles on all approaches at major junctions; quieter intersections get two heads.
        signal_corners = ((x0 + 1.3, y0 + 1.3, 180.0), (x1 - 1.3, y0 + 1.3, 90.0),
                          (x1 - 1.3, y1 - 1.3, 0.0), (x0 + 1.3, y1 - 1.3, -90.0))
        major = 'A' in cls or (cw_ == 'S' and ce_ == 'S' and cs_ == 'A') or (cn_ == 'A')
        for k, (cx, cy, rz) in enumerate(signal_corners if major else (signal_corners[0], signal_corners[2])):
            if not river:
                M.merge(P.traffic_signal(int(rng.integers(0, 3))), (cx, cy, CURB), rz=rz)
        if major and not holes:
            # Keep pavement arrows / pocket paint clear of a cut-and-cover tunnel portal.
            _turn_pocket_markings(M, (xl, xr, yb, yt, x0, x1, y0, y1), cls)
        # furniture along the pavement edge towards the block
        gap = SIDE['S'] * 0.5 + 0.3
        fx = []
        for side in range(4):
            if side == 0:
                a, b, nrm = (bx0 + 8, by0 - gap), (bx1 - 8, by0 - gap), (0, -1)
            elif side == 1:
                a, b, nrm = (bx0 + 8, by1 + gap), (bx1 - 8, by1 + gap), (0, 1)
            elif side == 2:
                a, b, nrm = (bx0 - gap, by0 + 8), (bx0 - gap, by1 - 8), (-1, 0)
            else:
                a, b, nrm = (bx1 + gap, by0 + 8), (bx1 + gap, by1 - 8), (1, 0)
            L = np.hypot(b[0] - a[0], b[1] - a[1])
            if L < 10:
                continue
            nitems = int(L // 14)
            for k in range(nitems):
                t = (k + 0.5) / max(1, nitems) + float(rng.uniform(-0.12, 0.12)) / max(1, nitems)
                px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                rz = P.yaw_facing(nrm[0], nrm[1])
                r = rng.random()
                if style == 'core':
                    item = P.planter(3.0, 1.0) if r < 0.52 else (P.bench() if r < 0.82 else P.trash_bin())
                elif style == 'market':
                    if r < 0.08:
                        item = P.parking_meter()
                    elif r < 0.23:
                        item = P.kiosk(int(rng.integers(0, 32)))
                    elif r < 0.36:
                        item = P.vending(int(rng.integers(0, 8)))
                    elif r < 0.58:
                        item = P.bench()
                    elif r < 0.82:
                        item = P.hydrant()
                    else:
                        item = P.trash_bin()
                elif style in ('ent', 'commercial'):
                    item = P.parking_meter() if r < 0.10 else (P.canopy(int(rng.integers(0, 5))) if r < 0.27 else (P.bench() if r < 0.48 else (P.planter(3.0, 1.0) if r < 0.72 else (P.hydrant() if r < 0.84 else P.trash_bin()))))
                elif style in ('res', 'suburb', 'hillside'):
                    item = P.parking_meter() if style == 'res' and r < 0.12 else (P.bench() if r < 0.44 else (P.planter(3.0, 1.0) if r < 0.70 else (P.hydrant() if r < 0.84 else P.trash_bin())))
                elif style in ('park', 'waterfront'):
                    item = P.bench() if r < 0.48 else (P.planter(3.2, 1.2) if r < 0.76 else P.trash_bin())
                else:
                    item = P.jersey_barrier(4.0) if r < 0.38 else (P.hydrant() if r < 0.60 else P.trash_bin())
                M.merge(item, (px, py, CURB), rz=rz)
        # Street trees are concentrated in neighborhood blocks and parks; palms are kept to the coast / warmer waterfront.
        if style in ('res', 'suburb', 'hillside', 'park', 'waterfront'):
            spacing = 23.0 if style in ('suburb', 'hillside') else (28.0 if style == 'park' else 34.0)
            tree_h = 8.5 if style in ('suburb', 'hillside') else 9.5
            for side, (a, b, nrm) in enumerate((( (bx0 + 7, by0 - gap), (bx1 - 7, by0 - gap), (0, -1)),
                                                 ( (bx0 + 7, by1 + gap), (bx1 - 7, by1 + gap), (0, 1)),
                                                 ( (bx0 - gap, by0 + 7), (bx0 - gap, by1 - 7), (-1, 0)),
                                                 ( (bx1 + gap, by0 + 7), (bx1 + gap, by1 - 7), (1, 0)))):
                L = float(np.hypot(b[0] - a[0], b[1] - a[1]))
                nt = max(1, int(L // spacing))
                for k in range(nt):
                    t = (k + 0.5) / nt
                    px = a[0] + (b[0] - a[0]) * t
                    py = a[1] + (b[1] - a[1]) * t
                    variant = int(rng.integers(0, 3))
                    if style == 'waterfront':
                        variant = 0 if rng.random() < 0.62 else int(rng.integers(1, 3))
                    elif style in ('suburb', 'hillside'):
                        variant = int(rng.integers(1, 3))
                    M.merge(P.street_tree(tree_h, variant), (px, py, CURB), rz=float(rng.integers(0, 360)))
                    C.box((px - 0.28, py - 0.28, CURB), (px + 0.28, py + 0.28, CURB + tree_h * 0.50))
        # utility poles with sagging cables are limited to the older main-street district.
        if style == 'market':
            for (a, b, rz) in (((bx0 - 1.2, by0 + 6), (bx0 - 1.2, by1 - 6), 0), ((bx1 + 1.2, by0 + 6), (bx1 + 1.2, by1 - 6), 0)):
                n = max(2, int(abs(b[1] - a[1]) // 16))
                pts = [np.array([a[0], a[1] + (b[1] - a[1]) * k / (n - 1)]) for k in range(n)]
                for p in pts:
                    M.merge(P.utility_pole(9.0), (p[0], p[1], CURB))
                for k in range(n - 1):
                    for dx, z in ((-0.8, 8.4), (0.0, 8.4), (0.8, 8.4)):
                        P.cable(M, (pts[k][0] + dx, pts[k][1], CURB + z), (pts[k + 1][0] + dx, pts[k + 1][1], CURB + z), sag=0.5, r=0.035, k=5)
    # manholes
    for _ in range(int(rng.integers(2, 6))):
        if river:
            break
        sx = rng.integers(4)
        if sx == 0:
            p = (rng.uniform(x0 + 8, x1 - 8), yb + CARR[cs_] / 4 + rng.uniform(-2, 2))
        elif sx == 1:
            p = (rng.uniform(x0 + 8, x1 - 8), yt - CARR[cn_] / 4 + rng.uniform(-2, 2))
        elif sx == 2:
            p = (xl + CARR[cw_] / 4 + rng.uniform(-2, 2), rng.uniform(y0 + 8, y1 - 8))
        else:
            p = (xr - CARR[ce_] / 4 + rng.uniform(-2, 2), rng.uniform(y0 + 8, y1 - 8))
        if any(r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3] for r in hole_rects):
            continue
        M.merge(P.manhole(), (p[0], p[1], 0.0))
    # light pools of the shop windows / signs that spill onto the pavements (vertex light only)
    if style in ('market', 'ent', 'commercial', 'core') and not river:
        for _ in range(max(1, int(W / 28))):
            sd = int(rng.integers(4))
            t = rng.uniform(0.1, 0.9)
            if sd == 0:
                p = (bx0 + (bx1 - bx0) * t, by0 - 2.0)
            elif sd == 1:
                p = (bx0 + (bx1 - bx0) * t, by1 + 2.0)
            elif sd == 2:
                p = (bx0 - 2.0, by0 + (by1 - by0) * t)
            else:
                p = (bx1 + 2.0, by0 + (by1 - by0) * t)
            c = [P.WARMW, P.COOL, (1.0, 0.52, 0.22)][int(rng.integers(3))]
            M.light((p[0], p[1], 2.0), c, 0.22 if style != 'core' else 0.18, 9.0)
    # lamp poles collide (thin boxes)
    for p in lamp_pos:
        C.box((p[0] - 0.2, p[1] - 0.2, CURB), (p[0] + 0.2, p[1] + 0.2, CURB + 9.0))
    meta = dict(kind='ground', w=float(W), d=float(D), h=float(max(10.0, terrain + 1.0)), dist=480.0, style=style,
                bw=bw, bd=bd, cls=''.join(cls), block=(float(bx0), float(by0), float(bx1), float(by1)), terrain=terrain)
    return M, C, meta


def build_sea_cell(spec):
    """Flat seabed tile beneath a matching MTA water quad; sea surfaces remain engine water, not opaque mesh."""
    w, d = float(spec['w']), float(spec['d'])
    M, C = Mesh(), Col()
    M.hquad(-w / 2, -d / 2, w / 2, d / 2, BED_Z, 'nc_riverbed', tile=(8.0, 8.0))
    C.box((-w / 2, -d / 2, BED_Z - 1.0), (w / 2, d / 2, BED_Z))
    return M, C, dict(kind='ground', w=w, d=d, h=BED_Z, dist=480.0, style='sea', bw=w, bd=d)
