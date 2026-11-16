#!/usr/bin/env python3
"""Convert a 3D anatomy model (FBX binary / GLB / OBJ) into the data the web atlas loads.

    python tools/build_model.py MODEL [MODEL ...] --out atlas/data --credits tools/credits.json

What it does
  1. reads every object of the model(s), applies the file's transforms
  2. finds which way is up, which way the body faces and which side is left, then scales the body
     to the atlas frame (Y up, feet at 0, height 1.73 m, face towards +Z, body's right on -X)
  3. detects left/right from names (Left/Right, .l/.r, _L/_R, (L)/(R) ...) or from position
  4. names every structure in Latin, Czech and English (tools/names_dictionary.csv, name rules,
     and your own overrides in --names), sorts it into one of 15 body systems and 13 regions
  5. simplifies meshes until the whole body fits the triangle budget (--budget)
  6. writes atlas/data/parts.json + body-N.txt, a report and a preview image

Anything it could not name or classify goes to report/missing_names.csv. Fill in the Latin/Czech
columns, save it as your --names file and run the script again.
"""
import argparse, base64, collections, csv, gzip, json, os, re, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decim, meshio, name_rules

SYS = ['skeletal', 'muscular', 'connective', 'cardiac', 'arterial', 'venous', 'nervous', 'sensory', 'respiratory',
       'digestive', 'urinary', 'reproductive', 'endocrine', 'lymphatic', 'integumentary']
REG = ['caput', 'collum', 'humerus', 'thorax', 'dorsum', 'abdomen', 'pelvis', 'brachium', 'antebrachium', 'manus', 'femur', 'crus', 'pes']
HEIGHT = 1.73

# ------------------------------------------------------------------ names & sides
SIDE_PATTERNS = [
    (r'^(left|right)[ _.-]+', 'pre'), (r'[ _.-]+(left|right)$', 'post'),
    (r'\.(l|r)$', 'post'), (r'[ _-](l|r)$', 'post'), (r'\((l|r|left|right)\)$', 'post'),
    (r'\b(left|right)\b ?', 'mid'), (r'_(l|r)_', 'mid'),
]
def split_side(raw):
    s = raw.strip(); side = 0
    for pat, _ in SIDE_PATTERNS:
        m = re.search(pat, s, flags=re.I)
        if m:
            w = m.group(1).lower(); side = 2 if w.startswith('l') else 1
            s = (s[:m.start()] + ' ' + s[m.end():]).strip()
            break
    return side, s

def tidy(s):
    s = re.sub(r'\.\d{3}$', '', s)                     # Blender duplicates: name.001
    s = s.replace('_', ' ').replace('*', '').replace('//', ' ')
    s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)          # CamelCase -> words
    s = re.sub(r'\s+', ' ', s).strip(" .-'")
    return s[:1].upper() + s[1:] if s else s

def key(s):
    s = s.lower()
    s = re.sub(r'\(.*?\)', ' ', s)
    s = re.sub(r'\b(the|muscle|muscles|musculus|m\.|bone|of the)\b', ' ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

class Names:
    def __init__(self, files):
        self.exact, self.loose, self.sys_override = {}, {}, {}
        for f in files:
            if not f or not os.path.exists(f): continue
            with open(f, encoding='utf-8-sig') as fh:
                sample = fh.read(2048); fh.seek(0)
                delim = ';' if sample.count(';') >= sample.count(',') else ','
                for r in csv.DictReader(fh, delimiter=delim):
                    en = (r.get('en') or r.get('name') or r.get('source_name') or '').strip()
                    if not en: continue
                    la, cs = (r.get('la') or '').strip(), (r.get('cs') or '').strip()
                    for k, store in ((en, self.exact), (key(en), self.loose)):
                        old = store.get(k, ('', ''))
                        store[k] = (la or old[0], cs or old[1])
                    if (r.get('system') or '').strip() in SYS:
                        self.sys_override[en] = r['system'].strip(); self.sys_override[key(en)] = r['system'].strip()
                    if r.get('source_name'):
                        self.exact[r['source_name'].strip()] = self.exact[en]
    def lookup(self, raw, en):
        la, cs = '', ''
        for cand in (raw, en, key(en)):
            for store in (self.exact, self.loose):
                if cand in store:
                    a, b = store[cand]; la = la or a; cs = cs or b
        r = name_rules.rules(en)
        if r: la = la or r[0]; cs = cs or r[1]
        cs = cs or (name_rules.cs_rule(en) or '')
        return la, cs
    def system(self, raw, en):
        return self.sys_override.get(raw) or self.sys_override.get(en) or self.sys_override.get(key(en))

# ------------------------------------------------------------------ body systems
def has(t, *w): return any(x in t for x in w)
GROUP_HINTS = [
    ('integumentary', ('integument', 'skin', 'hair', 'nail')),
    ('skeletal', ('skelet', 'bones', 'osteo', 'cartilage')),
    ('muscular', ('muscul', 'muscles', 'myo')),
    ('connective', ('ligament', 'tendon', 'fascia', 'joint', 'connective', 'capsule', 'bursa')),
    ('lymphatic', ('lymph',)),
    ('nervous', ('nervous', 'nerve', 'neuro', 'brain', 'spinal cord')),
    ('arterial', ('arter',)),
    ('venous', ('vein', 'venous')),
    ('cardiac', ('heart', 'cardiac')),
    ('respiratory', ('respir', 'lung', 'pulmo')),
    ('digestive', ('digest', 'aliment', 'gastro')),
    ('urinary', ('urin', 'renal')),
    ('reproductive', ('reprod', 'genital')),
    ('endocrine', ('endocrin', 'gland')),
    ('sensory', ('sense', 'sensory', 'eye', 'ear')),
]
def classify(name, path):
    n = name.lower()
    # structure-level rules first: they beat the folder the object sits in
    if has(n, 'cartilage') and not has(n, 'costal cartilage', 'articular cartilage'):
        return 'respiratory' if has(n, 'thyroid', 'cricoid', 'arytenoid', 'epiglott', 'corniculate', 'cuneiform cart', 'trache', 'bronch', 'nasal', 'alar') else 'skeletal'
    if has(n, 'ligament', 'tendon', 'aponeurosis', 'fascia', 'retinacul', 'tendon sheath', 'bursa', 'meniscus', 'menisci', 'labrum', 'articular capsule',
           'joint capsule', 'interosseous membrane', 'linea alba', 'raphe', 'iliotibial', 'intervertebral dis', 'nucleus pulposus', 'articular disc', 'membrane of'):
        if not has(n, 'tympanic', 'thyrohyoid membrane') or has(n, 'ligament'):
            return 'connective'
    if has(n, 'lymph', 'node', 'nodes', 'tonsil', 'spleen', 'thymus') and not has(n, 'atrioventricular node', 'sinuatrial node'):
        return 'lymphatic' if not has(n, 'thymus') else 'endocrine'
    if has(n, 'artery', 'arteries', 'arter', 'aorta', 'aortic', 'celiac trunk', 'coeliac trunk', 'brachiocephalic trunk', 'costocervical', 'thyrocervical', 'pulmonary trunk') \
            and not has(n, 'nerve', 'plexus', 'node', 'valve', 'leaflet', 'cusp'):
        return 'arterial'
    if has(n, 'vein', 'venous', 'vena ', 'vena cava', 'sinus', 'azygos') and not has(n, 'nerve', 'node', 'sinus of frontal', 'sinus of sphenoid', 'maxillary sinus',
                                                                                 'paranasal', 'frontal sinus', 'sphenoidal sinus', 'ethmoid', 'tarsi', 'renal sinus'):
        return 'venous'
    if has(n, 'nerve', 'nervus', 'plexus', 'ganglion', 'ganglia', 'gyrus', 'gyri', 'sulcus', 'lobe of cerebrum', 'cerebell', 'cerebr', 'brain', 'spinal cord',
           'medulla oblongata', 'pons', 'midbrain', 'thalam', 'nucleus', 'nuclei', 'tract', 'fasciculus', 'ventricle of brain', 'lateral ventricle', 'third ventricle',
           'fourth ventricle', 'cauda equina', 'corpus callosum', 'hippocamp', 'amygdal', 'fornix', 'chiasm', 'commissure', 'dura', 'arachnoid', 'pia mater',
           'falx', 'tentorium', 'putamen', 'globus pallidus', 'insula', 'colliculus', 'peduncle', 'pituitary stalk', 'choroid plexus', 'olive', 'vermis', 'lobule', 'flocculus', 'cuneus', 'precuneus'):
        if not has(n, 'lobule of auricle', 'tract of', 'iliotibial', 'biliary', 'nucleus pulposus', 'urinary tract', 'digestive tract'):
            return 'nervous'
    if has(n, 'muscle', 'musculus', ' m. ', 'muscul') or n.startswith('m. ') or has(n, 'head of', 'belly of', 'part of') and has(n, 'muscle'):
        return 'muscular'
    if has(n, 'eye', 'retina', 'lens', 'cornea', 'iris', 'sclera', 'choroid', 'vitreous', 'ciliary body', 'cochle', 'vestibule', 'semicircular', 'tympan',
           'auricle', 'ear ', 'external ear', 'lacrimal', 'eyelid', 'tarsus', 'conjunctiv', 'malleus', 'incus', 'stapes', 'auditory', 'helix', 'tragus', 'concha of auricle'):
        return 'sensory'
    if has(n, 'heart', 'atrium', 'atria', 'ventricle', 'valve', 'cusp', 'leaflet', 'papillary', 'chordae', 'myocard', 'pericard', 'trabecul', 'interatrial', 'interventricular septum'):
        return 'cardiac'
    if has(n, 'lung', 'bronch', 'trache', 'laryn', 'epiglott', 'vocal', 'nasal cavity', 'nasal concha', 'nasal septum', 'pleura', 'lingula', 'pulmonary segment', 'bronchopulmonary'):
        return 'respiratory'
    if has(n, 'kidney', 'ureter', 'urinary bladder', 'bladder', 'urethr', 'renal'): return 'urinary'
    if has(n, 'testis', 'prostat', 'penis', 'ovar', 'uter', 'vagin', 'epididym', 'deferen', 'seminal', 'scrot', 'spermatic', 'glans', 'corpus cavernosum',
           'corpus spongiosum', 'bulbourethral', 'ejaculatory', 'vulva', 'clitor', 'labium majus', 'labium minus'): return 'reproductive'
    if has(n, 'thyroid gland', 'parathyroid', 'adrenal', 'suprarenal', 'pituitary', 'hypophys', 'pineal', 'lobe of thyroid', 'isthmus of thyroid', 'pancreatic islet'): return 'endocrine'
    if has(n, 'skin', 'hair', 'nail', 'eyebrow', 'eyelash', 'region', 'umbilicus', 'fossa', 'triangle', 'groove'):
        return 'integumentary'
    if has(n, 'stomach', 'esophag', 'oesophag', 'duoden', 'jejun', 'ileum', 'ileal', 'colon', 'cecum', 'caecum', 'rectum', 'anal canal', 'appendix', 'liver', 'hepat',
           'gallbladder', 'bile', 'biliary', 'cystic duct', 'pancrea', 'tongue', 'tooth', 'teeth', 'incisor', 'canine', 'molar', 'premolar', 'gingiva', 'palate', 'uvula',
           'pharynx', 'pharyn', 'salivary', 'parotid', 'submandibular gland', 'sublingual', 'mesenter', 'omentum', 'mesocolon', 'taenia', 'peritone', 'lip'):
        return 'digestive'
    if has(n, 'bone', 'vertebra', 'rib', 'sternum', 'skull', 'cranium', 'mandible', 'maxilla', 'phalanx', 'carpal', 'metacarp', 'tarsal', 'metatars', 'patella',
           'femur', 'tibia', 'fibula', 'humerus', 'radius', 'ulna', 'clavicle', 'scapula', 'sacrum', 'coccyx', 'pelvis', 'hip bone', 'ilium', 'ischium', 'pubis',
           'calcaneus', 'talus', 'scaphoid', 'lunate', 'triquetr', 'pisiform', 'trapezi', 'capitate', 'hamate', 'cuboid', 'navicular', 'cuneiform', 'hyoid',
           'atlas', 'axis', 'vomer', 'ethmoid', 'sphenoid', 'occipital bone', 'parietal bone', 'frontal bone', 'temporal bone', 'zygomatic', 'sesamoid', 'manubrium', 'xiphoid'):
        return 'skeletal'
    # fall back to the group the object sits in (e.g. "Muscular System" folder)
    p = ' / '.join(path).lower()
    for s, words in GROUP_HINTS:
        if has(p, *words): return s
    return None

# ------------------------------------------------------------------ orientation
AX = np.eye(3)
HEAD_WORDS = ('skull', 'cranium', 'frontal bone', 'parietal bone', 'occipital bone', 'mandible', 'brain', 'cerebrum', 'head')
FOOT_WORDS = ('calcaneus', 'talus', 'metatarsal', 'phalanx of foot', 'toe', 'foot', 'hallux', 'hallucis')
TOE_WORDS = ('metatarsal', 'toe', 'phalanx of foot', 'phalanges of foot', 'hallu')
HEEL_WORDS = ('calcaneus', 'heel')
FRONT_WORDS = ('sternum', 'nasal bone', 'mandible', 'patella', 'rectus abdominis', 'manubrium')
BACK_WORDS = ('vertebra', 'sacrum', 'scapula', 'occipital bone', 'calcaneus', 'spinal cord')

def centroid(meshes, words):
    pts = [m.V.mean(0) for m in meshes if has(m.name.lower(), *words)]
    return np.mean(pts, 0) if pts else None

def orient(meshes, up=None, front=None, log=print):
    """Return a 3x3 matrix R (rows = new X, Y, Z in old coordinates)."""
    allV = np.vstack([m.V[:: max(1, len(m.V) // 400)] for m in meshes])
    ext = allV.max(0) - allV.min(0)
    def parse(s):
        sgn = -1 if s.startswith('-') else 1
        return sgn * AX['xyz'.index(s[-1])]
    if up: U = parse(up); log(f'  up axis: {up} (given)')
    else:
        a = int(np.argmax(ext)); U = AX[a].copy()
        h, f = centroid(meshes, HEAD_WORDS), centroid(meshes, FOOT_WORDS)
        if h is not None and f is not None:
            if (h - f)[a] < 0: U = -U
            how = 'head/foot names'
        else:   # the head end is narrower than the two legs
            lo, hi = allV[:, a].min(), allV[:, a].max(); L = hi - lo
            def spread(t0, t1):
                s = allV[(allV[:, a] > lo + t0 * L) & (allV[:, a] < lo + t1 * L)]
                o = [i for i in range(3) if i != a]
                return np.ptp(s[:, o[0]]) * np.ptp(s[:, o[1]]) if len(s) else 0
            if spread(0.85, 0.95) > spread(0.05, 0.15): U = -U
            how = 'body shape'
        log(f'  up axis: {"+-"[int(U.sum() < 0)]}{"xyz"[a]} ({how})')
    if front: F = parse(front); log(f'  front: {front} (given)')
    else:
        F, how = None, ''
        t, h = centroid(meshes, TOE_WORDS), centroid(meshes, HEEL_WORDS)
        if t is not None and h is not None:
            d = t - h; d -= d.dot(U) * U
            if np.linalg.norm(d) > 1e-9: F, how = d, 'toes in front of heels'
        if F is None:
            fr, bk = centroid(meshes, FRONT_WORDS), centroid(meshes, BACK_WORDS)
            if fr is not None and bk is not None:
                d = fr - bk; d -= d.dot(U) * U
                if np.linalg.norm(d) > 1e-9: F, how = d, 'sternum in front of spine'
        if F is None:   # toes stick out forward from the ankles
            hgt = allV @ U; lo = hgt.min(); L = np.ptp(hgt)
            sole = allV[hgt < lo + 0.025 * L]; ankle = allV[(hgt > lo + 0.05 * L) & (hgt < lo + 0.09 * L)]
            d = sole.mean(0) - ankle.mean(0); d -= d.dot(U) * U; F, how = d, 'foot shape'
        k = int(np.argmax(np.abs(F))); F = np.sign(F[k]) * AX[k]          # snap to the nearest axis
        log(f'  front: {"+-"[int(F.sum() < 0)]}{"xyz"[k]} ({how})')
    if abs(U.dot(F)) > 0.5: raise SystemExit('up and front axes are the same — pass --up and --front explicitly')
    X = np.cross(U, F)
    return np.vstack([X, U, F])

def normalize(meshes, R, log=print):
    out = [meshio.Mesh(m.name, m.path, m.V @ R.T, m.T) for m in meshes]
    allV = np.vstack([m.V for m in out])
    lo, hi = allV.min(0), allV.max(0)
    s = HEIGHT / (hi[1] - lo[1])
    c = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    log(f'  scale: {s:.6g} (model height {hi[1]-lo[1]:.4g} file units -> {HEIGHT} m)')
    if centroid(meshes, HEAD_WORDS) is None or centroid(meshes, FOOT_WORDS) is None:
        log('  WARNING: no skull or foot structures found — the model may not be a whole body, so the height scaling can be off')
    return [meshio.Mesh(m.name, m.path, (m.V - c) * s, m.T) for m in out]

ABDOMINAL = ('liver', 'hepat', 'gallbladder', 'stomach', 'spleen', 'pancrea', 'kidney', 'adrenal', 'suprarenal', 'duoden', 'colon', 'caud', 'falciform',
             'round ligament of liver', 'triangular ligament', 'coronary ligament', 'ligamentum venosum', 'portal', 'bile', 'biliary', 'cystic', 'omentum', 'celiac', 'coeliac')
def region(c, name=''):
    x, y, z = c; ax = abs(x)
    if 1.10 < y < 1.30 and ax < 0.16 and has(name.lower(), *ABDOMINAL): return 'abdomen'
    if y >= 1.50: return 'caput'
    if ax > 0.155 and 0.70 < y < 1.46:
        if y >= 1.33: return 'humerus'
        if y >= 1.11: return 'brachium'
        if y >= 0.895: return 'antebrachium'
        return 'manus'
    if y >= 1.435: return 'collum'
    if y < 0.80:
        if y >= 0.45: return 'femur'
        if y >= 0.065: return 'crus'
        return 'pes'
    if ax > 0.12 and y >= 1.33: return 'humerus'
    if z < -0.06 and y >= 0.95: return 'dorsum'
    if y >= 1.17: return 'thorax'
    if y >= 0.98: return 'abdomen'
    return 'pelvis'

# ------------------------------------------------------------------ simplification
def simplify_to_budget(meshes, budget, log=print):
    total = sum(len(m.T) for m in meshes)
    if total <= budget:
        log(f'  {total:,} triangles — within budget, no simplification'); return meshes
    ratio = budget / total
    out = []
    for m in meshes:
        n = len(m.T); target = max(min(n, 400), int(n * ratio))
        if n <= target * 1.15: out.append(m); continue
        diag = float(np.linalg.norm(np.ptp(m.V, 0))) or 1e-3
        cell = diag / max(8.0, np.sqrt(target) * 1.1)
        best = (m.V, m.T)
        for _ in range(5):
            r = decim.cluster(m.V, m.T, cell)
            if r is None or len(r[1]) < 8: cell *= 0.6; continue
            best = r; got = len(r[1])
            if got > target * 1.3: cell *= np.sqrt(got / target)
            elif got < target * 0.6: cell *= np.sqrt(got / target)
            else: break
        out.append(meshio.Mesh(m.name, m.path, best[0].astype(np.float64), best[1].astype(np.int64)))
    log(f'  simplified {total:,} -> {sum(len(m.T) for m in out):,} triangles (budget {budget:,})')
    return out

# ------------------------------------------------------------------ packing
def pack(items, out_dir, credits, chunk_bytes=3_000_000):
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if re.match(r'body-\d+\.(txt|bin)$', f) or f == 'parts.json': os.remove(os.path.join(out_dir, f))
    names, nidx, parts, chunks, cur = [], {}, [], [], bytearray()
    def pad(b):
        while len(b) % 4: b.append(0)
    for it in items:
        V, T = it['V'], it['T']
        N = decim.normals(V, T)
        b0, b1 = V.min(0), V.max(0); ext = np.maximum(b1 - b0, 1e-6)
        Q = np.rint((V - b0) / ext * 65535).astype('<u2'); NN = np.clip(np.rint(N * 127), -127, 127).astype('i1')
        vc, ic = len(V), T.size; big = vc > 65535
        I = T.astype('<u4' if big else '<u2').ravel()
        if len(cur) > chunk_bytes: chunks.append(cur); cur = bytearray()
        po = len(cur); cur += Q.tobytes(); pad(cur)
        no = len(cur); cur += NN.tobytes(); pad(cur)
        io = len(cur); cur += I.tobytes(); pad(cur)
        k = (it['en'], it['la'], it['cs'], 1)
        if k not in nidx: nidx[k] = len(names); names.append(list(k))
        c = (b0 + b1) / 2
        parts.append([it['en'] + {0: '', 1: ' (right)', 2: ' (left)'}[it['side']], nidx[k], it['side'], SYS.index(it['sys']), len(chunks), po, no, io,
                      vc, ic, int(big), REG.index(region(c, it['en'])), *[round(float(v), 4) for v in c], round(float((b1 - b0).max()), 4),
                      *[round(float(v), 6) for v in b0], *[round(float(v), 6) for v in b1], 0])
    chunks.append(cur)
    total = 0
    for i, ch in enumerate(chunks):
        g = gzip.compress(bytes(ch), 9); total += len(g)
        open(os.path.join(out_dir, f'body-{i}.txt'), 'w').write(base64.b64encode(g).decode())
    json.dump({'sys': SYS, 'reg': REG, 'names': names, 'parts': parts, 'chunks': len(chunks), 'fmt': 2, 'credits': credits,
               'built': time.strftime('%Y-%m-%d')},
              open(os.path.join(out_dir, 'parts.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    write_stats(out_dir, parts, total, credits)
    return len(chunks), total

def write_stats(out_dir, parts, size, credits=None):
    used = sorted({p[3] for p in parts}); regs = sorted({p[11] for p in parts})
    json.dump({'structures': len(parts), 'systems': len(used), 'regions': len(regs), 'languages': 3,
               'megabytes': round(size / 1e6, 1), 'built': time.strftime('%Y-%m-%d'), 'credits': (credits or {}).get('cs', '')},
              open(os.path.join(out_dir, 'stats.json'), 'w', encoding='utf-8'))

def preview(items, path):
    try:
        import render
    except ImportError:
        return
    col = {'skeletal': (225, 215, 190), 'muscular': (182, 70, 62), 'respiratory': (227, 154, 154), 'digestive': (214, 137, 95), 'cardiac': (160, 58, 64),
           'arterial': (210, 42, 42), 'venous': (58, 99, 198), 'nervous': (226, 190, 58)}
    def pick(systems): return [(it['V'], it['T'], col[it['sys']], 1) for it in items if it['sys'] in systems]
    a = render.raster(pick({'skeletal', 'respiratory', 'digestive', 'cardiac'}), 'front', ((-0.4, -0.02), (0.4, 1.76)), 360)
    b = render.raster(pick({'skeletal', 'respiratory', 'digestive', 'cardiac'}), 'side', ((-0.4, -0.02), (0.4, 1.76)), 360)
    c = render.raster(pick({'muscular', 'skeletal'}), 'front', ((-0.4, -0.02), (0.4, 1.76)), 360)
    render.png(path, np.concatenate([a, b, c], 1))

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='FBX (binary), GLB or OBJ files, or folders with them')
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'atlas', 'data'), help='output folder (default atlas/data)')
    ap.add_argument('--names', action='append', default=[], help='extra CSV with columns en;la;cs[;system][;source_name] (overrides the built-in dictionary)')
    ap.add_argument('--credits', help='JSON with the model credits shown in the atlas (see tools/credits.example.json)')
    ap.add_argument('--budget', type=int, default=4_000_000, help='max triangles in the whole body (default 4,000,000)')
    ap.add_argument('--up', help='force the up axis, e.g. +y, +z, -z')
    ap.add_argument('--front', help='force the facing direction, e.g. +z, -y')
    ap.add_argument('--skip', default=r'^(cross section|label|text|camera|light|armature|bone_|ik_|ctrl)', help='regex of object names to ignore')
    ap.add_argument('--strip', default='', help='regex removed from every object name first, e.g. a vendor prefix like "^VH_M_"')
    ap.add_argument('--hide-by-default', default='integumentary', help='comma list of systems hidden when the atlas opens (stored in credits.defaultHidden)')
    ap.add_argument('--report', default=os.path.join(HERE, '..', 'report'), help='folder for the report, missing names and preview image')
    a = ap.parse_args()
    os.makedirs(a.report, exist_ok=True)
    log_lines = []
    def log(s=''): print(s); log_lines.append(s)

    log('1/6 reading model'); meshes = meshio.read_inputs(a.inputs)
    skip = re.compile(a.skip, re.I)
    meshes = [m for m in meshes if len(m.T) >= 4 and not skip.search(m.name) and np.ptp(m.V, 0).max() > 0]
    if not meshes: raise SystemExit('no meshes found')
    log(f'  {len(meshes)} objects, {sum(len(m.T) for m in meshes):,} triangles')

    log('2/6 orientation and scale'); R = orient(meshes, a.up, a.front, log); meshes = normalize(meshes, R, log)

    log('3/6 names, sides, systems')
    names = Names([os.path.join(HERE, 'names_dictionary.csv')] + a.names)
    items, missing, unsorted = [], collections.OrderedDict(), collections.Counter()
    strip = re.compile(a.strip, re.I) if a.strip else None
    for m in meshes:
        side, base = split_side(strip.sub('', m.name) if strip else m.name)
        en = tidy(base)
        if not en: continue
        la, cs = names.lookup(base.strip(), en)
        sysk = names.system(base.strip(), en) or classify(en, m.path)
        if not sysk: unsorted[en] += 1; sysk = 'connective'
        if not (la and cs): missing.setdefault(en, (la, cs, sysk, m.name))
        items.append(dict(raw=m.name, en=en, la=la, cs=cs, side=side, sys=sysk, V=m.V, T=m.T))
    # side from position when the name does not say it, but a mirror twin exists
    groups = collections.defaultdict(list)
    for it in items: groups[it['en']].append(it)
    for en, g in groups.items():
        if len(g) >= 2 and all(it['side'] == 0 for it in g):
            for it in g:
                x = it['V'][:, 0].mean()
                if abs(x) > 0.01: it['side'] = 1 if x < 0 else 2
    # sanity check: body's right must be on -X; flip the whole model if the names say otherwise
    rx = [it['V'][:, 0].mean() for it in items if it['side'] == 1]; lx = [it['V'][:, 0].mean() for it in items if it['side'] == 2]
    if rx and lx and np.median(rx) > np.median(lx):
        log('  names say left/right are swapped — mirroring the model (file uses a left-handed axis system)')
        for it in items:
            it['V'] = it['V'] * np.array([-1, 1, 1]); it['T'] = it['T'][:, [0, 2, 1]]
    nl = sum(1 for it in items if it['la']); nc = sum(1 for it in items if it['cs'])
    log(f'  {len(items)} structures; Latin {nl}/{len(items)}, Czech {nc}/{len(items)}; unsorted {sum(unsorted.values())}')
    for s, n in collections.Counter(it['sys'] for it in items).most_common(): log(f'    {s:14} {n}')

    log('4/6 simplification')
    simp = simplify_to_budget([meshio.Mesh(it['en'], [], it['V'], it['T']) for it in items], a.budget, log)
    for it, m in zip(items, simp): it['V'], it['T'] = m.V, m.T
    for it in items:      # names: fall back so the atlas never shows an empty label
        it['la'] = it['la'] or it['en']; it['cs'] = it['cs'] or ''

    log('5/6 writing atlas data')
    credits = json.load(open(a.credits, encoding='utf-8')) if a.credits else {}
    credits.setdefault('defaultHidden', [s for s in a.hide_by_default.split(',') if s])
    n, size = pack(items, a.out, credits)
    log(f'  {a.out}: parts.json + {n} blocks, {size/1e6:.1f} MB compressed')

    log('6/6 report')
    with open(os.path.join(a.report, 'missing_names.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';'); w.writerow(['en', 'la', 'cs', 'system', 'source_name'])
        for en, (la, cs, s, raw) in missing.items(): w.writerow([en, la, cs, s, raw])
    regs = collections.Counter(region((it['V'].min(0) + it['V'].max(0)) / 2, it['en']) for it in items)
    log('  regions: ' + ', '.join(f'{k} {regs[k]}' for k in REG))
    log(f'  missing names: {len(missing)} -> report/missing_names.csv')
    preview(items, os.path.join(a.report, 'preview.png'))
    open(os.path.join(a.report, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(log_lines) + '\n')

if __name__ == '__main__':
    main()
