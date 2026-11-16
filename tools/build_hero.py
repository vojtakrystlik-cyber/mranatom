#!/usr/bin/env python3
"""Build the light-weight interactive body for the home page from the atlas data.

    python tools/build_hero.py            # reads atlas/data, writes atlas/data/hero.json + hero.txt

Takes every bone and muscle, simplifies it hard (the home page has to load fast), and keeps for each
one its index in the atlas, so a click on the home page can open the same structure in the atlas.
build_model.py runs this automatically after a model swap.
"""
import argparse, base64, gzip, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import latin, meshio
from build_model import simplify_to_budget

SIDE_CS = {1: ' (vpravo)', 2: ' (vlevo)'}
SIDE_EN = {1: ' (right)', 2: ' (left)'}

def load_atlas(data):
    d = json.load(open(os.path.join(data, 'parts.json'), encoding='utf-8'))
    bufs = [gzip.decompress(base64.b64decode(open(os.path.join(data, f'body-{i}.txt')).read())) for i in range(d['chunks'])]
    return d, bufs

def geometry(p, bufs):
    b = bufs[p[4]]
    q = np.frombuffer(b, '<u2', p[8] * 3, p[5]).reshape(-1, 3).astype(np.float64) / 65535
    b0, b1 = np.array(p[16:19]), np.array(p[19:22])
    V = b0 + q * (b1 - b0)
    T = np.frombuffer(b, '<u4' if p[10] else '<u2', p[9], p[7]).reshape(-1, 3).astype(np.int64)
    return V, T

def build(data, bones_budget=55_000, muscles_budget=85_000, log=print):
    d, bufs = load_atlas(data)
    sysi = {s: i for i, s in enumerate(d['sys'])}
    groups = []
    for sysname, budget in (('skeletal', bones_budget), ('muscular', muscles_budget)):
        sel = [(i, p) for i, p in enumerate(d['parts']) if p[3] == sysi[sysname]]
        meshes = []
        for i, p in sel:
            V, T = geometry(p, bufs); meshes.append(meshio.Mesh(str(i), [], V, T))
        meshes = simplify_to_budget(meshes, budget, log=lambda s: log('  ' + sysname + ':' + s), floor=40)
        groups.append((sysname, sel, meshes))
    allV = np.vstack([m.V for _, _, ms in groups for m in ms])
    lo, hi = allV.min(0), allV.max(0); ext = np.maximum(hi - lo, 1e-6)
    Q, PID, IDX, parts = [], [], [], []
    vbase = tbase = 0
    for g, (sysname, sel, meshes) in enumerate(groups):
        for k, ((i, p), m) in enumerate(zip(sel, meshes)):
            n = d['names'][p[1]]; side = p[2]; sfx = n[3] and side
            cs = (n[2] or n[1]) + (SIDE_CS.get(side, '') if sfx else '')
            la = latin.with_side(n[1], n[4] if len(n) > 4 else latin.gender(n[1]), side) if sfx else n[1]
            en = n[0] + (SIDE_EN.get(side, '') if sfx else '')
            Q.append(np.rint((m.V - lo) / ext * 65535).astype('<u2'))
            PID.append(np.full(len(m.V), len(parts), '<u2'))
            IDX.append((m.T + vbase).astype('<u4'))
            parts.append([i, g, cs, la, en])
            vbase += len(m.V); tbase += len(m.T)
        if g == 0: bone_tris = tbase
    blob = np.concatenate([np.vstack(Q).ravel()]).tobytes() + np.concatenate(PID).tobytes()
    while len(blob) % 4: blob += b'\0'
    blob += np.vstack(IDX).ravel().tobytes()
    gz = gzip.compress(blob, 9)
    open(os.path.join(data, 'hero.txt'), 'w').write(base64.b64encode(gz).decode())
    json.dump({'v': vbase, 't': tbase, 'boneTris': bone_tris, 'min': [round(float(x), 6) for x in lo], 'max': [round(float(x), 6) for x in hi],
               'parts': parts}, open(os.path.join(data, 'hero.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log(f'  hero: {len(parts)} structures, {tbase:,} triangles, {len(gz)/1e6:.2f} MB compressed')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--data', default=os.path.join(HERE, '..', 'atlas', 'data'))
    ap.add_argument('--bones', type=int, default=55_000); ap.add_argument('--muscles', type=int, default=85_000)
    a = ap.parse_args(); build(a.data, a.bones, a.muscles)
