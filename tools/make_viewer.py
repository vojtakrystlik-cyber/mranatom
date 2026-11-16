"""Builds atlas/index.html (self-hosted site) and, optionally, the claude.ai preview variant
from the viewer source in tools/viewer_src.html.

    python tools/make_viewer.py                # writes atlas/index.html
    python tools/make_viewer.py --preview OUT  # writes the CDN variant used for the online preview
"""
import argparse, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'viewer_src.html')

HEAD = '''<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="Interaktivní 3D pitevní atlas lidského těla s latinskými, českými a anglickými názvy.">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<style>body{margin:0;font-size:14px}[hidden]{display:none!important}img{max-width:100%}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>
'''

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--preview')
    a = ap.parse_args()
    s = open(SRC, encoding='utf-8').read()
    if a.preview:
        out = s.replace('vendor/three.min.js', 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js') \
               .replace('vendor/OrbitControls.js', 'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js') \
               .replace('<a class="btn" id="homeLink" href="../">', '<a class="btn" id="homeLink" href="index.html">')
        open(a.preview, 'w', encoding='utf-8').write(out)
        print('wrote', a.preview)
    else:
        title, rest = s.split('\n', 1)
        rest = rest.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
        rest = re.sub(r'<link rel="preconnect"[^>]*>\n', '', rest)
        rest = re.sub(r'<link rel="stylesheet" href="https://fonts.googleapis.com[^>]*>', '<link rel="stylesheet" href="../assets/fonts.css">', rest)
        out = HEAD + title + '\n' + rest.replace('<div class="app">', '</head>\n<body>\n<div class="app">', 1) + '\n</body>\n</html>\n'
        path = os.path.join(HERE, '..', 'atlas', 'index.html')
        open(path, 'w', encoding='utf-8').write(out)
        print('wrote', os.path.normpath(path))

if __name__ == '__main__':
    main()
