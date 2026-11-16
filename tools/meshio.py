"""Readers for anatomy models: binary FBX (7.x), GLB / glTF-binary and Wavefront OBJ.

Every reader returns a list of Mesh(name, path, V, T):
  name  object name as written in the file
  path  names of the parent groups (outermost first), used to guess the body system
  V     (n, 3) float64 vertex positions in the file's own units and axes, transforms applied
  T     (m, 3) int64 triangle indices
"""
import json, math, os, re, struct, zlib
from collections import namedtuple
import numpy as np

Mesh = namedtuple('Mesh', 'name path V T')


# ----------------------------------------------------------------- FBX
class _Node:
    __slots__ = ('name', 'props', 'kids')
    def __init__(s, name, props, kids): s.name, s.props, s.kids = name, props, kids
    def get(s, n): return next((k for k in s.kids if k.name == n), None)
    def all(s, n): return [k for k in s.kids if k.name == n]

_ARR = {b'f': ('f', 4), b'd': ('d', 8), b'l': ('q', 8), b'i': ('i', 4), b'b': ('?', 1)}

def _fbx_tree(path):
    data = open(path, 'rb').read()
    if not data.startswith(b'Kaydara FBX Binary'):
        raise ValueError(f'{path}: only binary FBX is supported (export as FBX binary, or use GLB/OBJ)')
    ver = struct.unpack_from('<I', data, 23)[0]
    wide = ver >= 7500; hdr = 25 if wide else 13

    def prop(o):
        t = data[o:o+1]; o += 1
        if t == b'Y': return struct.unpack_from('<h', data, o)[0], o + 2
        if t == b'C': return data[o] != 0, o + 1
        if t == b'I': return struct.unpack_from('<i', data, o)[0], o + 4
        if t == b'F': return struct.unpack_from('<f', data, o)[0], o + 4
        if t == b'D': return struct.unpack_from('<d', data, o)[0], o + 8
        if t == b'L': return struct.unpack_from('<q', data, o)[0], o + 8
        if t in (b'S', b'R'):
            n = struct.unpack_from('<I', data, o)[0]; o += 4
            v = data[o:o+n]; return (v.decode('utf-8', 'replace') if t == b'S' else v), o + n
        if t in _ARR:
            n, enc, clen = struct.unpack_from('<III', data, o); o += 12
            raw = data[o:o+clen]; o += clen
            if enc: raw = zlib.decompress(raw)
            fmt, _ = _ARR[t]
            return np.frombuffer(raw, dtype='<' + fmt, count=n), o
        raise ValueError(f'FBX property type {t!r} at {o}')

    def node(o):
        if wide: end, nprops, _ = struct.unpack_from('<QQQ', data, o); o += 24
        else: end, nprops, _ = struct.unpack_from('<III', data, o); o += 12
        if end == 0: return None, o
        nl = data[o]; o += 1
        name = data[o:o+nl].decode(); o += nl
        props = []
        for _ in range(nprops):
            v, o = prop(o); props.append(v)
        kids = []
        while o < end:
            if end - o == hdr and data[o:o+hdr] == b'\0' * hdr: o += hdr; break
            k, o = node(o)
            if k is None: break
            kids.append(k)
        return _Node(name, props, kids), end

    o = 27; top = []
    while o < len(data) - hdr:
        n, o2 = node(o)
        if n is None: break
        top.append(n); o = o2
    return _Node('root', [], top)

def _p70(n):
    out = {}
    pp = n.get('Properties70')
    if pp:
        for p in pp.all('P'): out[p.props[0]] = p.props[4:]
    return out

def _euler(r):
    x, y, z = [math.radians(v) for v in r]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx

def _fbx_name(n): return str(n.props[1]).split('\x00')[0]

def read_fbx(path):
    root = _fbx_tree(path)
    objs, conns = root.get('Objects'), root.get('Connections')
    geo, mod = {}, {}
    for n in objs.kids:
        if n.name == 'Geometry' and len(n.props) > 2 and n.props[2] == 'Mesh': geo[n.props[0]] = n
        elif n.name == 'Model': mod[n.props[0]] = n
    parent, geo_of = {}, {}
    for c in conns.all('C'):
        if c.props[0] != 'OO': continue
        a, b = c.props[1], c.props[2]
        if a in mod and (b in mod or b == 0): parent[a] = b
        elif a in geo and b in mod: geo_of[b] = a
    local = {}
    for k, n in mod.items():
        p = _p70(n)
        M = np.eye(4)
        M[:3, :3] = _euler(p.get('PreRotation', (0, 0, 0))) @ _euler(p.get('Lcl Rotation', (0, 0, 0))) @ np.diag(p.get('Lcl Scaling', (1, 1, 1)))
        M[:3, 3] = p.get('Lcl Translation', (0, 0, 0))
        local[k] = M
    world = {}
    def W(k):
        if k not in world:
            pa = parent.get(k, 0)
            world[k] = (W(pa) if pa in mod else np.eye(4)) @ local[k]
        return world[k]
    def ancestors(k):
        out, pa = [], parent.get(k, 0)
        while pa in mod: out.append(_fbx_name(mod[pa])); pa = parent.get(pa, 0)
        return out[::-1]
    out = []
    for mk, gk in geo_of.items():
        g = geo[gk]; v = g.get('Vertices'); pi = g.get('PolygonVertexIndex')
        if v is None or pi is None: continue
        V = v.props[0].reshape(-1, 3).astype(np.float64)
        M = W(mk); V = V @ M[:3, :3].T + M[:3, 3]
        P = pi.props[0].astype(np.int64)
        ends = np.where(P < 0)[0]; P = np.where(P < 0, ~P, P)
        tris, st = [], 0
        for e in ends:
            poly = P[st:e+1]
            for j in range(1, len(poly) - 1): tris.append((poly[0], poly[j], poly[j+1]))
            st = e + 1
        if tris:
            out.append(Mesh(_fbx_name(mod[mk]), ancestors(mk), V, np.array(tris, np.int64)))
    return out


# ----------------------------------------------------------------- GLB
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

def _quat(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])

def read_glb(path):
    d = open(path, 'rb').read()
    if d[:4] != b'glTF': raise ValueError(f'{path}: not a binary glTF (.glb)')
    jl = struct.unpack_from('<I', d, 12)[0]
    J = json.loads(d[20:20+jl])
    if any(e in (J.get('extensionsRequired') or []) for e in ('KHR_draco_mesh_compression', 'EXT_meshopt_compression')):
        raise ValueError(f'{path}: compressed glTF (Draco/meshopt) — export it without mesh compression')
    o = 20 + jl; bl = struct.unpack_from('<I', d, o)[0]; B = d[o+8:o+8+bl]

    def acc(i):
        a = J['accessors'][i]; bv = J['bufferViews'][a['bufferView']]
        n = _NC[a['type']]; dt = np.dtype(_CT[a['componentType']])
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0); stride = bv.get('byteStride', 0)
        if stride and stride != n * dt.itemsize:
            raw = np.frombuffer(B, np.uint8, a['count'] * stride, off).reshape(-1, stride)[:, :n * dt.itemsize]
            return np.ascontiguousarray(raw).view(dt).reshape(-1, n)
        arr = np.frombuffer(B, dt, a['count'] * n, off).reshape(-1, n)
        if a.get('normalized'):
            arr = arr.astype(np.float64) / np.iinfo(dt).max
        return arr

    def local(n):
        if 'matrix' in n: return np.array(n['matrix']).reshape(4, 4).T
        M = np.eye(4); M[:3, :3] = _quat(n.get('rotation', [0, 0, 0, 1])) @ np.diag(n.get('scale', [1, 1, 1]))
        M[:3, 3] = n.get('translation', [0, 0, 0]); return M

    out = []
    def walk(i, P, path):
        n = J['nodes'][i]; W = P @ local(n); name = n.get('name', f'node_{i}')
        if 'mesh' in n:
            Vs, Ts, base = [], [], 0
            for pr in J['meshes'][n['mesh']]['primitives']:
                if pr.get('mode', 4) != 4 or 'POSITION' not in pr['attributes']: continue
                V = acc(pr['attributes']['POSITION']).astype(np.float64)
                T = acc(pr['indices']).reshape(-1, 3).astype(np.int64) if 'indices' in pr else np.arange(len(V)).reshape(-1, 3)
                Vs.append(V); Ts.append(T + base); base += len(V)
            if Vs:
                V = np.vstack(Vs) @ W[:3, :3].T + W[:3, 3]
                out.append(Mesh(name, list(path), V, np.vstack(Ts)))
        for c in n.get('children', []): walk(c, W, path + [name])
    for r in J['scenes'][J.get('scene', 0)]['nodes']: walk(r, np.eye(4), [])
    return out


# ----------------------------------------------------------------- OBJ
def read_obj(path):
    verts, out = [], []
    name, group, faces = None, [], []
    def flush():
        if name is not None and faces:
            F = np.array(faces, np.int64)
            out.append((name, list(group), F))
    for line in open(path, encoding='utf-8', errors='replace'):
        if line.startswith('v '):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('f '):
            idx = []
            for tok in line.split()[1:]:
                i = int(tok.split('/')[0]); idx.append(i - 1 if i > 0 else len(verts) + i)
            for j in range(1, len(idx) - 1): faces.append((idx[0], idx[j], idx[j+1]))
        elif line.startswith('o '):
            flush(); name = line[2:].strip(); faces = []
        elif line.startswith('g '):
            g = line[2:].strip()
            if name is None or faces: flush(); name = g; faces = []
            else: group = [g]
    flush()
    V = np.array(verts, np.float64)
    meshes = []
    for n, grp, F in out:
        used, inv = np.unique(F, return_inverse=True)
        meshes.append(Mesh(n, grp, V[used], inv.reshape(-1, 3)))
    return meshes


def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.fbx': return read_fbx(path)
    if ext == '.glb': return read_glb(path)
    if ext == '.obj': return read_obj(path)
    raise ValueError(f'{path}: unsupported format {ext} (use FBX binary, GLB or OBJ)')

def read_inputs(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                files += [os.path.join(root, f) for f in sorted(fs) if f.lower().endswith(('.fbx', '.glb', '.obj'))]
        else:
            files.append(p)
    meshes = []
    for f in files:
        got = read_any(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        meshes += [Mesh(m.name, [stem] + m.path, m.V, m.T) for m in got]
        print(f'  read {os.path.basename(f)}: {len(got)} objects, {sum(len(m.T) for m in got):,} triangles')
    return meshes
