"""Name rules: systematic series (vertebrae, ribs, phalanges, teeth, segments...) to Latin and Czech.
rules(en)    -> (latin, czech) or None
cs_rule(en)  -> czech or None
"""
import re
ORD = ['first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth','eleventh','twelfth']
ROM = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII']
def o(w): return ORD.index(w.lower())

SEG_LA = {'anterior inferior':'anterioris inferioris','anterior superior':'anterioris superioris','lateral inferior':'lateralis inferioris',
          'lateral superior':'lateralis superioris','medial inferior':'medialis inferioris','medial superior':'medialis superioris',
          'posterior inferior':'posterioris inferioris','posterior superior':'posterioris superioris','caudate lobe':'lobi caudati'}
SEG_CS = {'anterior inferior':'předního dolního','anterior superior':'předního horního','lateral inferior':'zevního dolního',
          'lateral superior':'zevního horního','medial inferior':'vnitřního dolního','medial superior':'vnitřního horního',
          'posterior inferior':'zadního dolního','posterior superior':'zadního horního','caudate lobe':'ocasatého laloku'}
FING_LA = {'thumb':'pollicis','index finger':'digiti II manus','middle finger':'digiti III manus','ring finger':'digiti IV manus',
           'little finger':'digiti minimi manus','big toe':'hallucis','second toe':'digiti II pedis','third toe':'digiti III pedis',
           'fourth toe':'digiti IV pedis','little toe':'digiti minimi pedis'}
FING_CS = {'thumb':'palce ruky','index finger':'ukazováku','middle finger':'prostředníku','ring finger':'prsteníku',
           'little finger':'malíku ruky','big toe':'palce nohy','second toe':'2. prstu nohy','third toe':'3. prstu nohy',
           'fourth toe':'4. prstu nohy','little toe':'malíku nohy'}
BR_LA = {'anterior basal':'basalis anterior','anterior':'anterior','apical':'apicalis','lateral basal':'basalis lateralis','lateral':'lateralis',
         'medial basal':'basalis medialis','medial':'medialis','posterior basal':'basalis posterior','posterior':'posterior','superior':'superior'}
BR_CS = {'anterior basal':'Přední bazální','anterior':'Přední','apical':'Apikální','lateral basal':'Zevní bazální','lateral':'Zevní',
         'medial basal':'Vnitřní bazální','medial':'Vnitřní','posterior basal':'Zadní bazální','posterior':'Zadní','superior':'Horní'}
VREG = {'cervical':('cervicalis','Krční','C'),'thoracic':('thoracica','Hrudní','Th'),'lumbar':('lumbalis','Bederní','L')}
ORD_CS_F = ['1.','2.','3.','4.']

def rules(n):
    m = re.match(r'^(\w+) (cervical|thoracic|lumbar) vertebra$', n)
    if m:
        i = o(m[1]); la, cs, c = VREG[m[2]]
        return (f'Vertebra {la} {ROM[i]} ({c}{i+1})', f'{cs} obratel {c}{i+1}')
    m = re.match(r'^Intervertebral disk of (?:(\w+) (cervical|thoracic|lumbar) vertebra|axis)$', n)
    if m:
        code = 'C2' if m[1] is None else VREG[m[2]][2] + str(o(m[1]) + 1)
        return (f'Discus intervertebralis ({code})', f'Meziobratlová ploténka ({code})')
    m = re.match(r'^(\w+) rib$', n)
    if m: i = o(m[1]); return (f'Costa {ROM[i]}', f'{i+1}. žebro')
    m = re.match(r'^(\w+) costal cartilage$', n)
    if m: i = o(m[1]); return (f'Cartilago costalis {ROM[i]}', f'Žeberní chrupavka {i+1}. žebra')
    m = re.match(r'^(\w+) metacarpal bone$', n)
    if m: i = o(m[1]); return (f'Os metacarpi {ROM[i]}', f'{i+1}. záprstní kost')
    m = re.match(r'^(\w+) metatarsal bone$', n)
    if m: i = o(m[1]); return (f'Os metatarsi {ROM[i]}', f'{i+1}. nártní kost')
    m = re.match(r'^(Distal|Middle|Proximal) phalanx of (.+)$', n)
    if m and m[2] in FING_LA:
        la = {'Distal':'distalis','Middle':'media','Proximal':'proximalis'}[m[1]]
        cs = {'Distal':'Koncový','Middle':'Střední','Proximal':'Základní'}[m[1]]
        return (f'Phalanx {la} {FING_LA[m[2]]}', f'{cs} článek {FING_CS[m[2]]}')
    m = re.match(r'^(Upper|Lower) (?:(central|lateral) secondary incisor|secondary canine|(first|second) secondary (premolar|molar)) tooth$', n)
    if m:
        pos_la = 'superior' if m[1] == 'Upper' else 'inferior'; pos_cs = 'Horní' if m[1] == 'Upper' else 'Dolní'
        if m[2]: return (f'Dens incisivus {"medialis" if m[2]=="central" else "lateralis"} {pos_la}',
                         f'{pos_cs} {"střední" if m[2]=="central" else "postranní"} řezák')
        if m[3] is None: return (f'Dens caninus {pos_la}', f'{pos_cs} špičák')
        k = 0 if m[3] == 'first' else 1
        if m[4] == 'premolar': return (f'Dens premolaris {ROM[k]} {pos_la}', f'{pos_cs} {["první","druhý"][k]} třenový zub')
        return (f'Dens molaris {ROM[k]} {pos_la}', f'{pos_cs} {["první","druhá"][k]} stolička')
    m = re.match(r'^(\w+) lumbrical of foot$', n)
    if m: i = o(m[1]); return (f'M. lumbricalis {ROM[i]} pedis', f'{i+1}. červovitý sval nohy')
    m = re.match(r'^(\w+) plantar interosseous of foot$', n)
    if m: i = o(m[1]); return (f'M. interosseus plantaris {ROM[i]}', f'{i+1}. chodidlový mezikostní sval')
    m = re.match(r'^(.+) segmental bronchial tree$', n)
    if m and m[1].lower() in BR_LA:
        k = m[1].lower(); return (f'Bronchus segmentalis {BR_LA[k]}', f'{BR_CS[k]} segmentová průduška')
    m = re.match(r'^(.+) segmental hepatic artery$', n)
    if m and m[1].lower() in SEG_LA:
        k = m[1].lower(); return (f'A. segmenti {SEG_LA[k]} hepatis', f'Tepna {SEG_CS[k]} jaterního segmentu')
    m = re.match(r'^(.+) segmental branch of portal vein$', n)
    if m and m[1].lower() in SEG_LA:
        k = m[1].lower(); return (f'R. segmenti {SEG_LA[k]} v. portae', f'Větev vrátnicové žíly k segmentu {SEG_CS[k]}')
    m = re.match(r'^(.+) segmental tributary of (middle )?hepatic vein$', n)
    if m and m[1].lower() in SEG_LA:
        k = m[1].lower(); mid = m[2] is not None
        return (f'Tributarium segmenti {SEG_LA[k]} v. hepaticae{" intermediae" if mid else ""}',
                f'Přítok {SEG_CS[k]} segmentu do {"střední " if mid else ""}jaterní žíly')
    m = re.match(r'^(.+) tributary of hepatic biliary tree$', n)
    if m and m[1].lower() in SEG_LA:
        k = m[1].lower(); return (f'Ductus bilifer segmenti {SEG_LA[k]}', f'Žlučový vývod {SEG_CS[k]} segmentu jater')
    m = re.match(r'^Hepatovenous segment ([IVX]+)$', n)
    if m: return (f'Segmentum hepatis {m[1]} (venae)', f'Žilní drenáž jaterního segmentu {m[1]}')
    m = re.match(r'^(\w+) anterior branch of anterior interventricular branch of coronary artery$', n)
    if m: i = o(m[1]); return (f'R. anterior {ROM[i]} rami interventricularis anterioris', f'{i+1}. přední větev přední mezikomorové větve')
    m = re.match(r'^(\w+) anterior ventricular branch of coronary artery$', n)
    if m: i = o(m[1]); return (f'R. ventricularis anterior {ROM[i]} a. coronariae', f'{i+1}. přední komorová větev věnčité tepny')
    m = re.match(r'^(\w+) posterior ventricular branch of coronary artery$', n)
    if m: i = o(m[1]); return (f'R. ventricularis posterior {ROM[i]} a. coronariae', f'{i+1}. zadní komorová větev věnčité tepny')
    m = re.match(r'^(\w+) septal branch of posterior interventricular artery$', n)
    if m: i = o(m[1]); return (f'R. septalis {ROM[i]} rami interventricularis posterioris', f'{i+1}. septální větev zadní mezikomorové větve')
    m = re.match(r'^(\w+) common palmar digital artery$', n)
    if m: i = o(m[1]); return (f'A. digitalis palmaris communis {ROM[i]}', f'{i+1}. společná dlaňová prstová tepna')
    m = re.match(r'^(\w+) posterior intercostal artery$', n)
    if m: i = o(m[1]); return (f'A. intercostalis posterior {ROM[i]}', f'{i+1}. zadní mezižeberní tepna')
    m = re.match(r'^(Lateral|Medial) proper palmar digital artery of (.+)$', n)
    if m and m[2] in FING_LA:
        la = 'lateralis' if m[1] == 'Lateral' else 'medialis'; cs = 'Zevní' if m[1] == 'Lateral' else 'Vnitřní'
        return (f'A. digitalis palmaris propria {la} {FING_LA[m[2]].replace(" manus","")}', f'{cs} vlastní dlaňová prstová tepna {FING_CS[m[2]]}')
    m = re.match(r'^Proper palmar digital vein of (.+)$', n)
    if m and m[1] in FING_LA:
        return (f'Vv. digitales palmares propriae {FING_LA[m[1]].replace(" manus","")}', f'Vlastní dlaňové prstové žíly {FING_CS[m[1]]}')
    return None


# ---- Czech-only rules ----
ORD_CS = ['first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth','eleventh','twelfth']
def o_cs(w): return ORD_CS.index(w.lower())
SEGL = {'anterior basal':'přední bazální','anteromedial basal':'předně-vnitřní bazální','anterior':'přední','apical':'apikální',
        'apicoposterior':'apikálně-zadní','lateral basal':'zevní bazální','lateral':'zevní','medial basal':'vnitřní bazální',
        'medial':'vnitřní','posterior basal':'zadní bazální','posterior':'zadní','superior':'horní','superior lingular':'horní lingulární',
        'inferior lingular':'dolní lingulární'}
FING = {'hand': ['palce ruky','ukazováku','prostředníku','prsteníku','malíku ruky'],
        'foot': ['palce nohy','2. prstu nohy','3. prstu nohy','4. prstu nohy','malíku nohy']}
def cs_rule(n):
    s = n.strip()
    m = re.match(r'^(Distal|Middle|Proximal) phalanx of (\w+) finger of (hand|foot)$', s)
    if m: return {'Distal':'Koncový','Middle':'Střední','Proximal':'Základní'}[m[1]] + ' článek ' + FING[m[3]][o_cs(m[2])]
    m = re.match(r'^Costal cartilage of (\w+) rib$', s)
    if m: return f'Žeberní chrupavka {o_cs(m[1])+1}. žebra'
    m = re.match(r'^(\w+) rib$', s)
    if m and m[1].lower() in ORD_CS: return f'{o_cs(m[1])+1}. žebro'
    m = re.match(r'^(\w+) metacarpal bone$', s)
    if m and m[1].lower() in ORD_CS: return f'{o_cs(m[1])+1}. záprstní kost'
    m = re.match(r'^(\w+) metatarsal bone$', s)
    if m and m[1].lower() in ORD_CS: return f'{o_cs(m[1])+1}. nártní kost'
    m = re.match(r'^(.+?) segmental (artery|bronchus) of (left|right) lung(?: \((B[IVX+B]+)\))?$', s)
    if m and m[1].lower() in SEGL:
        lung = 'levé' if m[3] == 'left' else 'pravé'
        what = 'segmentová tepna' if m[2] == 'artery' else 'segmentová průduška'
        b = f' ({m[4]})' if m[4] else ''
        return f'{SEGL[m[1].lower()].capitalize()} {what} {lung} plíce{b}'
    m = re.match(r'^(.+?) (?:segmental )?vein of (left|right) lung$', s)
    if m and m[1].lower() in SEGL:
        return f'{SEGL[m[1].lower()].capitalize()} žíla {"levé" if m[2]=="left" else "pravé"} plíce'
    m = re.match(r'^(.+?) lobe of (left|right) lung$', s)
    if m and m[1].lower() in ('superior','middle','inferior'):
        lob = {'superior': 'Horní', 'middle': 'Střední', 'inferior': 'Dolní'}[m[1].lower()]
        return lob + ' lalok ' + ('levé' if m[2] == 'left' else 'pravé') + ' plíce'
    m = re.match(r'^Vertebra (C|T|L)(\d+)$', s)
    if m: return {'C':'Krční','T':'Hrudní','L':'Bederní'}[m[1]] + f' obratel {"Th" if m[1]=="T" else m[1]}{m[2]}'
    m = re.match(r'^(\w+) posterior intercostal artery$', s)
    if m and m[1].lower() in ORD_CS: return f'{o_cs(m[1])+1}. zadní mezižeberní tepna'
    return None

_old = cs_rule
def cs_rule(n):
    r = _old(n)
    if r: return r
    m = re.match(r'^Intervertebral disc ([CTL]\d+)-([CTLS]\d+)$', n.strip())
    if m: return 'Meziobratlová ploténka ' + m[1].replace('T', 'Th') + '–' + m[2].replace('T', 'Th')
    return None

_old2 = cs_rule
def cs_rule(n):
    r = _old2(n)
    if r: return r
    m = re.match(r'^Nucleus pulposus ([CTL]\d+)-([CTLS]\d+)$', n.strip())
    if m: return 'Rosolovité jádro ploténky ' + m[1].replace('T', 'Th') + '–' + m[2].replace('T', 'Th')
    return None
