# Construye la app de Olivia: descarga las fotos elegidas a mano (tools/photos.json),
# las reduce para que la app vaya rapida y genera index.html a partir de tools/template.html.
import json, os, re, io, time, hashlib, requests
from PIL import Image

H = {'User-Agent': 'LosAnimalesDeOlivia/1.0 (github.com/diegogerig4/sonidos-animales)'}
if os.path.exists('tools/data.json'):
    data = json.load(open('tools/data.json', encoding='utf-8'))
else:
    data = json.loads(re.search(r'const ANIMALS = (\[.*?\]);\n', open('index.html', encoding='utf-8').read()).group(1))
photos = json.load(open('tools/photos.json', encoding='utf-8'))
os.makedirs('img/t', exist_ok=True)
out = []
for a in data:
    p = photos.get(a['k'])
    if not p:
        print('fuera:', a['k']); continue
    pid, ext = p.split('.')
    url = f"https://inaturalist-open-data.s3.amazonaws.com/photos/{pid}/large.{ext}"
    by = ''
    try:
        by = requests.get(f"https://api.inaturalist.org/v1/photos/{pid}", headers=H, timeout=30).json()['results'][0].get('attribution', '')
    except Exception as e:
        print('sin autor', a['k'], e)
    time.sleep(1)
    r = requests.get(url, headers=H, timeout=60); r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert('RGB')
    big = im.copy(); big.thumbnail((1000, 1000), Image.LANCZOS)
    big.save(f"img/{a['k']}.jpg", quality=78, optimize=True, progressive=True)
    th = im.copy(); th.thumbnail((480, 360), Image.LANCZOS)
    th.save(f"img/t/{a['k']}.jpg", quality=74, optimize=True, progressive=True)
    v = hashlib.md5(r.content).hexdigest()[:8]
    a = dict(a, photo=f"img/{a['k']}.jpg?v={v}", thumb=f"img/t/{a['k']}.jpg?v={v}", photo_by=by.replace('\n', ' ').strip() or 'iNaturalist', photo_src=url)
    out.append(a)
    print(a['k'], big.size, os.path.getsize(f"img/{a['k']}.jpg") // 1024, 'KB', flush=True)
used = {f"{a['k']}.jpg" for a in out}
for d in ('img', 'img/t'):
    for f in os.listdir(d):
        if f.endswith('.jpg') and f not in used: os.remove(os.path.join(d, f))
json.dump(out, open('tools/data.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
html = open('tools/template.html', encoding='utf-8').read().replace('__DATA__', json.dumps(out, ensure_ascii=False))
open('index.html', 'w', encoding='utf-8').write(html)
print('TOTAL', len(out))
