# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# plan.py - the city plan: non-uniform American street grid, district recipes, bay + river, scenic routes, a two-level
#           interchange, expressways, bridges, sky bridges and a distant skyline.  All variation is deterministic.
#
# City frame: origin = centre of the city, x east, y north, z = street level (0).  Everything is deterministic.
# -----------------------------------------------------------------------------
import numpy as np
from .ground import SW, CARR, SIDE, CURB, QUAY, RIVER_Z, BED_Z, cell_dims
from . import ground, bld, infra, tunnel as TUN
from .bldkit import POD_H

# ---------------------------------------------------------------------------------------------
# grid
# ---------------------------------------------------------------------------------------------
XB = [56, 56, 56, 56, 88, 88, 128, 88, 72, 72, 72, 72]                 # block widths (west -> east)
XC = ['S', 'N', 'N', 'N', 'A', 'S', 'A', 'A', 'S', 'S', 'A', 'S', 'S']  # 13 street lines (x = const)
YB = [88, 88, 88, 88, 88, 130, 72, 72, 128, 88, 72, 72]                # block depths (south -> north), j = 5 is the river
YC = ['S', 'S', 'S', 'S', 'S', 'S', 'S', 'A', 'A', 'S', 'A', 'S', 'S']  # 13 street lines (y = const)
RIVER_J = 5
HERO = (6, 8)
SEA_DEPTH = 100.0
SEA_OFFSET = 10.0  # leave the south arterial landward of a short bay seawall
# Original fictional Westhaven plan: rows j = 11 (north) ... 0 (south), printed top = north.
# C downtown, K landmark, E mixed-use, M main street, R apartments, S suburbs, H hillside homes,
# F roadside retail, G parking, W waterfront, I working port, Q hillside park, B bayfront park, ~ river.
DISTRICTS = [
    "QQQQQQQQQQQQ",   # 11  ridge park / scenic drive
    "HHHHRRSSSSHH",   # 10  hillside estates and garden suburbs
    "RRRCCCEEEEHH",   # 9   downtown transition
    "MMMCCCKCCMMM",   # 8   central landmark and commercial core (HERO = (6, 8))
    "MMMMCCEEFFFF",   # 7   main street / mixed retail
    "WWMMMMMMWWRR",   # 6   north riverfront
    "~~~~~~~~~~~~",   # 5   river
    "WWWWWWWMMMFF",   # 4   south riverfront / marina district
    "FFMMEERRHHHH",   # 3   neighborhood commercial / apartments / hillside
    "FFRRMMIIRRHH",   # 2   retail corridor / working harbour
    "SSRRFFIIRRSS",   # 1   suburbs and bay-side businesses
    "BBBBBBBBBBBB",   # 0   bayfront greenway; curved coastal boulevard crosses this open strip
]
assert all(len(row) == len(XB) for row in DISTRICTS)
DIST = {j: DISTRICTS[11 - j] for j in range(12)}

EXPRESS_EW = dict(line=8, level=12.0)         # lower east-west deck
EXPRESS_NS = dict(line=8, level=22.0)         # upper north-south deck; set east of the core for a clear elevated interchange
BRIDGE_LINES = {1: 'N', 4: 'A', 6: 'A', 8: 'S', 10: 'A'}
HERO_BRIDGE_LINE = 6
# the road tunnel (cut-and-cover underpass): north - south under x line 9 (an 'S' street) NORTH of the river, from row 6 to row 9.  The road
# falls at 10 % through an open cut (64 m), enters the covered box tube right behind the portal header and runs flat 6.5 m below the
# street under three cross streets (two avenues and the lower expressway deck), then rises through the second open cut.  No water
# polygon lies above it: GTA treats everything below a water polygon as water, so the tunnel stays away from the river on purpose.
TUNNEL = dict(line=9, row_in=6, g=0.10, L_open=64.0, PT=1.2, flat_L=64.0, flat_n=5, variants=(0, 1, 2, 1, 0), start=15.0)

STYLE = {
    'C': 'core', 'K': 'core', 'P': 'park', 'Q': 'park', 'B': 'waterfront',
    'E': 'ent', 'G': 'ent', 'M': 'market', 'R': 'res', 'S': 'suburb', 'H': 'hillside',
    'W': 'waterfront', 'I': 'ind', 'T': 'ind', 'F': 'commercial', 'Y': 'ind', '~': 'waterfront',
}
PAD = {
    'C': 'nc_plaza', 'K': 'nc_plaza', 'P': 'nc_grass', 'Q': 'nc_grass', 'B': 'nc_grass',
    'E': 'nc_sidewalk', 'G': 'nc_asphalt', 'M': 'nc_sidewalk', 'R': 'nc_sidewalk',
    'S': 'nc_grass', 'H': 'nc_grass', 'W': 'nc_plaza', 'I': 'nc_concrete', 'T': 'nc_concrete',
    'F': 'nc_asphalt', 'Y': 'nc_concrete',
}

GLASSES = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_d', 'nc_glass_e', 'nc_glass_f', 'nc_glass_g', 'nc_glass_h']
LEDS = ['nc_strip_white', 'nc_strip_white', 'nc_light_amber', 'nc_strip_cyan']


class Plan:
    def __init__(self):
        self.models = {}          # name -> dict(kind, builder, args, cat)
        self.keys = {}            # (builder, frozen args) -> name
        self.placements = []      # dict(model, x, y, z, rz, tag)
        self.water = []           # (x0, y0, x1, y1, z)
        self.points = {}
        self.tour = []
        self.counts = {'g': 0, 'b': 0, 'i': 0, 's': 0}

    def model(self, cat, builder, args, hint=''):
        key = (builder, tuple(sorted((k, v if not isinstance(v, (list, tuple)) else tuple(v)) for k, v in args.items())))
        if key in self.keys:
            return self.keys[key]
        self.counts[cat] += 1
        name = 'nc_%s%03d' % (cat, self.counts[cat])
        self.models[name] = dict(cat=cat, builder=builder, args=dict(args), hint=hint)
        self.keys[key] = name
        return name

    def place(self, name, x, y, z, rz, tag):
        self.placements.append(dict(model=name, x=float(x), y=float(y), z=float(z), rz=float(rz), tag=tag))


def tunnel_geom(X, Y):
    """river tunnel in city coordinates -> dict(x, y_in, y_out, y_cov0, y_cov1, z_floor, parts=[...], holes=[(y0, y1) of the open cuts],
    prof=[(y, z) road level breakpoints]).  A part is dict(builder, args, y, z, rz)."""
    T = TUNNEL
    g, Lo, PT = T['g'], T['L_open'], T['PT']
    Lt = Lo + PT
    fl, fn = T['flat_L'], T['flat_n']
    x = X[T['line']]
    y_in = Y[T['row_in']] + T['start']           # behind the crosswalk of the street line in front of it
    z_floor = -g * Lt                            # road level at the portal header = flat road level of the tube
    parts = [dict(builder='tunnel_open', args=dict(L=Lo, pt=PT, g=g), y=y_in + Lt / 2, z=-g * Lt / 2, rz=0.0)]
    y = y_in + Lt
    y_a = y
    for k in range(fn):                          # covered box tube, flat
        parts.append(dict(builder='tunnel_tube', args=dict(L=fl, dz=0.0, variant=T['variants'][k % len(T['variants'])]), y=y + fl / 2, z=z_floor, rz=0.0))
        y += fl
    y_b = y
    parts.append(dict(builder='tunnel_open', args=dict(L=Lo, pt=PT, g=g), y=y_b + Lt / 2, z=-g * Lt / 2, rz=180.0))      # the open cut turned around
    y_out = y_b + Lt
    prof = [(y_in, 0.0), (y_a, z_floor), (y_b, z_floor), (y_out, 0.0)]
    return dict(x=x, y_in=y_in, y_out=y_out, y_cov0=y_a, y_cov1=y_b, y_a=y_a, y_b=y_b, z_floor=z_floor, parts=parts, prof=prof,
                holes=[(y_in, y_in + Lo), (y_b + PT, y_out)])


def tunnel_z(tg, y):
    """road level of the tunnel at world y"""
    ys = [p[0] for p in tg['prof']]
    zs = [p[1] for p in tg['prof']]
    return float(np.interp(y, ys, zs))


def tunnel_tour(tg):
    """camera keys that drive through the tunnel: eye x, y, z, look-at x, y, z, seconds to the next key (the eye follows the road profile)"""
    x = tg['x']

    def at(ye, yt, sec, h=1.7, ht=1.2):
        return (x, ye, tunnel_z(tg, ye) + h, x, yt, tunnel_z(tg, yt) + ht, sec)
    yi, yo, ya, yb = tg['y_in'], tg['y_out'], tg['y_a'], tg['y_b']
    return [
        (x, yi - 70.0, 7.0, x, yi + 40.0, tunnel_z(tg, yi + 40.0) + 0.5, 5.0),
        at(yi + 25.0, yi + 125.0, 5.0),
        at(ya + 10.0, ya + 110.0, 8.0),
        at(ya + 130.0, ya + 230.0, 8.0),
        at(ya + 250.0, ya + 350.0, 6.0),
        at(yb - 40.0, yb + 60.0, 5.0),
        at(yb + 20.0, yo, 5.0),
        (x, yo + 8.0, 1.9, x, yo + 110.0, 2.6, 6.0),
    ]


def house_pad_rise(bw, bd, dx, dy, house_w, house_d, scale):
    """maximum natural terrain height across a home's footprint, used for a level hillside foundation."""
    x = float(np.clip(0.0, dx - house_w / 2.0, dx + house_w / 2.0))
    y = float(np.clip(0.0, dy - house_d / 2.0, dy + house_d / 2.0))
    ux = x / max(1.0, float(bw) / 2.0)
    uy = y / max(1.0, float(bd) / 2.0)
    return float(scale) * max(0.0, 1.0 - ux * ux) * max(0.0, 1.0 - uy * uy)


def grid_lines():
    W = [XB[i] + SW[XC[i]] / 2 + SW[XC[i + 1]] / 2 for i in range(12)]
    D = [YB[j] + SW[YC[j]] / 2 + SW[YC[j + 1]] / 2 for j in range(12)]
    X = [0.0]
    for w in W:
        X.append(X[-1] + w)
    Y = [0.0]
    for d in D:
        Y.append(Y[-1] + d)
    # centre the grid on the middle of the whole map
    cx = (X[0] + X[-1]) / 2
    cy = (Y[0] + Y[-1]) / 2
    X = [x - cx for x in X]
    Y = [y - cy for y in Y]
    return X, Y, W, D


# ---------------------------------------------------------------------------------------------
# palettes (fully specified building specs; the plan picks among them)
# ---------------------------------------------------------------------------------------------
def _palettes():
    rng = np.random.default_rng(2077)
    towers = []
    sizes = [(36, 36), (40, 36), (44, 38), (48, 40), (40, 44), (36, 44), (44, 44), (32, 32)]
    floors = [34, 40, 46, 52, 58, 64, 70, 78, 86, 96]
    for k in range(30):
        w, d = sizes[k % len(sizes)]
        f = floors[(k * 3 + int(rng.integers(0, 3))) % len(floors)]
        r = rng.random()
        mat = GLASSES[(k * 5 + int(rng.integers(0, 8))) % 8]
        led = LEDS[int(rng.integers(len(LEDS)))]
        if r < 0.58:
            towers.append(('tower_setback', dict(w=w, d=d, floors=f, mat=mat, seed=int(rng.integers(1, 9999)), crown_style=str(rng.choice(['flat', 'flat', 'spire', 'dish', 'prongs'])),
                                                 steps=int(rng.integers(1, 4)), scale_top=float(round(rng.uniform(0.55, 0.78), 2)), pod=int(rng.integers(1, 3)),
                                                 fin=int(rng.random() < 0.28), signs=int(rng.integers(0, 2)), led=led, octo=bool(rng.random() < 0.25))))
        elif r < 0.86:
            towers.append(('tower_cyl', dict(r=float(rng.choice([13, 14, 15, 16])), floors=f, mat=mat, seed=int(rng.integers(1, 9999)), ring_every=int(rng.choice([6, 8, 10])), led=led,
                                              crown_style=str(rng.choice(['ring', 'spire', 'flat'])))))
        else:
            towers.append(('tower_twin', dict(w=24, d=28, floors=min(f, 70), gap=float(rng.choice([16, 20])), mat=mat, seed=int(rng.integers(1, 9999)), led=led)))
    mids = []
    for k in range(18):
        w, d = [(36, 36), (40, 36), (32, 40), (44, 32), (36, 28)][k % 5]
        mids.append(('midrise', dict(w=w, d=d, floors=int(rng.integers(8, 20)), mat=GLASSES[(k * 3 + 1) % 8], seed=int(rng.integers(1, 9999)), signs=int(rng.integers(0, 2)),
                                     led=LEDS[int(rng.integers(len(LEDS)))])))
    tens = []
    for k in range(14):
        w, d = [(26, 22), (26, 24), (24, 22), (26, 26)][k % 4]
        tens.append(('tenement', dict(w=w, d=d, floors=int(rng.integers(6, 14)), mat=['nc_wall_tenement_a', 'nc_wall_tenement_b', 'nc_wall_brutal'][k % 3], seed=int(rng.integers(1, 9999)),
                                      escapes=int(rng.integers(1, 3)))))
    slabs = []
    for k in range(8):
        w, d = [(64, 18), (56, 18), (48, 16), (60, 20)][k % 4]
        slabs.append(('slab', dict(w=w, d=d, floors=int(rng.integers(14, 28)), mat=['nc_glass_b', 'nc_glass_g', 'nc_wall_brutal', 'nc_glass_h'][k % 4], seed=int(rng.integers(1, 9999)))))
    megas = [('megablock', dict(w=w, d=d, floors=int(f), seed=int(rng.integers(1, 9999)))) for (w, d, f) in ((48, 48, 30), (48, 44, 36), (52, 48, 32), (40, 40, 34))]
    warehouses = [('warehouse', dict(w=w, d=d, h=float(h), seed=int(rng.integers(1, 9999)))) for (w, d, h) in ((56, 36, 11), (60, 40, 12), (52, 34, 10), (64, 38, 13), (48, 32, 10))]
    return dict(towers=towers, mids=mids, tens=tens, slabs=slabs, megas=megas, warehouses=warehouses)


PAL = None


def pal():
    global PAL
    if PAL is None:
        PAL = _palettes()
    return PAL


def _footprint(arch, a):
    if arch == 'tower_setback':
        return a['w'] + 6, a['d'] + 6
    if arch == 'tower_cyl':
        return 2 * (a['r'] + 3.5), 2 * (a['r'] + 3.5)
    if arch == 'tower_twin':
        return 2 * a['w'] + a['gap'] + 6, a['d'] + 6
    if arch == 'arcology':
        return a['w'] + 8, a['w'] + 8
    if arch == 'plaza_gate':
        return a['w'], 9.0
    if arch == 'family_house':
        return a['w'] + 1.0, a['d'] + 7.5  # includes the front porch and driveway apron
    if arch == 'estate_house':
        return a['w'] + 14.0, a['d'] + 22.0  # private garden walls, pool deck and long driveway
    if arch == 'motel':
        return a['w'], a['d'] + 4.0
    return a['w'], a['d']


def _sample_access_route(corners, radii, spacing=3.0, start_z=0.0, end_z=12.0):
    """Round a right-angle street route into tangent arcs and ease its grade from surface to deck height."""
    corners = np.asarray(corners, dtype=float)
    radii = np.asarray(radii, dtype=float)
    assert corners.ndim == 2 and corners.shape[1] == 2 and len(corners) >= 3 and len(radii) == len(corners)
    points = [corners[0].copy()]

    def line_to(a, b):
        length = float(np.linalg.norm(b - a))
        if length < 1e-6:
            return
        n = max(1, int(np.ceil(length / spacing)))
        points.extend(a + (b - a) * t for t in np.linspace(0.0, 1.0, n + 1)[1:])

    cursor = corners[0].copy()
    for i in range(1, len(corners) - 1):
        a, b, c = corners[i - 1], corners[i], corners[i + 1]
        vin, vout = b - a, c - b
        lin, lout = float(np.linalg.norm(vin)), float(np.linalg.norm(vout))
        vin, vout = vin / max(lin, 1e-9), vout / max(lout, 1e-9)
        cross = vin[0] * vout[1] - vin[1] * vout[0]
        if abs(cross) < 1e-6:
            line_to(cursor, b)
            cursor = b.copy()
            continue
        radius = min(float(radii[i]), 0.45 * lin, 0.45 * lout)
        tin, tout = b - vin * radius, b + vout * radius
        line_to(cursor, tin)
        left = np.array([-vin[1], vin[0]])
        center = tin + np.sign(cross) * left * radius
        v0, v1 = tin - center, tout - center
        a0, a1 = np.arctan2(v0[1], v0[0]), np.arctan2(v1[1], v1[0])
        if cross > 0:
            delta = (a1 - a0) % (2.0 * np.pi)
        else:
            delta = -((a0 - a1) % (2.0 * np.pi))
        n = max(2, int(np.ceil(radius * abs(delta) / spacing)))
        for angle in np.linspace(a0, a0 + delta, n + 1)[1:]:
            points.append(center + radius * np.array([np.cos(angle), np.sin(angle)]))
        cursor = tout
    line_to(cursor, corners[-1])
    xy = np.asarray(points, dtype=float)
    keep = np.r_[True, np.linalg.norm(np.diff(xy, axis=0), axis=1) > 1e-5]
    xy = xy[keep]
    ds = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    u = ds / max(ds[-1], 1e-9)
    z = float(start_z) + (float(end_z) - float(start_z)) * (3.0 * u * u - 2.0 * u * u * u)
    return np.column_stack([xy, z])


def pick(items, bw, bd, target, rng, key=lambda it: it[1].get('floors', 0), margin=2.0, avoid=()):
    """choose the palette entry that fits (bw, bd) and whose size key is closest to `target`"""
    fit = [it for it in items if _footprint(it[0], it[1])[0] <= bw - margin and _footprint(it[0], it[1])[1] <= bd - margin]
    if not fit:
        fit = sorted(items, key=lambda it: _footprint(it[0], it[1])[0] * _footprint(it[0], it[1])[1])[:3]
    fit = [it for it in fit if (it[0], it[1].get('seed')) not in avoid] or fit
    fit.sort(key=lambda it: abs(key(it) - target))
    return fit[int(rng.integers(0, min(3, len(fit))))]


# ---------------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------------
def build_plan():
    plan = Plan()
    X, Y, W, D = grid_lines()
    rng = np.random.default_rng(31337)
    P_ = pal()
    recent = []
    cx0 = X[HERO[0]] + W[HERO[0]] / 2
    cy0 = Y[HERO[1]] + D[HERO[1]] / 2
    sea_y1 = Y[0] - SEA_OFFSET
    sea_y0 = sea_y1 - SEA_DEPTH
    plan.extent = (X[0], sea_y0, X[-1], Y[-1])
    tg = tunnel_geom(X, Y)
    plan.tunnel = tg
    # the open cuts must lie inside the straight part of their street (between the crosswalks of the cross streets)
    for (hy0, hy1) in tg['holes']:
        jj = [j for j in range(12) if Y[j] < hy0 and hy1 < Y[j + 1]]
        assert len(jj) == 1, (hy0, hy1)
        j = jj[0]
        lo = Y[j] + CARR[YC[j]] / 2 + 4.0 + 1.0
        hi = Y[j + 1] - CARR[YC[j + 1]] / 2 - 4.0 - 1.0
        assert lo <= hy0 and hy1 <= hi, ('tunnel cut leaves its street', hy0, hy1, lo, hi)
    skyblocks = {}                 # (i, j) -> list of (x, y, half_w, half_d, top_z) for the sky bridge search
    for j in range(12):
        for i in range(12):
            ch = DIST[j][i]
            cls = (XC[i], XC[i + 1], YC[j], YC[j + 1])
            bw, bd = XB[i], YB[j]
            cxm = X[i] + W[i] / 2
            cym = Y[j] + D[j] / 2
            style = STYLE[ch]
            # block centre in world coordinates
            bcx = cxm + (SW[cls[0]] / 2 - SW[cls[1]] / 2) / 2
            bcy = cym + (SW[cls[2]] / 2 - SW[cls[3]] / 2) / 2
            alley = None
            if ch == 'M':
                alley = ('x', 0.0, 8.0)
            terrain = 4.0 if ch == 'H' else (6.0 if ch == 'Q' else 0.0)
            house_w = min(22.0 if ch == 'H' else 20.0, bw * (0.36 if ch == 'H' else 0.34)) if ch in ('S', 'H') else 0.0
            house_d = min(26.0 if ch == 'H' else 24.0, bd * (0.38 if ch == 'H' else 0.31)) if ch in ('S', 'H') else 0.0
            block_dx, block_dy = bcx - cxm, bcy - cym
            houseplots = tuple((block_dx + col * bw * 0.25, block_dy + row * bd * 0.25, house_w, house_d)
                               for row in (-1, 1) for col in (-1, 1)) if ch == 'H' else ()
            spec = dict(bw=bw, bd=bd, cls=cls, style=style, pad=PAD.get(ch, 'nc_sidewalk'), alley=alley,
                        river=(ch == '~'), parking=(ch in ('F', 'G')), terrain=terrain, houseplots=houseplots,
                        seed=1000 + 13 * bw + bd)
            if spec['river']:
                spec['seed'] = 3000 + bw
                gp = []
                if i in BRIDGE_LINES:                  # bridge on the west edge of this cell
                    gp.append((-W[i] / 2, -W[i] / 2 + SW[XC[i]] / 2))
                if (i + 1) in BRIDGE_LINES:            # ... and on the east edge
                    gp.append((W[i] / 2 - SW[XC[i + 1]] / 2, W[i] / 2))
                spec['gaps'] = tuple((float(a), float(b)) for a, b in gp)
            holes = []
            for (hy0, hy1) in tg['holes']:
                if Y[j] < hy0 and hy1 < Y[j + 1]:
                    if i + 1 == TUNNEL['line']:
                        holes.append(('e', round(hy0 - cym, 3), round(hy1 - cym, 3)))
                    if i == TUNNEL['line']:
                        holes.append(('w', round(hy0 - cym, 3), round(hy1 - cym, 3)))
            if holes:
                spec['holes'] = tuple(holes)
            gname = plan.model('g', 'cell', spec, hint='%s %dx%d' % (ch, bw, bd))
            plan.place(gname, cxm, cym, 0.0, 0.0, 'ground')
            if ch == '~':
                # river water: between the quay walls, even integer coordinates (GTA water grid)
                yw0 = cym + (-D[j] / 2 + CARR[cls[2]] / 2 + SIDE[cls[2]] + QUAY)
                yw1 = cym + (D[j] / 2 - CARR[cls[3]] / 2 - SIDE[cls[3]] - QUAY)
                plan.water.append((int(round(X[i] / 2.0)) * 2, int(np.floor(yw0 / 2) * 2), int(round(X[i + 1] / 2.0)) * 2, int(np.ceil(yw1 / 2) * 2), RIVER_Z))   # neighbours share the same even grid line
                continue
            dist_c = np.hypot(bcx - cx0, bcy - cy0)
            rr = np.random.default_rng(int(rng.integers(1, 10**9)))
            blds = []                # (arch, args, x, y, rz) relative to the block centre
            if ch in 'CKP':
                if ch == 'K':
                    blds.append(('arcology', dict(w=110, floors=70, seed=77), 0.0, 0.0, 0.0))
                elif ch == 'P':
                    blds.append(('plaza_gate', dict(w=56, h=70.0, seed=5), 0.0, 0.0, 90.0))
                else:
                    target = 96 - dist_c / 14.0 + float(rr.uniform(-8, 8))
                    arch, a = pick(P_['towers'], bw, bd, target, rr, avoid=recent[-6:])
                    recent.append((arch, a.get('seed')))
                    fw, fd = _footprint(arch, a)
                    rz = 0.0 if (fw <= bw - 2 and fd <= bd - 2) else 90.0
                    blds.append((arch, a, 0.0, 0.0, rz))
            elif ch == 'E':
                r = rr.random()
                if r < 0.34:
                    arch, a = pick(P_['towers'], bw, bd, 40 + float(rr.uniform(-6, 16)), rr, avoid=recent[-6:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, 0.0 if _footprint(arch, a)[0] <= bw - 2 and _footprint(arch, a)[1] <= bd - 2 else 90.0))
                elif r < 0.78:
                    arch, a = pick(P_['mids'], bw - 4, bd - 4, 14 + float(rr.uniform(-4, 5)), rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, float(rr.choice([0, 90]))))
                else:
                    g = ('garage', dict(w=float(rr.choice([48, 52, 56])), d=float(rr.choice([32, 36])), levels=int(rr.integers(5, 9)), seed=int(rr.integers(1, 99))))
                    blds.append((g[0], g[1], 0.0, 0.0, float(rr.choice([0, 90]))))
            elif ch == 'G':
                blds.append(('garage', dict(w=56.0, d=40.0, levels=8, seed=3), 0.0, -bd * 0.2, 0.0))
                arch, a = pick(P_['mids'], bw - 4, bd * 0.4, 12, rr)
                blds.append((arch, a, 0.0, bd * 0.25, 0.0))
            elif ch == 'W':
                if rr.random() < 0.6:
                    arch, a = pick(P_['mids'], bw - 4, bd - 4, 10 + float(rr.uniform(-2, 8)), rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, 0.0))
                else:
                    arch, a = pick(P_['slabs'], bw - 4, bd - 4, 18, rr)
                    blds.append((arch, a, 0.0, 0.0, 0.0 if bw >= bd else 90.0))
            elif ch == 'M':
                # Older main street: low-rise mixed-use block at the back, independent storefront at the corner.
                shop_w, shop_d = min(34.0, bw - 8.0), 17.0
                shop = ('roadside_shop', dict(w=shop_w, d=shop_d, seed=int(rr.integers(1, 9999)), kind='diner'))
                blds.append((shop[0], shop[1], 0.0, -bd * 0.25, 0.0))
                arch, a = pick(P_['tens'], bw - 8, min(bd * 0.36, 32.0), int(rr.integers(7, 13)), rr, avoid=recent[-4:])
                recent.append((arch, a.get('seed')))
                blds.append((arch, a, 0.0, bd * 0.25, float(rr.choice([0, 90, 180, 270]))))
            elif ch == 'R':
                # Apartment neighborhoods step down from the CBD: two distinct mid-rise / brick walk-up buildings per block.
                if rr.random() < 0.36 and bw >= 72:
                    arch, a = pick(P_['mids'], bw - 8, bd - 8, 12, rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, float(rr.choice([0, 90]))))
                else:
                    for col in (-1, 1):
                        arch, a = pick(P_['tens'], bw * 0.48, bd * 0.72, int(rr.integers(7, 13)), rr, avoid=recent[-4:])
                        recent.append((arch, a.get('seed')))
                        blds.append((arch, a, col * bw * 0.25, 0.0, float(rr.choice([0, 180]))))
            elif ch in ('S', 'H'):
                # Three gated garden parcels distinguish the bay-side estates from ordinary family-house blocks.
                estate_parcel = ch == 'S' and (i, j) in ((0, 1), (10, 1), (11, 1))
                if estate_parcel:
                    style_id = int(rr.integers(1, 4))
                    args = dict(w=30.0, d=32.0, seed=int(rr.integers(1, 9999)), style=style_id)
                    blds.append(('estate_house', args, 0.0, 0.0, 0.0))
                else:
                    # Four detached homes per standard parcel.  A north-suburb run faces a curving through-street.
                    curved_suburb = ch == 'S' and j == 10 and 6 <= i <= 9
                    row_scale = 0.32 if curved_suburb else 0.25
                    for row in (-1, 1):
                        for col in (-1, 1):
                            dx, dy = col * bw * 0.25, row * bd * row_scale
                            style_id = int(rr.integers(0, 4))
                            args = dict(w=house_w, d=house_d, seed=style_id, style=style_id, garage=True)
                            rz = (180.0 if row < 0 else 0.0) if curved_suburb else (0.0 if row < 0 else 180.0)
                            blds.append(('family_house', args, dx, dy, rz))
            elif ch == 'F':
                if (i, j) == (0, 3):
                    # Fixed neighborhood grocery with a real parking forecourt, distinct from a strip centre.
                    args = dict(w=float(bw - 4.0), d=float(bd - 8.0), seed=int(rr.integers(1, 9999)))
                    blds.append(('supermarket', args, 0.0, 0.0, 0.0))
                elif (i, j) == (11, 7):
                    # A glass-fronted auto showroom anchors the east-side commercial corridor.
                    args = dict(w=float(bw - 4.0), d=float(bd - 6.0), seed=int(rr.integers(1, 9999)))
                    blds.append(('dealership', args, 0.0, 0.0, 0.0))
                else:
                    r = 0.91 if (i, j) == (1, 3) else rr.random()  # keep one visible small roadside motel in the retail corridor
                    if r < 0.28:
                        args = dict(w=min(bw - 6.0, 54.0), d=min(bd - 8.0, 46.0), seed=int(rr.integers(1, 9999)))
                        blds.append(('gas_station', args, 0.0, 0.0, 0.0))
                    elif r < 0.54:
                        args = dict(w=min(bw - 6.0, 70.0), d=min(bd * 0.38, 28.0), seed=int(rr.integers(1, 9999)), shops=int(rr.integers(3, 6)))
                        blds.append(('strip_mall', args, 0.0, bd * 0.21, 0.0))
                    elif r < 0.78:
                        kind = 'diner' if rr.random() < 0.65 else 'fast_food'
                        args = dict(w=min(bw - 8.0, 42.0), d=min(bd * 0.40, 30.0), seed=int(rr.integers(1, 9999)), kind=kind)
                        blds.append(('roadside_shop', args, 0.0, bd * 0.17, 0.0))
                    else:
                        args = dict(w=min(bw - 8.0, 62.0), d=min(bd * 0.42, 32.0), seed=int(rr.integers(1, 9999)))
                        blds.append(('motel', args, 0.0, bd * 0.16, 0.0))
            elif ch == 'I':
                if (i, j) == (6, 1):
                    r = 0.90  # a fixed container yard anchors the working harbour
                elif (i, j) == (7, 2):
                    r = 0.65  # guarantee one factory among the port parcels
                elif (i, j) == (7, 1):
                    r = 0.30  # keep a warehouse in the industrial mix
                else:
                    r = rr.random()
                if r < 0.55:
                    arch, a = pick(P_['warehouses'], bw - 4, bd - 4, 11, rr, key=lambda it: it[1]['h'])
                    blds.append((arch, a, 0.0, -bd * 0.18 if bd > 70 else 0.0, 0.0))
                    if bd >= 84:
                        arch, a = pick(P_['warehouses'], bw - 4, bd * 0.4, 10, rr, key=lambda it: it[1]['h'])
                        blds.append((arch, a, 0.0, bd * 0.27, 0.0))
                elif r < 0.78:
                    blds.append(('factory', dict(w=float(bw - 4), d=float(min(bd - 4, 70)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
                else:
                    blds.append(('container_yard', dict(w=float(min(bw - 4, 80)), d=float(min(bd - 4, 60)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'T':
                blds.append(('tank_farm', dict(w=float(bw - 6), d=float(min(bd - 6, 70)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'Y':
                blds.append(('container_yard', dict(w=float(bw - 4), d=float(min(bd - 4, 64)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            for arch, a, dx, dy, rz in blds:
                bname = plan.model('b', arch, a, hint=arch)
                z0 = CURB + (house_pad_rise(bw, bd, dx, dy, a['w'], a['d'], terrain)
                             if arch == 'family_house' and terrain > 0.0 else 0.0)
                plan.place(bname, bcx + dx, bcy + dy, z0, rz, 'bld')
                fw, fd = _footprint(arch, a)
                if rz % 180 == 90:
                    fw, fd = fd, fw
                skyblocks.setdefault((i, j), []).append((bcx + dx, bcy + dy, fw / 2, fd / 2, arch, a))
    # ------------------------------------------------------------------ bay floor, waterfront promenade, and two scenic curved routes
    for i in range(12):
        L = float(X[i + 1] - X[i])
        sea = plan.model('g', 'sea_cell', dict(w=L, d=SEA_DEPTH), hint='bay floor')
        plan.place(sea, (X[i] + X[i + 1]) / 2, (sea_y0 + sea_y1) / 2, 0.0, 0.0, 'seabed')
        x0w = int(round(X[i] / 2.0)) * 2
        x1w = int(round(X[i + 1] / 2.0)) * 2
        plan.water.append((x0w, int(round(sea_y0 / 2.0)) * 2, x1w, int(round(sea_y1 / 2.0)) * 2, RIVER_Z))
        shore = plan.model('i', 'shorefront', dict(L=L), hint='bayfront promenade')
        plan.place(shore, (X[i] + X[i + 1]) / 2, sea_y1 + 25.0, 0.0, 0.0, 'waterfront')

    route_x0, route_x1 = X[1], X[11]
    route_span = route_x1 - route_x0
    def coast_profile(x):
        t = (x - route_x0) / route_span
        s = np.sin(np.pi * t)
        return Y[1] - 75.0 * s * s, -75.0 * np.pi / route_span * np.sin(2.0 * np.pi * t)
    def hill_profile(x):
        t = (x - route_x0) / route_span
        s, c = np.sin(np.pi * t), np.sin(2.0 * np.pi * t)
        y = Y[11] + 45.0 + 12.0 * c + 10.0 * s * s
        dy = 24.0 * np.pi / route_span * np.cos(2.0 * np.pi * t) + 10.0 * np.pi / route_span * c
        return y, dy
    for i in range(1, 11):
        xa, xb = X[i], X[i + 1]
        xm = (xa + xb) / 2.0
        ya, dya = coast_profile(xa)
        yb, dyb = coast_profile(xb)
        ym = (ya + yb) / 2.0
        args = dict(L=float(xb - xa), y0=float(ya - ym), y1=float(yb - ym), dy0=float(dya), dy1=float(dyb),
                    z0=0.0, z1=0.0, dz0=0.0, dz1=0.0, crest=0.0, hw=6.7, guardrail=False, supports=False, seed=500 + i)
        road = plan.model('i', 'curved_road', args, hint='coastal boulevard')
        plan.place(road, xm, ym, 0.0, 0.0, 'scenic')
        ya, dya = hill_profile(xa)
        yb, dyb = hill_profile(xb)
        ym = (ya + yb) / 2.0
        args = dict(L=float(xb - xa), y0=float(ya - ym), y1=float(yb - ym), dy0=float(dya), dy1=float(dyb),
                    z0=0.0, z1=0.0, dz0=0.0, dz1=0.0, crest=10.0, hw=6.2,
                    guardrail=True, supports=True, seed=600 + i)
        road = plan.model('i', 'curved_road', args, hint='ridge scenic drive')
        plan.place(road, xm, ym, 0.0, 0.0, 'scenic')

    # A connected, gently sinuous neighborhood street crosses four north-suburb parcels.
    # The houses on this run face the lane, so garages and front walks meet the road naturally.
    suburb_j = 10
    suburb_x0, suburb_x1 = X[6], X[10]
    suburb_span = suburb_x1 - suburb_x0
    suburb_y = (Y[suburb_j] + Y[suburb_j + 1]) / 2.0 + (SW[YC[suburb_j]] - SW[YC[suburb_j + 1]]) / 4.0
    def suburb_profile(x):
        t = (x - suburb_x0) / suburb_span
        return suburb_y + 2.4 * np.sin(2.0 * np.pi * t), 4.8 * np.pi / suburb_span * np.cos(2.0 * np.pi * t)
    for i in range(6, 10):
        xa, xb = X[i], X[i + 1]
        xm = (xa + xb) / 2.0
        ya, dya = suburb_profile(xa)
        yb, dyb = suburb_profile(xb)
        ym = (ya + yb) / 2.0
        args = dict(L=float(xb - xa), y0=float(ya - ym), y1=float(yb - ym), dy0=float(dya), dy1=float(dyb),
                    z0=0.0, z1=0.0, dz0=0.0, dz1=0.0, crest=CURB, hw=3.9,
                    road_mat='nc_road_local', shoulder_w=0.45, edge_lines=False, lamps=False,
                    guardrail=False, supports=False, seed=710 + i)
        road = plan.model('i', 'curved_road', args, hint='suburban connector')
        plan.place(road, xm, ym, 0.0, 0.0, 'residential_road')

    # ------------------------------------------------------------------ expressways
    ew, ns = EXPRESS_EW, EXPRESS_NS
    for i in range(12):
        L = int(round(W[i]))
        m = plan.model('i', 'expressway', dict(L=L, level=ew['level'], seed=i % 3, pier=True, soundwall=(i % 3 == 1)), hint='ew')
        plan.place(m, X[i] + W[i] / 2, Y[ew['line']], 0.0, 0.0, 'infra')
    for j in range(12):
        L = int(round(D[j]))
        if j == RIVER_J:
            m = plan.model('i', 'expressway', dict(L=L, level=ns['level'], seed=j % 3, pier=False, river=True, soundwall=False), hint='ns-river')
        else:
            m = plan.model('i', 'expressway', dict(L=L, level=ns['level'], seed=j % 3, pier=True, soundwall=(j % 3 == 1)), hint='ns')
        plan.place(m, X[ns['line']], Y[j] + D[j] / 2, 0.0, 90.0, 'infra')
    # Grade-separated ramps tie both directions of the lower freeway back into the surface street grid.
    # Each follows arterial/collector centerlines, with rounded turns and a smooth 12 m vertical profile.
    ramp_specs = [
        ('eastbound_surface_entry', [(X[2], Y[7] - 6.6), (X[3], Y[7] - 6.6), (X[3], Y[8] - 6.6), (X[3] + 26.0, Y[8] - 6.6)], [0, 12, 26, 0]),
        ('westbound_surface_entry', [(X[10], Y[9] + 6.6), (X[9], Y[9] + 6.6), (X[9], Y[8] + 6.6), (X[9] - 26.0, Y[8] + 6.6)], [0, 18, 26, 0]),
        ('eastbound_surface_exit', [(X[9], Y[8] - 6.6), (X[10] - 6.6, Y[8] - 6.6), (X[10] - 6.6, Y[7])], [0, 15, 0]),
        ('westbound_surface_exit', [(X[3] + 42.0, Y[8] + 6.6), (X[3], Y[8] + 6.6), (X[3], Y[9]), (X[2] + 6.6, Y[9])], [0, 24, 18, 0]),
    ]
    for k, (hint, corners, radii) in enumerate(ramp_specs):
        is_exit = hint.endswith('_exit')
        path = _sample_access_route(corners, radii, spacing=3.0,
                                    start_z=ew['level'] if is_exit else 0.0,
                                    end_z=0.0 if is_exit else ew['level'])
        origin = (path[:, :2].min(0) + path[:, :2].max(0)) / 2.0
        path[:, :2] -= origin
        args = dict(points=tuple(tuple(float(round(v, 5)) for v in q) for q in path), hw=4.2, seed=810 + k)
        ramp = plan.model('i', 'access_ramp', args, hint=hint)
        plan.place(ramp, origin[0], origin[1], 0.0, 0.0, 'surface_access_ramp')
    # ------------------------------------------------------------------ four-ramp, two-level interchange where the expressways cross
    junction = plan.model('i', 'interchange', dict(low=ew['level'], high=ns['level'], radius=86.0, seed=7331), hint='elevated interchange')
    plan.place(junction, X[ns['line']], Y[ew['line']], 0.0, 0.0, 'interchange')

    # ------------------------------------------------------------------ bridges over the river
    j = RIVER_J
    span = int(round(D[j]))
    water_span = int(round(D[j] - (CARR[YC[j]] / 2 + SIDE[YC[j]] + QUAY) - (CARR[YC[j + 1]] / 2 + SIDE[YC[j + 1]] + QUAY)))
    for line, cls in BRIDGE_LINES.items():
        if line == HERO_BRIDGE_LINE:
            m = plan.model('i', 'bridge_cable', dict(span=span, water=water_span, cls='A', seed=3), hint='hero bridge')
        else:
            m = plan.model('i', 'bridge_girder', dict(span=span, water=water_span, cls=cls, seed=line), hint='bridge %s' % cls)
        plan.place(m, X[line], (Y[j] + Y[j + 1]) / 2, 0.0, 0.0, 'bridge')
    # ------------------------------------------------------------------ the river road tunnel
    for pt_ in tg['parts']:
        m = plan.model('i', pt_['builder'], pt_['args'], hint='tunnel')
        plan.place(m, tg['x'], pt_['y'], pt_['z'], pt_['rz'], 'tunnel')
    # ------------------------------------------------------------------ sky bridges between neighbouring core / entertainment towers
    sky = []
    for (i, j), lst in skyblocks.items():
        if (i + 1, j) in skyblocks and DIST[j][i] in 'CE' and DIST[j][i + 1] in 'CE':
            for (x0, y0, hw0, hd0, a0, s0) in lst:
                for (x1, y1, hw1, hd1, a1, s1) in skyblocks[(i + 1, j)]:
                    f0, f1 = s0.get('floors', 0), s1.get('floors', 0)
                    if a0.startswith('tower') and a1.startswith('tower') and min(f0, f1) >= 46 and abs(y0 - y1) < 6:
                        gap = (x1 - hw1) - (x0 + hw0)
                        if 8 < gap < 64:
                            sky.append(((x0 + hw0 - 1.0 + x1 - hw1 + 1.0) / 2, (y0 + y1) / 2, gap + 2.0, min(f0, f1)))
    sky.sort(key=lambda s: -s[3])
    used = 0
    for (sx, sy, L, f) in sky[:5]:
        z = 40.0 + 3.8 * int(f * 0.35)
        m = plan.model('i', 'skybridge', dict(length=int(round(L)), seed=used), hint='skybridge')
        plan.place(m, sx, sy, z, 0.0, 'sky')
        used += 1
    # ------------------------------------------------------------------ distant skyline strips (no collision)
    x0, y0, x1, y1 = plan.extent
    lw = x1 - x0 + 500
    lh = y1 - y0 + 500
    sk = [
        ('N', 0, (x0 + x1) / 2, y1 + 150.0, 0.0, lw, 11), ('N', 1, (x0 + x1) / 2, y1 + 330.0, 0.0, lw, 12),
        ('S', 2, (x0 + x1) / 2, y0 - 150.0, 180.0, lw, 13), ('S', 3, (x0 + x1) / 2, y0 - 330.0, 180.0, lw, 14),
    ]
    ry0 = Y[RIVER_J]
    ry1 = Y[RIVER_J + 1]
    for (side, k, cx, cy, rz, L, sd) in sk:
        m = plan.model('s', 'skyline_strip', dict(L=int(L), seed=sd, rows=2), hint='skyline')
        plan.place(m, cx, cy, 0.0, rz, 'skyline')
    # east / west strips, leaving the river corridor open
    for (rz, xs, tagn) in ((-90.0, x1 + 150.0, 'E'), (90.0, x0 - 150.0, 'W')):
        for (a, b, sd) in ((y0 - 100, ry0 - 20, 21), (ry1 + 20, y1 + 100, 22)):
            m = plan.model('s', 'skyline_strip', dict(L=int(b - a), seed=sd + (0 if tagn == 'E' else 5), rows=2), hint='skyline')
            plan.place(m, xs, (a + b) / 2, 0.0, rz, 'skyline')
    # ------------------------------------------------------------------ named points: spawn, tour, viewpoints
    coast_x = (route_x0 + route_x1) / 2.0
    coast_y, _ = coast_profile(coast_x)
    hill_x = coast_x
    hill_y, _ = hill_profile(hill_x)
    plan.points = dict(
        spawn=(cx0 - 0.0, cy0 - D[HERO[1]] / 2 + 12.0, CURB + 1.0),
        plaza=(cx0 - 94.0, cy0, CURB + 1.0),
        avenue=(X[4], cy0 - 200.0, 1.0),
        market=(X[1] + 4.0, Y[8] + 40.0, 1.0),
        quay=(cx0, Y[RIVER_J] + CARR[YC[RIVER_J]] / 2 + SIDE[YC[RIVER_J]] + 4.0, CURB + 1.0),
        bridge=(X[HERO_BRIDGE_LINE], (Y[RIVER_J] + Y[RIVER_J + 1]) / 2, CURB + 1.0),
        expressway=(X[3], Y[ew['line']], ew['level'] + 1.0),
        interchange=(X[ns['line']], Y[ew['line']], ns['level'] + 1.0),
        coastal_drive=(coast_x, coast_y, 1.0),
        ridge_drive=(hill_x, hill_y, 10.0),
        waterfront=(coast_x, sea_y1 + 25.0, CURB + 1.0),
        industrial=(X[8] + 60, Y[2] + 80, 1.0),
        tunnel_in=(tg['x'], tg['y_in'] - 14.0, 1.0),
        tunnel_out=(tg['x'], tg['y_out'] + 14.0, 1.0),
        tunnel_mid=(tg['x'], (tg['y_a'] + tg['y_b']) / 2, tg['z_floor'] + 1.0),
    )
    yr = (Y[RIVER_J] + Y[RIVER_J + 1]) / 2
    hb = X[HERO_BRIDGE_LINE]
    plan.tour = [      # eye x, y, z, look-at x, y, z, seconds to the next key
        (X[10], Y[2] - 60.0, 300.0, cx0, cy0, 90.0, 14.0),                      # high aerial over the harbour side, the core in the distance
        (hb + 120.0, yr - 230.0, 70.0, hb, yr, 45.0, 12.0),                      # over the river towards the cable-stayed bridge
        (hb, yr - 70.0, 7.0, hb, yr + 330.0, 40.0, 14.0),                        # along the bridge deck, the core ahead
        (X[4], Y[7] + 20.0, 3.5, X[4], Y[10], 60.0, 12.0),                       # avenue canyon between the towers
        (cx0 - 140.0, cy0 - 120.0, 3.0, cx0, cy0, 150.0, 12.0),                  # plaza, looking up at the arcology
        (cx0 + 70.0, cy0 - 30.0, 40.0, cx0, cy0, 140.0, 10.0),                   # climb along the arcology
        (X[2], Y[ew['line']], ew['level'] + 3.0, X[9], Y[ew['line']], ew['level'] + 9.0, 14.0),   # along the lower expressway deck
        (X[1] + 3.0, Y[8] + 6.0, 3.0, X[1] + 3.0, Y[8] + 220.0, 14.0, 14.0),     # older American main street
        (X[9] + 50.0, Y[2] + 30.0, 11.0, X[9] + 50.0, Y[3] + 140.0, 46.0, 12.0), # working port and warehouses
    ] + tunnel_tour(tg) + [
        (coast_x - 140.0, coast_y - 45.0, 36.0, coast_x, coast_y, 0.5, 14.0),     # bayfront boulevard and ocean edge
        (hill_x - 110.0, hill_y - 52.0, 42.0, hill_x, hill_y, 7.0, 14.0),          # ridge drive through parkland
        (X[ns['line']] + 115.0, Y[ew['line']] - 95.0, 44.0, X[ns['line']], Y[ew['line']], 17.0, 14.0),  # multilevel interchange
        (X[3], Y[4] - 100.0, 140.0, cx0, cy0, 40.0, 10.0),                         # final skyline view
    ]
    plan.grid = dict(X=X, Y=Y, W=W, D=D)
    plan.hero = (cx0, cy0)
    return plan
