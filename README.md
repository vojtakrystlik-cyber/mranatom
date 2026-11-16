# Atlas lidského těla 3D – web

Statický web: nepotřebuje server s databází, stačí nahrát složku na hosting statických stránek.

```
index.html            úvodní stránka (nastavení e-mailu a odkazů: blok CONFIG na konci souboru)
LICENSES.html         licence a zdroje (při výměně modelu je nutné ji upravit)
favicon.svg
assets/               písma (IBM Plex, OFL), náhled atlasu, fonts.css
atlas/index.html      3D atlas (vygenerovaný z tools/viewer_src.html)
atlas/data/           data modelu: parts.json, body-N.txt, stats.json
atlas/vendor/         three.js (MIT), bez závislosti na cizím CDN
tools/                převodník modelu a slovník názvů
_headers              cache pro Netlify / Cloudflare Pages
```

## Zveřejnění

- **Netlify:** https://app.netlify.com/drop → přetáhnout celou složku. Vlastní doménu nastavíte v Domain settings.
- **Cloudflare Pages:** Create project → Upload assets → nahrát složku.
- **Vlastní hosting / Wedos / Forpsi:** nahrát obsah složky přes FTP do kořene webu.

Lokálně: `python -m http.server 8000` v této složce a otevřít http://localhost:8000 (dvojklik na index.html nefunguje, prohlížeč nedovolí načíst data z disku).

## Výměna modelu těla (až přijde licencovaný model)

1. Model uložte jako **FBX (binární)**, **GLB** nebo **OBJ**, klidně do více souborů (např. po soustavách).
2. Zkopírujte `tools/credits.example.json` jako `tools/credits.json` a vyplňte autora a licenci.
3. Spusťte (Python 3.9+, potřebuje numpy; pro zjednodušení sítí není potřeba nic dalšího):

   ```
   pip install numpy pillow
   python tools/build_model.py cesta/k/modelu.fbx --credits tools/credits.json
   ```

   Převodník sám zjistí orientaci, měřítko a strany, roztřídí struktury do soustav a oblastí a doplní latinské a české názvy ze slovníku. Výsledek zapíše do `atlas/data/` a do složky `report/`:
   - `report/report.txt` – co zjistil (osy, měřítko, počty),
   - `report/preview.png` – náhled zepředu, z boku a svaly – rychlá kontrola, že tělo stojí správně,
   - `report/missing_names.csv` – struktury bez latinského nebo českého názvu.

4. Doplňte chybějící názvy v `missing_names.csv` (sloupce `la`, `cs`, případně `system`), uložte ho např. jako `tools/names_custom.csv` a spusťte znovu s `--names tools/names_custom.csv`.
5. Upravte `LICENSES.html` podle nové licence a nahrajte web znovu.

Užitečné přepínače: `--budget 4000000` (max. trojúhelníků celého těla; menší = rychlejší načítání), `--up +z --front -y` (ruční orientace, kdyby automatika selhala), `--strip "^PREFIX_"` (odstraní předponu z názvů objektů), `--skip "regex"` (vynechá pomocné objekty).

## Úpravy atlasu

Zdroj atlasu je `tools/viewer_src.html`; po úpravě spusťte `python tools/make_viewer.py`, který vytvoří `atlas/index.html`.

## Licence

Současný model: BodyParts3D (CC BY 4.0) + HuBMAP HRA (CC BY 4.0) – komerční použití povoleno s uvedením autorů (je na stránce Licence a v atlasu). Slovník názvů v `tools/names_dictionary.csv` je vlastní práce. Nepoužívejte data ze Z-Anatomy (CC BY-SA), vynutila by stejnou licenci pro celý web.
