# Busca fotos candidatas de cada animal y monta una hoja de contacto por animal
# para revisarlas a mano antes de usarlas en la app de Olivia.
import json, os, re, time, io, requests
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

H = {'User-Agent': 'LosAnimalesDeOlivia/1.0 (github.com/diegogerig4/sonidos-animales)'}
API = 'https://api.inaturalist.org/v1'
if os.path.exists('tools/data.json'):
    data = json.load(open('tools/data.json', encoding='utf-8'))
else:
    data = json.loads(re.search(r'const ANIMALS = (\[.*?\]);\n', open('index.html', encoding='utf-8').read()).group(1))
os.makedirs('review', exist_ok=True)
json.dump(data, open('review/data.json', 'w'), ensure_ascii=False)

def getj(url, params=None):
    for i in range(6):
        try:
            r = requests.get(url, params=params, headers=H, timeout=30)
            if r.status_code == 429: time.sleep(10 * (i + 1)); continue
            r.raise_for_status(); time.sleep(1.0); return r.json()
        except Exception:
            if i == 5: raise
            time.sleep(4 * (i + 1))

def ph(p, src):
    u = p.get('url') or p.get('square_url') or ''
    if not u or not p.get('license_code'): return None
    base = u.replace('/square.', '/medium.').replace('/small.', '/medium.')
    return {'id': p['id'], 'medium': base, 'large': base.replace('/medium.', '/large.'),
            'by': p.get('attribution', ''), 'lic': p.get('license_code'), 'src': src,
            'w': (p.get('original_dimensions') or {}).get('width'), 'h': (p.get('original_dimensions') or {}).get('height')}

def candidates(a):
    out, seen = [], set()
    def add(c):
        if c and c['id'] not in seen: seen.add(c['id']); out.append(c)
    t = getj(f"{API}/taxa/{a['id']}")['results'][0]
    if a['k'] not in ('gallina', 'gallo'):
        for tp in t.get('taxon_photos', [])[:12]: add(ph(tp['photo'], 'taxon'))
    p = {'taxon_id': a['id'], 'photos': 'true', 'quality_grade': 'research', 'order_by': 'votes', 'per_page': 10, 'photo_license': 'cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc0'}
    if a['k'] == 'gallina': p.update(term_id=9, term_value_id=10)
    if a['k'] == 'gallo': p.update(term_id=9, term_value_id=11)
    if a['k'] in ('gallina', 'gallo'): p.pop('quality_grade')
    for ob in getj(f"{API}/observations", p)['results']:
        for o in ob.get('photos', [])[:1]: add(ph(o, 'obs'))
    return out[:15]

def thumb(c):
    try:
        r = requests.get(c['medium'], headers=H, timeout=30); r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert('RGB'); im.thumbnail((300, 225))
        return im
    except Exception:
        return None

font = ImageFont.load_default(size=34)
allc = {}
for a in data:
    try:
        cs = candidates(a)
    except Exception as e:
        print('FALLO', a['k'], e); continue
    with ThreadPoolExecutor(8) as ex: ims = list(ex.map(thumb, cs))
    cs = [c for c, im in zip(cs, ims) if im]; ims = [im for im in ims if im]
    cols = 5; rows = max(1, (len(ims) + cols - 1) // cols)
    sheet = Image.new('RGB', (cols * 310 + 10, rows * 235 + 60), (245, 240, 230))
    d = ImageDraw.Draw(sheet)
    d.text((12, 10), a['k'], fill=(0, 0, 0), font=font)
    for i, im in enumerate(ims):
        x = 10 + (i % cols) * 310; y = 55 + (i // cols) * 235
        sheet.paste(im, (x + (300 - im.width) // 2, y + (225 - im.height) // 2))
        d.rectangle([x, y, x + 44, y + 40], fill=(255, 255, 0))
        d.text((x + 6, y + 2), str(i + 1), fill=(0, 0, 0), font=font)
    sheet.save(f"review/{a['k']}.jpg", quality=80)
    allc[a['k']] = cs
    print(a['k'], len(cs), flush=True)
json.dump(allc, open('review/candidates.json', 'w'), ensure_ascii=False, indent=0)
print('TOTAL', len(allc))
