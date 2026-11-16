import numpy as np, zlib, struct

def png(path, img):
    h, w, _ = img.shape
    raw = b''.join(b'\x00' + img[y].tobytes() for y in range(h))
    def ch(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw, 6)) + ch(b'IEND', b''))

def raster(meshes, view, box, W=700):
    """meshes: list of (V, T, rgb, alpha). view: 'front' (x,y, depth z) or 'side' (z,y, depth -x) or 'top'.
       Simple z-buffer with Lambert shading; alpha<1 blends over result."""
    (x0, y0), (x1, y1) = box
    H = int(W * (y1 - y0) / (x1 - x0))
    col = np.full((H, W, 3), 245.0); zb = np.full((H, W), -1e9)
    def proj(V):
        if view == 'front': u, v, d = V[:, 0], V[:, 1], V[:, 2]
        elif view == 'back': u, v, d = -V[:, 0], V[:, 1], -V[:, 2]
        else: u, v, d = V[:, 2], V[:, 1], -V[:, 0]
        return (u - x0) / (x1 - x0) * (W - 1), (y1 - v) / (y1 - y0) * (H - 1), d
    layers = []
    for V, T, rgb, a in meshes:
        u, v, d = proj(V)
        A, B, C = T[:, 0], T[:, 1], T[:, 2]
        n = np.cross(np.stack([u[B]-u[A], v[B]-v[A], d[B]-d[A]], 1), np.stack([u[C]-u[A], v[C]-v[A], d[C]-d[A]], 1))
        nz = np.abs(n[:, 2]) / (np.linalg.norm(n, axis=1) + 1e-12)
        shade = 0.35 + 0.65 * nz
        # rasterize triangles by sampling barycentric points (cheap, dense enough for preview)
        k = 6; ws = [(i / k, j / k) for i in range(k + 1) for j in range(k + 1 - i)]
        for wa, wb in ws:
            wc = 1 - wa - wb
            pu = (u[A]*wa + u[B]*wb + u[C]*wc).astype(int); pv = (v[A]*wa + v[B]*wb + v[C]*wc).astype(int)
            pd = d[A]*wa + d[B]*wb + d[C]*wc
            ok = (pu >= 0) & (pu < W) & (pv >= 0) & (pv < H)
            layers.append((pu[ok], pv[ok], pd[ok], shade[ok], np.array(rgb, float), a))
    # opaque first
    for pu, pv, pd, sh, rgb, a in layers:
        if a < 1: continue
        order = np.argsort(pd); pu, pv, pd, sh = pu[order], pv[order], pd[order], sh[order]
        m = pd > zb[pv, pu]; zb[pv[m], pu[m]] = pd[m]; col[pv[m], pu[m]] = rgb * sh[m, None]
    for pu, pv, pd, sh, rgb, a in layers:
        if a >= 1: continue
        tmp = np.zeros((H, W)); tmp[pv, pu] = 1
        col[tmp > 0] = col[tmp > 0] * (1 - a) + rgb * a
    return np.clip(col, 0, 255).astype(np.uint8)
