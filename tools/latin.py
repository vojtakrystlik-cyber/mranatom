"""Latin names: write out abbreviations and give each name its grammatical gender for the side word.

    expand('R. profundus a. femoralis')  -> 'Ramus profundus arteriae femoralis'
    gender('Musculus biceps brachii')    -> 'm'   (m, f, n; mp, fp, np for plural heads)
    with_side('Arteria radialis', 'f', 1) -> 'Arteria radialis dextra'

Abbreviations at the start of a name are nominative (M. = Musculus), lower-case ones inside a name
are genitive (m. = musculi), as in the Terminologia Anatomica.
"""
import re

NOM = {'M': 'Musculus', 'Mm': 'Musculi', 'A': 'Arteria', 'Aa': 'Arteriae', 'V': 'Vena', 'Vv': 'Venae',
       'N': 'Nervus', 'Nn': 'Nervi', 'R': 'Ramus', 'Rr': 'Rami', 'Lig': 'Ligamentum', 'Ligg': 'Ligamenta',
       'Gl': 'Glandula', 'Gll': 'Glandulae', 'Proc': 'Processus', 'Art': 'Articulatio', 'Artt': 'Articulationes',
       'Ln': 'Nodus lymphoideus', 'Lnn': 'Nodi lymphoidei', 'Tr': 'Truncus', 'Sut': 'Sutura', 'For': 'Foramen'}
GEN = {'m': 'musculi', 'mm': 'musculorum', 'a': 'arteriae', 'aa': 'arteriarum', 'v': 'venae', 'vv': 'venarum',
       'n': 'nervi', 'nn': 'nervorum', 'r': 'rami', 'rr': 'ramorum', 'lig': 'ligamenti', 'ligg': 'ligamentorum',
       'gl': 'glandulae', 'proc': 'processus', 'art': 'articulationis', 'tr': 'trunci', 'sut': 'suturae'}

def expand(la):
    if not la:
        return la
    def rep(m):
        w = m.group(1)
        start = m.start() == 0 or la[m.start() - 1] in '(,;'
        if w in NOM and (start or w[0].isupper()):
            return NOM[w]
        if w in GEN:
            return GEN[w]
        return m.group(0)
    return re.sub(r'(?<![\w.])([A-Za-z]{1,4})\.(?=\s|$|,|\))', rep, la)

# grammatical gender of the head noun (first word) of a Latin anatomical name
G = {}
for g, words in {
    'm': '''musculus nervus ramus discus ductus dens bronchus gyrus arcus truncus ventriculus paries tendo tarsus tractus
           colliculus lobus lacertus anulus canaliculus lacus saccus canalis aqueductus nucleus plexus fornix globus
           hippocampus hypothalamus pedunculus pons thalamus lobulus sinus conus oesophagus splen ren pulmo testis
           meniscus processus nodus tuberculus condylus epicondylus malleolus hamulus sulcus porus meatus funiculus
           ureter uterus? bulbus lemniscus recessus folliculus sphincter atrium? cortex? ductulus digitus pollex hallux
           cuneus calcaneus talus femur? humerus radius carpus metacarpus metatarsus angulus margo apex limbus''',
    'f': '''arteria vena pars phalanx vertebra costa glandula aorta valvula cavitas membrana commissura taenia gingiva
           camera choroidea corona cornea sclera zonula trochlea linea habenula insula capsula fossa lamina medulla
           substantia stria raphe vesica trachea lingua epiglottis junctio cartilago cuspis gaster hypophysis lens iris
           pubes epididymis glans cutis auris appendix mandibula maxilla clavicula scapula ulna tibia fibula patella
           articulatio sutura tonsilla tuba mamma prostata vagina vulva urethra plica papilla fascia bursa aponeurosis
           tunica pleura pericardium? ala spina crista tuberositas facies incisura concha orbita sella cisterna
           cauda radix vallecula uvula fovea lacuna ampulla flexura pyramis amygdala lunula''',
    'n': '''os ligamentum caput corpus segmentum tributarium brachium ganglion foramen septum tentorium cerebellum
           putamen tuber chiasma platysma diaphragma parenchyma labium supercilium retinaculum mesencephalon pancreas
           rete rectum duodenum colon cor hepar jejunum ileum cecum caecum omentum mesenterium peritoneum pericardium
           sternum sacrum coccyx? cranium frontale occipitale sphenoidale ethmoidale atrium cortex? velum frenulum
           infundibulum claustrum tegmentum operculum crus collum dorsum'''}.items():
    for w in words.split():
        if not w.endswith('?'):
            G[w] = g
G.update({'atlas': 'm', 'axis': 'm', 'vomer': 'm', 'coccyx': 'n', 'cortex': 'm', 'uterus': 'm', 'femur': 'n', 'humerus': 'm', 'crus': 'n'})
PLURAL = {'musculi': 'mp', 'nervi': 'mp', 'rami': 'mp', 'gyri': 'mp', 'capilli': 'mp', 'nodi': 'mp', 'menisci': 'mp', 'dentes': 'mp',
          'arteriae': 'fp', 'venae': 'fp', 'glandulae': 'fp', 'costae': 'fp', 'vertebrae': 'fp', 'articulationes': 'fp',
          'partes': 'fp', 'ossa': 'np', 'ligamenta': 'np', 'segmenta': 'np', 'ganglia': 'np', 'capita': 'np'}

def gender(la):
    if not la:
        return 'm'
    w = expand(la).split()[0].lower()
    if w in PLURAL: return PLURAL[w]
    if w in G: return G[w]
    if w.endswith(('us', 'er')): return 'm'
    if w.endswith(('um', 'on', 'en', 'ma', 'al', 'ar')): return 'n'
    if w.endswith(('a', 'io', 'is', 'x')): return 'f'
    return 'm'

SIDE = {'m': ('dexter', 'sinister'), 'f': ('dextra', 'sinistra'), 'n': ('dextrum', 'sinistrum'),
        'mp': ('dextri', 'sinistri'), 'fp': ('dextrae', 'sinistrae'), 'np': ('dextra', 'sinistra')}

def with_side(la, g, side):
    """side: 1 = right, 2 = left (atlas convention)."""
    if side not in (1, 2):
        return la
    return f'{la} {SIDE.get(g, SIDE["m"])[side - 1]}'

if __name__ == '__main__':
    for s in ['R. profundus a. femoralis', 'Caput longum m. bicipitis brachii', 'Vv. digitales palmares propriae',
              'M. obliquus externus abdominis', 'Nn. ciliares breves', 'Pars insularis a. cerebri mediae', 'Os metatarsi I']:
        e = expand(s); print(f'{s:40} -> {e}  [{gender(s)}] -> {with_side(e, gender(s), 1)}')
