# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# infra.py - scenic roads, waterfront promenade, elevated interchange / expressways, river bridges, sky bridges and skyline strips.
# Every function returns (Mesh, Col, meta).  Bridges / expressways are built along +x, centred on the origin.
# (No vehicles anywhere: only the road structures themselves.)
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, unit
from . import parts as P
from . import bldkit as K
from .bldkit import rect
from .ground import CURB, SW, CARR, SIDE, ROAD, RIVER_Z, BED_Z


def _path_tangents(path):
    p = np.asarray(path, np.float64)
    d = p[1:, :2] - p[:-1, :2]
    t = np.zeros((len(p), 2), np.float64)
    t[:-1] += unit(d)
    t[1:] += unit(d)
    return unit(t)


def _offset_path(path, distance):
    p = np.asarray(path, np.float64).copy()
    t = _path_tangents(p)
    left = np.stack([-t[:, 1], t[:, 0]], axis=1)
    p[:, :2] += left * float(distance)
    return p


def _collision_ribbon(C, path, half_width, zoff=0.04):
    p = np.asarray(path, np.float64)
    t = _path_tangents(p)
    left = np.stack([-t[:, 1], t[:, 0]], axis=1)
    a = p.copy()
    b = p.copy()
    a[:, :2] += left * half_width
    b[:, :2] -= left * half_width
    a[:, 2] += zoff
    b[:, 2] += zoff
    verts = np.concatenate([b, a], axis=0)
    faces = []
    n = len(p)
    for k in range(n - 1):
        faces.extend(((k, k + 1, n + k + 1), (k, n + k + 1, n + k)))
    C.mesh(verts, np.asarray(faces, np.int64), 0)


def curved_road(L, y0, y1, dy0=0.0, dy1=0.0, z0=0.0, z1=0.0, dz0=0.0, dz1=0.0,
                crest=0.0, hw=6.7, road_mat='nc_road_str', shoulder_w=0.95,
                edge_lines=True, lamps=True, guardrail=False, supports=False, seed=0):
    """Smooth Hermite-spline local road segment with collision, shoulders, markings and optional guardrails.

    x runs from -L/2 to +L/2.  Endpoint offsets and slopes are supplied in the local frame so neighboring
    segments share position and tangent exactly.  `crest` adds a smooth, zero-slope hill between the ends.
    """
    L = float(L)
    assert L > 4.0
    n = max(20, int(L // 3.0) + 1)
    t = np.linspace(0.0, 1.0, n)
    h00, h10 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t
    h01, h11 = -2*t**3 + 3*t**2, t**3 - t**2
    yy = h00*y0 + h10*L*dy0 + h01*y1 + h11*L*dy1
    zz = h00*z0 + h10*L*dz0 + h01*z1 + h11*L*dz1 + float(crest) * (16.0 * (t * (1.0 - t))**2)
    path = np.stack([-L / 2 + t * L, yy, zz], axis=1)
    M, C = Mesh(), Col()
    # Textured road ribbon with optional paved shoulders and edge paint.
    M.ribbon(path, hw, road_mat, tile_v=8.0, u=(0.0, 1.0), zoff=0.04)
    _collision_ribbon(C, path, hw, 0.04)
    for side in (-1, 1):
        if shoulder_w > 0.0:
            shoulder = _offset_path(path, side * (hw + shoulder_w))
            M.ribbon(shoulder, shoulder_w, 'nc_asphalt', tile_v=8.0, u=(0.0, 1.0), zoff=0.02)
        if edge_lines:
            edge = _offset_path(path, side * (hw - 0.20))
            M.ribbon(edge, 0.065, 'nc_light_white', tile_v=2.0, zoff=0.07)
    if guardrail:
        for side in (-1, 1):
            rail = _offset_path(path, side * (hw + 1.85))
            rail[:, 2] += 1.0
            M.tube(rail, 0.065, 6, 'nc_metal_light', tile=(3.0, 1.0), caps=False, smooth=True)
            for k in range(0, len(rail), 5):
                p = rail[k]
                M.tube(np.array([[p[0], p[1], p[2] - 1.0], [p[0], p[1], p[2]]]), 0.045, 6, 'nc_metal_dark', tile=(1, 1), caps=False)
                C.box((p[0] - 0.07, p[1] - 0.07, p[2] - 1.0), (p[0] + 0.07, p[1] + 0.07, p[2]))
    # Street lamps at a realistic arterial spacing; quiet residential lanes stay uncluttered.
    if lamps:
        for k in range(max(1, int(L // 42.0))):
            i = min(len(path) - 1, int((k + 0.5) * len(path) / max(1, int(L // 42.0))))
            p = path[i]
            M.merge(P.street_lamp(8.5, 2.6, False, False), (p[0], p[1] + hw + 2.2, p[2] + 0.04), rz=180.0)
    if supports:
        tangents = _path_tangents(path)
        step = max(5, len(path) // 8)
        for k in range(step, len(path) - step, step):
            p = path[k]
            if p[2] < 3.2:
                continue
            lateral = np.array([-tangents[k, 1], tangents[k, 0]])
            for side in (-1, 1):
                q = p[:2] + lateral * side * (hw + 2.2)
                top = p[2] - 1.8
                M.box((q[0] - 0.45, q[1] - 0.45, 0.0), (q[0] + 0.45, q[1] + 0.45, top), 'nc_concrete', tile=(2, 5))
                C.box((q[0] - 0.45, q[1] - 0.45, 0.0), (q[0] + 0.45, q[1] + 0.45, top))
    half_extent = max(hw + 2.0 * max(0.0, shoulder_w), hw + (1.92 if guardrail else 0.0))
    return M, C, dict(kind='curved_road', w=L, d=float(2 * half_extent), h=float(max(zz) + 3.0), dist=650.0, seed=int(seed))


def shorefront(L):
    """Segment of bayfront promenade and seawall, built above the engine-water coastline."""
    L = float(L)
    M, C = Mesh(), Col()
    coast_y = -25.0                    # with the model origin on land, the wall aligns to the sea-cell edge
    M.hquad(-L / 2, 0.0, L / 2, 8.0, CURB, 'nc_plaza', tile=(4.8, 4.8))
    # Seaward quay face and a restrained metal handrail.
    M.wall(np.array([-L / 2, coast_y]), np.array([L / 2, coast_y]), BED_Z, 0.0, 'nc_concrete_dark', tile=(4.0, 4.0))
    M.box((-L / 2, coast_y - 0.12, 0.0), (L / 2, coast_y + 0.12, 0.12), 'nc_concrete', tile=(3, 1))
    M.box((-L / 2, 1.0, CURB + 1.0), (L / 2, 1.12, CURB + 1.08), 'nc_metal_light', tile=(3, 1))
    for x in np.arange(-L / 2 + 2.0, L / 2, 4.0):
        M.box((x - 0.04, 1.0, CURB), (x + 0.04, 1.12, CURB + 1.0), 'nc_metal_dark', tile=(1, 2))
    C.box((-L / 2, 0.0, 0.0), (L / 2, 8.0, CURB))
    C.box((-L / 2, coast_y - 0.8, BED_Z), (L / 2, coast_y + 0.8, 0.12))
    n = max(1, int(L // 38.0))
    for k in range(n):
        x = -L / 2 + (k + 0.5) * L / n
        if k % 2 == 0:
            M.merge(P.street_tree(9.0, 0), (x, 5.2, CURB), rz=180.0)
            C.box((x - 0.28, 4.92, CURB), (x + 0.28, 5.48, CURB + 4.5))
        else:
            M.merge(P.bench(), (x, 5.0, CURB), rz=180.0)
        M.merge(P.street_lamp(8.5, 2.4, False, False), (x, 2.4, CURB), rz=180.0)
    return M, C, dict(kind='shorefront', w=L, d=34.0, h=10.0, dist=480.0)


def interchange(low=12.0, high=22.0, radius=86.0, seed=0):
    """Four swept, one-lane connectors tying a lower freeway to its elevated crossing deck."""
    M, C = Mesh(), Col()
    r = float(radius)
    n = 42
    for sx in (-1, 1):
        for sy in (-1, 1):
            p0 = np.array([sx * r, sy * 6.4, low + 0.05])
            p1 = np.array([sx * (r * 0.72), sy * 6.4, low + 1.0])
            p2 = np.array([sx * 6.4, sy * (r * 0.72), high - 1.0])
            p3 = np.array([sx * 6.4, sy * r, high + 0.05])
            t = np.linspace(0.0, 1.0, n)
            path = ((1-t)**3)[:, None] * p0 + (3*(1-t)**2*t)[:, None] * p1 + (3*(1-t)*t**2)[:, None] * p2 + (t**3)[:, None] * p3
            hw = 5.25
            M.ribbon(path, hw, 'nc_asphalt', tile_v=7.0, u=(0.0, 1.0), zoff=0.04)
            _collision_ribbon(C, path, hw, 0.04)
            for side in (-1, 1):
                edge = _offset_path(path, side * (hw - 0.22))
                M.ribbon(edge, 0.065, 'nc_light_white', tile_v=2.0, zoff=0.07)
            # Concrete box-girder soffit, outer walls, steel rails and a narrow shoulder stripe.
            M.ribbon(path, hw + 0.25, 'nc_deck_under', tile_v=5.0, u=(0.0, 1.0), zoff=-1.7, up=False)
            for side in (-1, 1):
                edge = _offset_path(path, side * (hw + 0.28))
                lower, upper = edge.copy(), edge.copy()
                lower[:, 2] -= 1.65
                upper[:, 2] += 1.15
                quads = np.stack([lower[:-1], lower[1:], upper[1:], upper[:-1]], axis=1)
                M.quads(quads, 'nc_concrete')
                rail = _offset_path(path, side * (hw + 0.42))
                rail[:, 2] += 1.25
                M.tube(rail, 0.09, 6, 'nc_metal_light', tile=(3, 1), caps=False)
                for k in range(0, n, 6):
                    p = rail[k]
                    M.tube(np.array([[p[0], p[1], p[2] - 1.0], [p[0], p[1], p[2]]]), 0.055, 6, 'nc_metal_dark', tile=(1, 1), caps=False)
                    C.box((p[0] - 0.08, p[1] - 0.08, p[2] - 1.0), (p[0] + 0.08, p[1] + 0.08, p[2]))
            # High-clearance bents at regular intervals, kept outside the travelled lanes.
            for k in (10, 21, 32):
                p = path[k]
                tangent = _path_tangents(path)[k]
                lateral = np.array([-tangent[1], tangent[0]])
                for side in (-1, 1):
                    q = p.copy()
                    q[:2] += lateral * side * 7.0
                    h = max(1.0, p[2] - 2.1)
                    M.box((q[0] - 0.75, q[1] - 0.75, 0.0), (q[0] + 0.75, q[1] + 0.75, h), 'nc_pillar', tile=(2, 6))
                    C.box((q[0] - 0.75, q[1] - 0.75, 0.0), (q[0] + 0.75, q[1] + 0.75, h))
            # Sparse reflector paint keeps the ramp readable at night without neon edge lighting.
            for k in (4, 12, 20, 28, 36):
                p = path[k]
                M.box((p[0] - 0.11, p[1] - 0.11, p[2] + 0.045), (p[0] + 0.11, p[1] + 0.11, p[2] + 0.065), 'nc_light_amber', tile=(1, 1))
    return M, C, dict(kind='interchange', w=2*r+18.0, d=2*r+18.0, h=float(high + 4.0), dist=720.0, ramps=4, seed=int(seed))


def access_ramp(points, hw=4.2, seed=0):
    """One-way surface-to-freeway connector: sampled smooth plan curve, graded pavement, girder, rails and supports."""
    path = np.asarray(points, np.float64)
    assert path.ndim == 2 and path.shape[1] == 3 and len(path) >= 8
    hw = float(hw)
    M, C = Mesh(), Col()
    M.ribbon(path, hw, 'nc_asphalt', tile_v=7.0, u=(0.0, 1.0), zoff=0.04)
    _collision_ribbon(C, path, hw, 0.04)
    for side in (-1, 1):
        edge = _offset_path(path, side * (hw - 0.18))
        M.ribbon(edge, 0.07, 'nc_light_white', tile_v=2.0, zoff=0.07)
        soffit = _offset_path(path, side * (hw + 0.25))
        lower, upper = soffit.copy(), soffit.copy()
        lower[:, 2] -= 1.55
        upper[:, 2] += 1.05
        M.quads(np.stack([lower[:-1], lower[1:], upper[1:], upper[:-1]], axis=1), 'nc_concrete_dark')
        rail = soffit.copy()
        rail[:, 2] += 1.20
        M.tube(rail, 0.075, 6, 'nc_metal_light', tile=(3, 1), caps=False)
        for k in range(0, len(path), 6):
            p = soffit[k]
            M.box((p[0] - 0.055, p[1] - 0.055, p[2] - 0.05), (p[0] + 0.055, p[1] + 0.055, p[2] + 1.18), 'nc_metal_dark', tile=(1, 2))
            C.box((p[0] - 0.06, p[1] - 0.06, p[2] - 0.05), (p[0] + 0.06, p[1] + 0.06, p[2] + 1.20))
    M.ribbon(path, hw + 0.38, 'nc_deck_under', tile_v=6.0, u=(0.0, 1.0), zoff=-1.55, up=False)
    # Bents at 32 m intervals, placed beside the one-way pavement and clear of its collision surface.
    tangent = _path_tangents(path)
    left = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    dist = np.concatenate([[0.0], np.cumsum(np.linalg.norm(path[1:, :2] - path[:-1, :2], axis=1))])
    for target in np.arange(30.0, dist[-1] - 14.0, 32.0):
        k = int(np.clip(np.searchsorted(dist, target), 1, len(path) - 2))
        p = path[k]
        if p[2] < 3.8:
            continue
        for side in (-1, 1):
            q = p[:2] + left[k] * side * (hw + 2.4)
            top = p[2] - 1.65
            M.box((q[0] - 0.42, q[1] - 0.42, 0.0), (q[0] + 0.42, q[1] + 0.42, top), 'nc_pillar', tile=(2, 6))
            C.box((q[0] - 0.42, q[1] - 0.42, 0.0), (q[0] + 0.42, q[1] + 0.42, top))
    lo, hi = path[:, :2].min(0) - hw - 3.0, path[:, :2].max(0) + hw + 3.0
    return M, C, dict(kind='access_ramp', w=float(hi[0] - lo[0]), d=float(hi[1] - lo[1]),
                       h=float(path[:, 2].max() + 3.0), dist=600.0, seed=int(seed))


def _cap_beam_pier(M, C, x, level, thick, ytop_w=18.0, base=0.0):
    h = level - thick
    M.box((x - 1.2, -1.2, base), (x + 1.2, 1.2, h - 1.8), 'nc_pillar', tile=(2.4, 6.0))
    M.box((x - 1.5, -ytop_w / 2, h - 1.8), (x + 1.5, ytop_w / 2, h), 'nc_concrete_dark', tile=(3, 3))
    M.box((x - 1.25, -1.25, base + 0.2), (x + 1.25, 1.25, base + 0.32), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((x, 0, base + 1.0), P.CYA, 0.7, 14.0)
    C.box((x - 1.2, -1.2, base), (x + 1.2, 1.2, h - 1.8))
    C.box((x - 1.5, -ytop_w / 2, h - 1.8), (x + 1.5, ytop_w / 2, h))


def _freeway_gantry(M, C, x, level):
    """American-style green overhead direction signs, mounted outside the freeway barriers."""
    z0 = float(level)
    for sy in (-1, 1):
        y = sy * 12.9
        M.box((x - 0.30, y - 0.30, z0 + 0.95), (x + 0.30, y + 0.30, z0 + 10.0), 'nc_metal_light', tile=(1, 5))
        C.box((x - 0.30, y - 0.30, z0 + 0.95), (x + 0.30, y + 0.30, z0 + 10.0))
    M.box((x - 0.38, -15.1, z0 + 10.0), (x + 0.38, 15.1, z0 + 10.45), 'nc_metal_dark', tile=(4, 1))
    for sy in (-1, 1):
        cy = sy * 6.6
        M.box((x - 0.14, cy - 4.5, z0 + 7.1), (x + 0.14, cy + 4.5, z0 + 9.9),
              'nc_hwy_sign', tile=(9.0, 2.8), skip=('+y', '-y', '+z', '-z'))
        M.box((x - 0.18, cy - 4.55, z0 + 6.95), (x + 0.18, cy + 4.55, z0 + 7.1), 'nc_metal_light', tile=(4, 1))
    return


def expressway(L, level, seed=0, pier=True, river=False, soundwall=False):
    """double carriageway elevated expressway segment, length L along x, deck top at z = level"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    hw = 13.2
    th = 2.2
    for sy in (1, -1):
        M.ribbon([(-L / 2, sy * 6.6, level), (L / 2, sy * 6.6, level)], 6.0, 'nc_road_hwy', tile_v=8.0, u=(0.0, 1.0))
    # median + outer barriers (jersey profile as stepped boxes)
    for (ya, yb) in ((-0.6, 0.6),):
        M.box((-L / 2, ya, level), (L / 2, yb, level + 1.0), 'nc_concrete', tile=(4, 2))
    for sy in (1, -1):
        y0, y1 = (12.6, 13.2) if sy > 0 else (-13.2, -12.6)
        M.box((-L / 2, y0, level), (L / 2, y1, level + 0.95), 'nc_concrete', tile=(4, 2))
        ya, yb = (12.7, 13.1) if sy > 0 else (-13.1, -12.7)
        M.box((-L / 2, ya, level + 0.95), (L / 2, yb, level + 1.05), 'nc_strip_white', tile=(1, 1), emis=0.9)
    if soundwall:
        # Selective acoustic screening: one elevated side is walled, the opposite skyline remains open.
        sy = 1 if int(seed) % 2 else -1
        wy0, wy1 = sorted((sy * 13.12, sy * 13.58))
        M.box((-L / 2, wy0, level + 0.92), (L / 2, wy1, level + 1.55), 'nc_concrete_dark', tile=(4, 1))
        M.box((-L / 2, wy0, level + 1.55), (L / 2, wy1, level + 4.25), 'nc_concrete', tile=(4, 3))
        M.box((-L / 2, wy0 - sy * 0.08, level + 4.25), (L / 2, wy1 + sy * 0.08, level + 4.42), 'nc_metal_dark', tile=(4, 1))
        for px in np.arange(-L / 2 + 3.0, L / 2 - 1.0, 6.0):
            M.box((px - 0.13, wy0, level + 0.95), (px + 0.13, wy1, level + 4.42), 'nc_metal_dark', tile=(1, 3))
            C.box((px - 0.14, wy0 - 0.04, level + 0.95), (px + 0.14, wy1 + 0.04, level + 4.45))
        C.box((-L / 2, wy0, level + 1.0), (L / 2, wy1, level + 4.3))
    # box girder: underside + sides + LED line
    M.hquad(-L / 2, -hw, L / 2, hw, level - th, 'nc_deck_under', tile=(4, 4), up=False)
    M.wall_strip([(L / 2, hw), (-L / 2, hw)], level - th, level, 'nc_concrete', tile=(4, 2))
    M.wall_strip([(-L / 2, -hw), (L / 2, -hw)], level - th, level, 'nc_concrete', tile=(4, 2))
    for sy in (1, -1):
        y = sy * (hw + 0.02)
        M.box((-L / 2, min(y, y + sy * 0.12), level - th + 0.15), (L / 2, max(y, y + sy * 0.12), level - th + 0.35), 'nc_strip_cyan', tile=(1, 1), emis=1.0, skip=('-z',))
    # deck end faces
    # lamps on the median every ~24 m, twin arm
    nl = max(1, int(L // 24))
    for k in range(nl):
        x = -L / 2 + (k + 0.5) * L / nl
        M.merge(P.street_lamp(10.0, 4.2, False, True), (x, 0, level + 1.0), rz=90.0)
    # About every third segment carries an overhead destination/exit sign assembly.
    if int(seed) % 3 == 0:
        _freeway_gantry(M, C, 0.0, level)
    if river:
        for fx in (-L / 6, L / 6):
            _cap_beam_pier(M, C, fx, level, th, base=BED_Z)
    elif pier:
        _cap_beam_pier(M, C, 0.0, level, th)
    C.box((-L / 2, -hw, level - th), (L / 2, hw, level))
    C.box((-L / 2, -0.6, level), (L / 2, 0.6, level + 1.0))
    C.box((-L / 2, 12.6, level), (L / 2, 13.2, level + 0.95))
    C.box((-L / 2, -13.2, level), (L / 2, -12.6, level + 0.95))
    return M, C, dict(kind='expressway', w=float(L), d=(27.2 if soundwall else 26.4), h=float(level + 12), dist=560.0, soundwall=bool(soundwall))


def bridge_girder(span, cls, seed=0, water=None):
    """river bridge of road class `cls`, deck along +y over `span` (bank street centre to bank street centre), top at z = 0.
    The structure (parapets, lamps, girder, piers) exists over the water section only (`water` m, centred)."""
    M, C = Mesh(), Col()
    water = float(span if water is None else water)
    wd = SW[cls]
    car, side = CARR[cls], SIDE[cls]
    th = 1.8
    hw = wd / 2
    jn = CARR['S'] / 2                           # half carriageway of the bank street: this band is the intersection (plain asphalt, no raised pavement)
    ya, yb = -span / 2 + jn, span / 2 - jn
    if cls in ROAD:
        M.ribbon([(0, ya, 0.0), (0, yb, 0.0)], car / 2, ROAD[cls], tile_v=8.0, u=(0.0, 1.0))
    else:
        M.hquad(-car / 2, ya, car / 2, yb, 0.0, 'nc_alley', tile=(6, 6))
    M.hquad(-hw, -span / 2, hw, ya, 0.0, 'nc_asphalt', tile=(12.0, 12.0))
    M.hquad(-hw, yb, hw, span / 2, 0.0, 'nc_asphalt', tile=(12.0, 12.0))
    for sx in (1, -1):
        x0, x1 = (car / 2, hw) if sx > 0 else (-hw, -car / 2)
        M.hquad(x0, ya, x1, yb, CURB, 'nc_sidewalk', tile=(3.6, 3.6))
        xc = car / 2 * sx
        a, b = ((xc, yb), (xc, ya)) if sx > 0 else ((xc, ya), (xc, yb))
        M.wall(np.array(a), np.array(b), 0.0, CURB, 'nc_curb', tile=(1.6, 1.6))
        px = hw * sx
        M.box((min(px, px - sx * 0.4), -water / 2, CURB), (max(px, px - sx * 0.4), water / 2, CURB + 1.1), 'nc_concrete', tile=(4, 2))
        M.box((min(px - sx * 0.05, px - sx * 0.35), -water / 2, CURB + 1.1), (max(px - sx * 0.05, px - sx * 0.35), water / 2, CURB + 1.18), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
        n = max(2, int(water // 26))
        for k in range(n):
            y = -water / 2 + (k + 0.5) * water / n
            M.merge(P.street_lamp(9.0, 2.6, False, False), (px - sx * 0.7, y, CURB), rz=(-90.0 if sx > 0 else 90.0) + 180.0)
    # girder: underside + outer faces (over the water only)
    M.hquad(-hw, -water / 2, hw, water / 2, -th, 'nc_deck_under', tile=(4, 4), up=False)
    M.wall_strip([(hw, -water / 2), (hw, water / 2)], -th, 0.0, 'nc_concrete_dark', tile=(4, 2))
    M.wall_strip([(-hw, water / 2), (-hw, -water / 2)], -th, 0.0, 'nc_concrete_dark', tile=(4, 2))
    for fy in (-1 / 6, 1 / 6):
        y = water * fy
        M.box((-hw * 0.7, y - 1.6, BED_Z), (hw * 0.7, y + 1.6, -th), 'nc_concrete_dark', tile=(3, 3))
        M.box((-hw * 0.7 - 0.02, y - 1.62, -th - 1.0), (hw * 0.7 + 0.02, y + 1.62, -th - 0.9), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
        C.box((-hw * 0.7, y - 1.6, BED_Z), (hw * 0.7, y + 1.6, -th))
    C.box((-hw, -water / 2, -th), (hw, water / 2, 0.0))
    C.box((-hw, -span / 2, -0.5), (hw, span / 2, 0.0))
    for sx in (1, -1):                                    # the pavements stand 0.16 m above the road, the carriageway and the junction bands are at 0
        C.box((min(car / 2 * sx, hw * sx), ya, 0.0), (max(car / 2 * sx, hw * sx), yb, CURB))
    for sx in (1, -1):
        px = hw * sx
        C.box((min(px, px - sx * 0.4), -water / 2, CURB), (max(px, px - sx * 0.4), water / 2, CURB + 1.1))
    return M, C, dict(kind='bridge', w=float(wd), d=float(span), h=15.0, dist=560.0)


def bridge_cable(span, cls='A', seed=0, pylon_h=92.0, water=None):
    """hero cable-stayed bridge (H pylon at the middle of the span, harp cables, lit)"""
    M, C, meta = bridge_girder(span, cls, seed, water)
    hw = SW[cls] / 2
    rng = np.random.default_rng(seed + 1)
    ph = pylon_h
    for sx in (-1, 1):
        x = sx * (hw - 2.0)
        # tapered pylon leg
        M.loft(rect(3.2, 4.4, x, 0), CURB, rect(2.0, 3.0, x, 0), ph, 'nc_concrete', 'nc_concrete', tile=(4, 6))
        # LED edge lines up the leg
        for dy in (-1.5, 1.5):
            P.bar(M, (x + sx * 1.6, dy * 0.9, CURB + 0.5), (x + sx * 1.0, dy * 0.7, ph - 1), 0.14, 'nc_strip_cyan', emis=1.0)
        P.beacon_light(M, (x - 0.15, -0.15, ph))
        C.box((x - 1.6, -2.2, CURB), (x + 1.6, 2.2, ph * 0.5))
        C.box((x - 1.2, -1.8, ph * 0.5), (x + 1.2, 1.8, ph))
    for z in (ph * 0.45, ph * 0.8):
        M.box((-hw + 1.0, -1.4, z), (hw - 1.0, 1.4, z + 2.0), 'nc_concrete_dark', tile=(3, 3))
        C.box((-hw + 1.0, -1.4, z), (hw - 1.0, 1.4, z + 2.0))
    # harp of stay cables on both legs, both directions
    n = 9
    for sx in (-1, 1):
        x_leg, x_deck = sx * (hw - 2.0), sx * (hw - 0.6)
        for k in range(n):
            zt = ph * 0.52 + (ph * 0.44) * k / (n - 1)
            for sd in (-1, 1):
                yd = sd * (7.0 + 6.4 * k)
                if abs(yd) > (water or span) / 2 - 2:
                    continue
                M.tube(np.array([(x_leg, sd * 0.8, zt), (x_deck, yd, CURB + 1.2)]), 0.11, 4, 'nc_strip_white', tile=(4, 1), caps=False, emis=0.7, smooth=False)
    M.light((0, 0, ph * 0.6), P.COOL, 3.0, 80.0)
    meta.update(h=float(ph + 6), dist=800.0, hero=True)
    return M, C, meta


def skybridge(length, height=3.6, width=4.2, seed=0):
    """lit glass tube + steel truss between two buildings; along x, centred"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    M.box((-length / 2, -width / 2, 0.0), (length / 2, width / 2, height), 'nc_glass_e', tile=(3.2 * 4, 3.8 * 8), emis=0.95, skip=('+x', '-x'), uvoff=(float(rng.integers(0, 4)) / 4, 0.0))
    M.box((-length / 2, -width / 2 - 0.3, -0.9), (length / 2, width / 2 + 0.3, 0.0), 'nc_metal_dark', tile=(2, 2))
    M.box((-length / 2, -width / 2 - 0.3, height), (length / 2, width / 2 + 0.3, height + 0.5), 'nc_metal_dark', tile=(2, 2))
    M.box((-length / 2, -width / 2 - 0.32, height + 0.5), (length / 2, -width / 2 - 0.2, height + 0.58), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.box((-length / 2, width / 2 + 0.2, height + 0.5), (length / 2, width / 2 + 0.32, height + 0.58), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    # truss diagonals under the tube
    n = max(2, int(length // 5))
    for k in range(n):
        x0 = -length / 2 + k * length / n
        x1 = x0 + length / n
        zz = -2.2
        P.bar(M, (x0, -width / 2 - 0.2, -0.9), (x0 + (x1 - x0) / 2, -width / 2 - 0.2, zz), 0.16, 'nc_steel')
        P.bar(M, (x0 + (x1 - x0) / 2, -width / 2 - 0.2, zz), (x1, -width / 2 - 0.2, -0.9), 0.16, 'nc_steel')
        P.bar(M, (x0, width / 2 + 0.2, -0.9), (x0 + (x1 - x0) / 2, width / 2 + 0.2, zz), 0.16, 'nc_steel')
        P.bar(M, (x0 + (x1 - x0) / 2, width / 2 + 0.2, zz), (x1, width / 2 + 0.2, -0.9), 0.16, 'nc_steel')
    M.light((0, 0, height * 0.6), P.COOL, 1.5, 28.0)
    C.box((-length / 2, -width / 2 - 0.3, -0.9), (length / 2, width / 2 + 0.3, height + 0.5))
    return M, C, dict(kind='skybridge', w=float(length), d=float(width), h=float(height + 3), dist=520.0)


def skyline_strip(L, seed, rows=2, hmin=70.0, hmax=250.0):
    """distant towers (no podiums, no collision): a long strip along +x, centred, depth ~ rows * 55 m"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    mats = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_e', 'nc_glass_h', 'nc_glass_f', 'nc_glass_d']
    x = -L / 2
    while x < L / 2 - 20:
        w = float(rng.uniform(22, 46))
        for r in range(rows):
            d = float(rng.uniform(22, 40))
            h = float(rng.uniform(hmin, hmax)) * (1.0 + 0.25 * (r == 1))
            cy = r * 52.0 + float(rng.uniform(-6, 6))
            poly = rect(w, d, x + w / 2 + (r % 2) * 6, cy)
            m = mats[int(rng.integers(len(mats)))]
            K.tier(M, C, poly, 0.0, h, m, rng, emis=0.9, ledge_every=0, corners=False, col=False)
            if h > 160:
                P.beacon_light(M, (poly[:, 0].mean(), poly[:, 1].mean(), h))
            if rng.random() < 0.4:
                M.extrude(K.offset_poly(poly, 0.3), h - 0.7, h, 'nc_strip_cyan' if rng.random() < 0.6 else 'nc_strip_white', 'nc_strip_cyan', tile=(2, 1), emis=1.0)
        x += w + float(rng.uniform(2, 10))
    M.box((-L / 2 - 4, -30, -3.0), (L / 2 + 4, rows * 52.0 + 30, 0.0), 'nc_concrete_dark', tile=(8, 8))
    return M, C, dict(kind='skyline', w=float(L), d=float(rows * 52.0 + 60), h=float(hmax * 1.3 + 30), dist=1500.0, nocol=True)
