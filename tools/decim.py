import numpy as np
def normals(V,T):
    V=V.astype(np.float64); a,b,c=V[T[:,0]],V[T[:,1]],V[T[:,2]]; fn=np.cross(b-a,c-a)
    N=np.zeros_like(V)
    for k in range(3): np.add.at(N,T[:,k],fn)
    l=np.linalg.norm(N,axis=1,keepdims=True); l[l==0]=1; return (N/l)
def cluster(V,T,cell):
    N=normals(V,T)
    nb=(N>=0).astype(np.int64)                                     # 8 octant bins
    q=np.floor(V/cell).astype(np.int64)+(1<<19)
    key=((q[:,0]*(1<<20)+q[:,1])*(1<<20)+q[:,2])*27+nb[:,0]*9+nb[:,1]*3+nb[:,2]
    u,inv=np.unique(key,return_inverse=True)
    cnt=np.bincount(inv); NV=np.zeros((len(u),3))
    for k in range(3): NV[:,k]=np.bincount(inv,weights=V[:,k])/cnt
    NT=inv[T]
    ok=(NT[:,0]!=NT[:,1])&(NT[:,1]!=NT[:,2])&(NT[:,0]!=NT[:,2]); NT=NT[ok]
    if len(NT)==0: return None
    s=np.sort(NT,1); _,first=np.unique(s,axis=0,return_index=True); NT=NT[np.sort(first)]
    used=np.unique(NT); remap=-np.ones(len(NV),np.int64); remap[used]=np.arange(len(used))
    return NV[used].astype(np.float32),remap[NT].astype(np.int32)
def simplify(V,T,base,rel=1/40.,mn=0.04):
    diag=float(np.linalg.norm(V.max(0)-V.min(0))); cell=min(base,max(diag*rel,mn))
    r=cluster(V,T,cell)
    if r is None or len(r[1])<max(8,len(T)//50): return V,T
    return r
