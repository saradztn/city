# Created by: Arena.ai Agent Mode (AI) - headless test of the NightCity MTA:SA resource.
# Runs the REAL client.lua / tour.lua / server.lua (Lua 5.1 via lupa) against the strict API model in mta_stub_nc.lua and drives them through
# show / draw frames / commands / tour / free camera / hide / re-show / resource stop, plus failure injection (model limit, shader compile
# failure, missing ground, missing files).  It cannot replace a test inside a real MTA client - it catches every logic, API-usage,
# argument-type, ordering and cleanup error that does not depend on the engine itself.
#     python3 mta_lua_test_nc.py
import glob
import math
import os
import re
import sys
from lupa import lua51

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.environ.get('NC_RES') or os.path.join(HERE, '..', 'resource', 'NightCity')
sys.path.insert(0, HERE)
from lib import readers

fails = []
passed = [0]


def check(c, msg):
    print('  [%s] %s' % ('PASS' if c else 'FAIL', msg))
    if c:
        passed[0] += 1
    else:
        fails.append(msg)


def rd(f):
    return open(os.path.join(RES, f), encoding='utf8').read()


def fx_vars(path):
    out = set()
    for ln in open(path, encoding='utf8'):
        m = re.match(r'^(float\d?(?:x\d)?|texture|int|bool)\s+(\w+)\s*([(:=;<])', ln)
        if m and m.group(3) != '(':
            out.add(m.group(2))
    return out


TEXTURES = set()
for p in glob.glob(os.path.join(RES, 'files', '*.txd')):
    for t in readers.read_txd(p)['textures']:
        TEXTURES.add(t['name'])
META = rd('meta.xml')
META_FILES = re.findall(r'<(?:file|script) src="([^"]+)"', META)


def boot(server_patch=None, drop_files=()):
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(open(os.path.join(HERE, 'mta_stub_nc.lua'), encoding='utf8').read())
    T = lua.globals().T
    for f in META_FILES:
        if f not in drop_files:
            T.files[f] = True
    for n in TEXTURES:
        T.textures[n] = True
    for fx in ('wet.fx',):
        t = lua.table()
        for v in fx_vars(os.path.join(RES, fx)):
            t[v] = True
        T.fxvars[fx] = t
    for f in ('models.lua', 'layout.lua', 'sprites.lua', 'client.lua', 'tour.lua'):
        T.load('client', f, rd(f))
    srv = rd('server.lua')
    if server_patch:
        srv = server_patch(srv)
    T.load('server', 'layout.lua', rd('layout.lua'))
    T.load('server', 'server.lua', srv)
    return lua, T


def chat(T):
    return [T.chat[i] for i in range(1, int(T.chatCount()) + 1)]


def adv(T, ms, dt=50):
    for _ in range(int(ms / dt)):
        T.frame(dt)


def wait_for(T, cond, max_ms=180000, dt=50):
    t = 0
    while t < max_ms:
        if cond():
            return True
        T.frame(dt)
        t += dt
    return cond()


def world(T, k):
    return T.world[k]


def errors(T):
    e = T.errors()
    return [e[i] for i in range(1, len(e) + 1)]


def xyz(T, el):
    return float(T.elementProp(el, 'x')), float(T.elementProp(el, 'y')), float(T.elementProp(el, 'z'))


# =====================================================================================================================================
print('== static: both sides parse, commands registered ==')
lua, T = boot()
G = lambda n: T.globalOf('client', n)
N_MODELS = len(G('NC_MODELS'))
N_OBJECTS = len(G('NC_OBJECTS'))
N_WATER = len(G('NC_WATER'))
N_SPRITES = len(G('NC_SPRITES'))
print('   models %d, objects %d, water rects %d, sprites %d' % (N_MODELS, N_OBJECTS, N_WATER, N_SPRITES))
for c in ('ncfx', 'ncrain', 'nctime', 'ncview', 'ncinfo', 'nctour', 'ncfree'):
    check(T.hasCmd('client', c), 'client command /%s registered' % c)
for c in ('ncshow', 'nchide', 'ncz', 'ncempty'):
    check(T.hasCmd('server', c), 'server command /%s registered' % c)
    check(not T.hasCmd('client', c), 'server command /%s has no conflicting client placeholder' % c)
check(not errors(T), 'loading the scripts raised no error')

print('\n== resource start: nothing is shown until the server says so ==')
T.fireClient('onClientResourceStart', T.resourceRoot)
check(T.logHas('toClient:nc:hide'), 'server answered the client request with nc:hide')
check(world(T, 'birds') is None and world(T, 'fog') is None, 'the world was not touched by nc:hide')
check(not errors(T), 'no handler error')

print('\n== /ncshow: load models, build objects, water, sprites, ambience, shaders ==')
T.cmd('client', 'nctime', '21')  # selecting night while models load must survive city initialization
T.cmd('server', 'ncshow')
check(bool(T.player.frozen), 'the player is held in the air while the city loads')
ok = wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 120000)
check(ok, 'all %d objects created' % N_OBJECTS)
check(int(T.nmodels) == N_MODELS, '%d model ids allocated (one per model)' % N_MODELS)
check(int(T.modelsComplete()) == N_MODELS, 'every model went COL -> TXD -> DFF')
check(int(T.objectsFrozen()) == N_OBJECTS, 'all objects are frozen (no physics)')
check(int(T.objectsLowLOD()) == 0, 'city objects are high-LOD so their COL surfaces remain solid')
n_sky = sum(1 for i in range(1, N_OBJECTS + 1) if G('NC_OBJECTS')[i][6] == 'skyline')
check(int(T.objectsNoCollision()) == n_sky and n_sky > 0, '%d skyline objects have collisions disabled' % n_sky)
check(T.alive('water') == N_WATER, '%d river water quads' % N_WATER)
check(T.alive('texture') == 2, 'glow + steam textures loaded')
adv(T, 3000)
check(bool(T.player.frozen) is False, 'the player was released after the ground probe')
check(T.alive('sound') >= 4, 'ambience running (%d sounds)' % T.alive('sound'))
check(T.alive('shader') == 1, 'the localized wet.fx material shader created')
check(int(T.shaderTextures('wet.fx')) == 9, 'wet shader applied to 9 ground textures')
check(abs(float(T.shaderValue('wet.fx', 'gWet')) - 0.0) < 1e-6, 'dry daylight starts with gWet = 0')
check(T.shaderValue('wet.fx', 'gScreen') is not None and T.alive('screensource') == 1, 'screen source handed only to the localized wet shader')
check(T.shaderValue('wet.fx', 'gTun', 1) is not None and T.shaderValue('wet.fx', 'gTun', 4) is not None, 'tunnel volume handed to the wet shader')
check(world(T, 'fog') == 380 and world(T, 'far') == 1200, 'fog 380 m, far clip 1200 m')
check(T.weather == 0 and T.hour == 21 and T.minute == 30, 'night clock selection survives city loading without being forced back to noon')
check(world(T, 'clouds') is None and world(T, 'birds') is None and world(T, 'ambient_general') is None, 'native clouds, birds and ambience remain enabled')
check(world(T, 'occlusions') is False, 'city occlusions are disabled while visible')
check(abs(float(world(T, 'rain')) - 0.0) < 1e-6, 'rain level follows the current dry game weather')
check(world(T, 'sky') is None and world(T, 'minute') is None, 'native timecycle and minute duration are left untouched')
check(T.chatContains('objects.'), 'welcome message printed')
check(not errors(T), 'no handler / timer error during loading: %s' % errors(T)[:2])

print('\n== rendering ==')
sx, sy, sz = [float(v) for v in G('NC_POINTS')['spawn'].values()]
T.setCam(sx, sy, sz + 900.0 + 1.5, sx, sy + 20, sz + 900.0 + 1.5)
T.resetCounters()
adv(T, 800, 16)
per_frame = int(T.lines3d) / 50.0
check(int(T.lines3d) > 0, 'glow billboards drawn near the spawn point (%.0f per frame)' % per_frame)
check(per_frame <= 340, 'at most 340 billboards per frame')
check(T.handlerCount('client', 'onClientHUDRender') == 0, 'no fullscreen post-processing pass is installed')
check(int(T.screenUpdates()) >= 40, 'wet-material screen source updated every frame')
T.cmd('client', 'ncinfo')
check('glow sprites drawn=' in T.lastChat() and 'objects=%d' % N_OBJECTS in T.lastChat(), '/ncinfo: ' + T.lastChat()[:150])

print('\n== commands: /ncfx /ncrain /nctime /ncview ==')
T.cmd('client', 'ncfx')                       # 1 -> 0
check(T.alive('shader') == 0 and T.handlerCount('client', 'onClientHUDRender') == 0 and T.alive('screensource') == 0, '/ncfx turns off the wet shader and releases its screen source')
T.cmd('client', 'ncfx')                       # 0 -> 1
check(T.alive('shader') == 1 and int(T.shaderTextures('wet.fx')) == 9, '/ncfx enables the localized wet-road shader')
T.cmd('client', 'ncfx', '0')
check(T.alive('shader') == 0 and T.shaderOf('wet.fx') is None, '/ncfx 0 removes the wet shader from every texture')
T.cmd('client', 'ncfx', '1')
check(T.alive('shader') == 1 and int(T.shaderTextures('wet.fx')) == 9, '/ncfx 1 reapplies the wet shader')
T.cmd('client', 'ncrain', '0.5')
adv(T, 100)
check(abs(float(world(T, 'rain')) - 0.5) < 1e-6 and abs(float(T.shaderValue('wet.fx', 'gWet')) - 0.5) < 1e-6, '/ncrain 0.5 -> rain level and gWet')
T.cmd('client', 'ncrain', '7')
check(abs(float(world(T, 'rain')) - 1.0) < 1e-6, '/ncrain clamps to 1')
T.cmd('client', 'ncrain')
check('usage' in T.lastChat(), '/ncrain without value prints the usage')
T.cmd('client', 'nctime', '3')
adv(T, 1100)
check(T.hour == 3 and T.minute == 30, '/nctime 3 -> 03:30 without overriding the native minute duration')
T.cmd('client', 'nctime', '0')
adv(T, 1100)
check(T.hour == 0, '/nctime 0')
T.cmd('client', 'ncview', 'nonsense')
check('usage' in T.lastChat() and 'spawn' in T.lastChat(), '/ncview with a wrong name lists the points')
pts = G('NC_POINTS')
names = [k for k in pts.keys()]
check({'spawn', 'tunnel_in', 'tunnel_out', 'tunnel_mid'} <= set(names), 'named points: ' + ' '.join(sorted(names)))
T.groundHit = False
T.cmd('client', 'ncview', 'tunnel_mid')
px, py, pz = xyz(T, T.player)
mid = pts['tunnel_mid']
check(abs(px - mid[1]) < 1e-3 and abs(py - mid[2]) < 1e-3 and abs(pz - 900 - mid[3] - 0.5) < 1e-3, '/ncview tunnel_mid puts the player in the tunnel')
adv(T, 700)
check(bool(T.player.frozen), '/ncview holds the player until the ground at the destination exists')
T.groundHit = True
adv(T, 800)
check(bool(T.player.frozen) is False, '... and releases him once it does')
adv(T, 700)
check(abs(float(world(T, 'rain'))) < 1e-9, 'inside the tunnel it does not rain')
check(float(T.sounds('rain_loop')[1].vol) < 0.1 and float(T.sounds('hum_loop')[1].vol) > 0.3, 'tunnel acoustics: rain muffled, drone up')
check(abs(float(T.shaderValue('wet.fx', 'gWet')) - 0.25 * 1.0) < 0.3 * 1.0, 'the road is (almost) dry in the tunnel')
T.cmd('client', 'ncview', 'spawn')
adv(T, 1500)
check(abs(float(world(T, 'rain')) - 1.0) < 1e-6, 'outside again: the rain is back')
check(float(T.sounds('rain_loop')[1].vol) > 0.3, 'rain loop audible again')

print('\n== camera tour ==')
from nc import plan as PLAN
plan = PLAN.build_plan()
tg = plan.tunnel
tour = G('NC_TOUR')
n_keys = len(tour)
dur = sum(float(tour[i][7]) for i in range(1, n_keys))
print('   %d keys, %.0f s' % (n_keys, dur))
T.cmd('client', 'nctour')
check(bool(T.player.frozen), 'the tour freezes the player')
cams = []
t = 0
while T.handlerCount('client', 'onClientPreRender') > 0 and t < (dur + 30) * 1000:
    T.frame(50)
    t += 50
    cams.append([float(v) for v in (T.cam[1], T.cam[2], T.cam[3], T.cam[4], T.cam[5], T.cam[6])])
check(abs(t / 1000.0 - dur) < 2.0, 'the tour ends after %.0f s (expected %.0f s)' % (t / 1000.0, dur))
check(T.camIsPlayer() and bool(T.player.frozen) is False, 'the camera goes back to the player and the player is released')
check(T.chatContains('tour finished'), 'tour finished message')
check(not T.binds['space:down'] and not T.binds['backspace:down'], 'tour keys unbound')
# the camera must be inside the tube whenever it is in the covered part of the tunnel
bad = 0
inside = 0
off_map = 0
E = G('NC_EXTENT')
for c in cams:
    cx, cy, cz = c[0], c[1], c[2] - 900.0
    if not (E['x0'] - 150 < cx < E['x1'] + 150 and E['y0'] - 150 < cy < E['y1'] + 150):
        off_map += 1
    if abs(cx - tg['x']) < 6.0 and tg['y_cov0'] + 3 < cy < tg['y_cov1'] - 3:
        inside += 1
        road = PLAN.tunnel_z(tg, cy)
        if not (road + 0.8 < cz < road + 4.2):
            bad += 1
check(inside > 200, 'the tour spends %d frames in the covered tunnel' % inside)
check(bad == 0, 'while in the tunnel the camera always stays between road + 0.8 m and the ceiling (%d violations)' % bad)
check(off_map == 0, 'the camera never leaves the city surroundings')
T.cmd('client', 'nctour')
adv(T, 2000)
check(T.press('space'), 'space is bound while the tour runs')
check(T.handlerCount('client', 'onClientPreRender') == 0 and T.camIsPlayer(), 'space stops the tour at once')

print('\n== free camera ==')
T.cmd('client', 'ncfree')
check(bool(T.player.frozen) and T.handlerCount('client', 'onClientCursorMove') == 1, '/ncfree freezes the player and listens to the mouse')
c0 = [float(v) for v in (T.cam[1], T.cam[2], T.cam[3])]
T.setKey('w', True)
adv(T, 1000, 20)
c1 = [float(v) for v in (T.cam[1], T.cam[2], T.cam[3])]
d_walk = math.dist(c0, c1)
T.setKey('lshift', True)
adv(T, 1000, 20)
c2 = [float(v) for v in (T.cam[1], T.cam[2], T.cam[3])]
d_fast = math.dist(c1, c2)
T.setKey('lshift', False)
T.setKey('w', False)
check(15 < d_walk < 30 and d_fast > 3 * d_walk, 'W moves the camera (%.0f m/s, %.0f m/s with shift)' % (d_walk, d_fast))
look0 = (T.cam[4] - T.cam[1], T.cam[5] - T.cam[2])
T.fireClient('onClientCursorMove', T.root, 0.5, 0.5, 960 + 120, 540)
for _ in range(7):
    T.fireClient('onClientCursorMove', T.root, 0.5, 0.5, 960 + 120, 540)
T.frame(20)
look1 = (T.cam[4] - T.cam[1], T.cam[5] - T.cam[2])
check(abs(look0[0] - look1[0]) + abs(look0[1] - look1[1]) > 1.0, 'the mouse turns the camera')
T.cmd('client', 'ncfree')
check(T.handlerCount('client', 'onClientCursorMove') == 0 and T.handlerCount('client', 'onClientPreRender') == 0 and T.camIsPlayer() and bool(T.player.frozen) is False, '/ncfree again: camera and player restored')

print('\n== /ncz and the server ==')
o = T.firstObject()
z0 = float(T.elementProp(o, 'z'))
T.cmd('server', 'ncz', '0.5')
check(abs(float(T.elementProp(o, 'z')) - z0 - 0.5) < 1e-6, '/ncz 0.5 lifts every object by 0.5 m')
T.cmd('server', 'ncz', '100')
check(abs(float(T.elementProp(o, 'z')) - z0 - 8.5) < 1e-6, '/ncz is clamped to 8 m per call')
T.cmd('server', 'ncz', '-20')
T.cmd('server', 'ncz', '-0.5')
check(abs(float(T.elementProp(o, 'z')) - z0) < 1e-6, 'back to the original height (-8 clamped, then -0.5)')
T.cmd('server', 'ncz')
check('Usage' in chat(T)[-1], '/ncz without value prints the usage')
v_in = T.addVehicle(0.0, 0.0, 905.0)
p_in = T.addPed(10.0, 10.0, 905.0)
v_out = T.addVehicle(2000.0, -1500.0, 14.0)
T.cmd('server', 'ncempty', 'now')
check((not T.elementProp(v_in, 'alive')) and (not T.elementProp(p_in, 'alive')) and bool(T.elementProp(v_out, 'alive')), '/ncempty now removes vehicles and peds inside the city volume only')
T.cmd('server', 'ncempty', 'on')
v2 = T.addVehicle(5.0, 5.0, 905.0)
adv(T, 2100)
check(not T.elementProp(v2, 'alive'), '/ncempty on keeps the city empty')
T.cmd('server', 'ncempty', 'off')
n_server_timers = int(T.liveTimers('server'))
check(n_server_timers == 0, 'guard timer killed by /ncempty off')

print('\n== /nchide: everything is removed and the world is restored ==')
T.cmd('server', 'nchide')
px, py, pz = xyz(T, T.player)
check(pz < 100 and abs(px - 2495) < 1, 'players in the sky city are sent to a safe place on the ground')
check(T.alive('object') == 0 and T.alive('water') == 0 and T.alive('sound') == 0 and T.alive('texture') == 0, 'objects, water, sounds, textures destroyed')
check(T.alive('shader') == 0 and T.alive('screensource') == 0, 'wet shader and its screen source destroyed')
check(all(T.handlerCount('client', e) == 0 for e in ('onClientRender', 'onClientHUDRender', 'onClientPreRender', 'onClientCursorMove')), 'render handlers removed')
check(int(T.liveTimers('client')) == 1, 'only the (idle) safety-net timer is left (%d)' % int(T.liveTimers('client')))
check(world(T, 'birds') is None and world(T, 'clouds') is None and world(T, 'ambient_general') is None and world(T, 'occlusions') is True, 'native clouds, birds and ambience are untouched; occlusions restored')
check(world(T, 'rain') == 0 and world(T, 'sky') is None and world(T, 'fog') is None and world(T, 'far') is None and world(T, 'wind') is None and world(T, 'haze') is None, 'original rain restored; temporary fog, far clip and wind cleared')
check(world(T, 'minute') is None and T.weather == 0 and T.hour == 0 and T.minute == 30, 'native minute duration and selected night clock are preserved')
check(int(T.nmodels) == N_MODELS, 'models stay loaded for a quick re-show')
check(not errors(T), 'no error: %s' % errors(T)[:2])

print('\n== show again, /ncshow here, resource stop ==')
req0 = int(T.calls['engineRequestModel'])
T.player.x, T.player.y, T.player.z = 500.0, -300.0, 20.0
T.cmd('server', 'ncshow', 'here')
wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000)
check(int(T.calls['engineRequestModel']) == req0, 're-show does not reload the models')
check(T.alive('object') == N_OBJECTS and T.alive('water') == N_WATER, 'city rebuilt (%d objects, %d water)' % (T.alive('object'), T.alive('water')))
o = T.firstObject()
ob = G('NC_OBJECTS')[1]
sp = pts['spawn']
ex, ey, ez = 500.0 - sp[1] + ob[2], -300.0 - sp[2] + ob[3], 20.0 - sp[3] + ob[4]
x, y, z = xyz(T, o)
check(abs(x - ex) < 1e-3 and abs(y - ey) < 1e-3 and abs(z - ez) < 1e-3, '/ncshow here puts the spawn point exactly at the player')
adv(T, 3000)
check(bool(T.player.frozen) is False, 'player released')
T.cmd('server', 'ncshow', '100', '200', '900')
wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000)
o = T.firstObject()
x, y, z = xyz(T, o)
check(abs(x - (100 + ob[2])) < 1e-3 and abs(z - (900 + ob[4])) < 1e-3, '/ncshow x y z')
T.fireClient('onClientResourceStop', T.resourceRoot)
check(int(T.nmodels) == 0 and T.alive('object') == 0, 'resource stop frees every model and object')
check(not errors(T), 'no error during the whole session: %s' % errors(T)[:3])
check(int(T.liveTimers('client')) <= 1, 'no client timer survives the resource stop')

# =====================================================================================================================================
print('\n== failure injection: not enough free model ids ==')
lua, T = boot()
T.maxModels = 50
T.fireClient('onClientResourceStart', T.resourceRoot)
T.cmd('server', 'ncshow')
wait_for(T, lambda: T.chatContains('failed at'), 20000)
adv(T, 500)
check(T.chatContains('engineRequestModel') and T.chatContains('Model 51/288'), 'model allocation failure identifies the failing model and API')
check(int(T.nmodels) == 0 and T.alive('object') == 0, 'the partial models were freed again, no object created')
check(bool(T.player.frozen) is False, 'the player is not left frozen')
check(world(T, 'birds') is None, 'the atmosphere was never changed')
T.maxModels = None
T.cmd('server', 'nchide')
T.cmd('server', 'ncshow')
check(wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000), 'a later /ncshow works once ids are available')
check(not errors(T), 'no error: %s' % errors(T)[:2])

print('\n== failure injection: one model file is missing ==')
lua, T = boot(drop_files=('files/nc_i028.dff',))
T.cmd('server', 'ncshow')
wait_for(T, lambda: T.chatContains('failed at'), 30000)
adv(T, 500)
check(T.chatContains('nc_i028') and T.chatContains('engineLoadDFF'), 'the failing model file and loading API are identified')
check(int(T.nmodels) == 0 and T.alive('object') == 0 and T.alive('dff') == 0 and T.alive('col') == 0 and T.alive('txd') == 0, 'no model id and no loaded file leaks')
check(bool(T.player.frozen) is False, 'the player is not left frozen')
check(not errors(T), 'no error: %s' % errors(T)[:2])

print('\n== races: hide while loading, show twice ==')
lua, T = boot()
T.cmd('server', 'ncshow')
adv(T, 300)
check(T.alive('object') == 0 and 0 < int(T.nmodels) < N_MODELS, 'the models are still loading')
T.cmd('server', 'nchide')
adv(T, 60000)
check(T.alive('object') == 0 and T.alive('water') == 0 and T.alive('shader') == 0, '/nchide during loading cancels the show')
check(bool(T.player.frozen) is False and world(T, 'birds') is None, 'player free, world untouched')
T.cmd('server', 'ncshow')
adv(T, 200)
T.cmd('server', 'ncshow', '100', '200', '900')
check(wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000), 'second /ncshow while the first one is loading')
adv(T, 4000)
ob1 = G('NC_OBJECTS')[1]
x, y, z = xyz(T, T.firstObject())
check(T.alive('object') == N_OBJECTS and abs(x - (100 + ob1[2])) < 1e-3, 'one set of objects, at the second anchor')
check(not errors(T), 'no error: %s' % errors(T)[:2])

print('\n== failure injection: wet shader compile failure / fallback technique ==')
for mode in ('fail', 'fallback'):
    lua, T = boot()
    T.shaderMode = mode
    T.cmd('server', 'ncshow')
    check(wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000), '[%s] the city is shown without shaders' % mode)
    adv(T, 2000)
    check(T.alive('shader') == 0 and T.handlerCount('client', 'onClientHUDRender') == 0 and T.alive('screensource') == 0, '[%s] no shader, screen source, or HUD handler left' % mode)
    T.cmd('client', 'ncfx')
    check('could not compile' in T.lastChat(), '[%s] /ncfx tells the user' % mode)
    adv(T, 500)
    check(not errors(T), '[%s] no error: %s' % (mode, errors(T)[:2]))

print('\n== failure injection: wet shader only fails ==')
lua, T = boot()
T.cmd('server', 'ncshow')
wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000)
T.cmd('client', 'ncfx', '0')
T.shaderMode = 'ok'
orig = lua.eval('function() local f = T.C.dxCreateShader T.C.dxCreateShader = function(p, ...) if p == "wet.fx" then return false, "x" end return f(p, ...) end end')
orig()
T.cmd('client', 'ncfx', '1')
check(T.alive('shader') == 0 and T.alive('screensource') == 0 and 'wet.fx could not compile' in T.lastChat(), 'wet.fx failure leaves the city playable and explains the missing sheen')
check(not errors(T), 'wet.fx failure raised no handler error')

print('\n== failure injection: ground collision never appears ==')
lua, T = boot()
T.groundHit = False
T.cmd('server', 'ncshow')
wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000)
adv(T, 15000)
check(bool(T.player.frozen) and T.chatContains('stay frozen'), 'the player stays held (not dropped 900 m) and is told')
T.cmd('server', 'nchide')
check(bool(T.player.frozen) is False, '/nchide releases the player')
T.groundHit = True
T.cmd('server', 'ncshow')
wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000)
adv(T, 2000)
T.groundHit = False
T.cmd('client', 'ncview', 'plaza')
adv(T, 15000)
check(bool(T.player.frozen) and T.chatContains('not available here yet'), '/ncview without ground collision: the player stays held and is told')
T.cmd('server', 'nchide')
check(bool(T.player.frozen) is False, '/nchide releases him again')

print('\n== failure injection: audio / texture files missing ==')
lua, T = boot(drop_files=('files/audio/rain_loop.wav', 'files/audio/thunder.wav', 'files/fx/glow.png'))
T.cmd('server', 'ncshow')
check(wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000), 'city shown although rain_loop / thunder / glow files are missing')
adv(T, 30000)
check(not errors(T), 'no error: %s' % errors(T)[:2])
check(T.alive('texture') <= 1, 'no glow billboards, no crash')

print('\n== server: permissions ==')
lua, T = boot(server_patch=lambda s: s.replace('ADMIN_ONLY = false', 'ADMIN_ONLY = true'))
T.aclAdmin = False
T.cmd('server', 'ncshow')
check(T.chatContains('not allowed') and T.alive('object') == 0, 'ADMIN_ONLY: non-admin cannot show the city')
T.aclAdmin = True
T.cmd('server', 'ncshow')
check(wait_for(T, lambda: T.alive('object') >= N_OBJECTS, 60000), 'ADMIN_ONLY: an admin can')

print('\n== result: %d checks passed, %d failed ==' % (passed[0], len(fails)))
for f in fails:
    print('  FAILED:', f)
sys.exit(1 if fails else 0)
