# Prepara la app de Olivia: busca grabaciones reales de cada animal (iNaturalist y Wikimedia Commons),
# comprueba con un reconocedor de sonidos (YAMNet) que de verdad es ese animal y que no hay voces ni musica,
# recorta el mejor trozo, iguala el volumen y genera index.html con fotos reales.
import sys, os, re, json, time, glob, hashlib, subprocess
import requests, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from animals import A, DOM
from ai_edge_litert.interpreter import Interpreter

H = {'User-Agent': 'LosAnimalesDeOlivia/1.0 (github.com/diegogerig4/sonidos-animales)'}
RAW = 'work/raw'
os.makedirs(RAW, exist_ok=True); os.makedirs('sounds', exist_ok=True)
YI = Interpreter('work/yamnet.tflite'); YI.allocate_tensors()
IIN = YI.get_input_details()[0]['index']; IOUT = YI.get_output_details()[0]['index']
BAD = [0, 1, 2, 3, 4, 5, 132, 137, 300, 288, 500, 494, 495]  # voz humana, musica, motores...

def log(*a): print(*a, flush=True)

def getj(url, params=None):
    for i in range(6):
        try:
            r = requests.get(url, params=params, headers=H, timeout=30)
            if r.status_code == 429:
                time.sleep(10 * (i + 1)); continue
            r.raise_for_status(); time.sleep(1.1)
            return r.json()
        except Exception:
            if i == 5: raise
            time.sleep(4 * (i + 1))

def taxon(sci):
    r = getj('https://api.inaturalist.org/v1/taxa/autocomplete', {'q': sci, 'per_page': 10, 'locale': 'es'})['results']
    m = [t for t in r if t['name'].lower() == sci.lower()]
    return m[0] if m else None

def commons(title):
    r = getj('https://commons.wikimedia.org/w/api.php', {'action': 'query', 'titles': 'File:' + title, 'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'format': 'json'})
    ii = list(r['query']['pages'].values())[0]['imageinfo'][0]; em = ii.get('extmetadata', {})
    return {'url': ii['url'], 'lic': em.get('LicenseShortName', {}).get('value', ''),
            'by': re.sub('<[^>]+>', '', em.get('Artist', {}).get('value', ''))[:60].strip(),
            'src': 'Wikimedia Commons', 'page': ii.get('descriptionurl')}

def candidates(k, tid, titles):
    out = []
    for t in titles:
        try: out.append(commons(t))
        except Exception as e: log('  commons?', t, e)
    p = {'taxon_id': tid, 'sounds': 'true', 'order_by': 'votes', 'per_page': 12}
    if k not in DOM: p['quality_grade'] = 'research'
    for ob in getj('https://api.inaturalist.org/v1/observations', p)['results']:
        for s in ob.get('sounds', [])[:1]:
            if s.get('file_url'):
                out.append({'url': s['file_url'], 'lic': s.get('license_code') or 'c',
                            'by': (ob['user'].get('name') or ob['user']['login'])[:60], 'src': 'iNaturalist',
                            'page': 'https://www.inaturalist.org/observations/%d' % ob['id']})
    return out

def fetch(c):
    fn = RAW + '/' + hashlib.md5(c['url'].encode()).hexdigest()
    r = requests.get(c['url'], headers=H, timeout=60, stream=True); data = b''
    for ch in r.iter_content(65536):
        data += ch
        if len(data) > 15e6: return None
    open(fn, 'wb').write(data)
    if subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', fn, '-ac', '1', '-ar', '16000', '-t', '60', fn + '.16k.wav']).returncode: return None
    return fn

def score(fn, exp):
    y, sr = sf.read(fn + '.16k.wav', dtype='float32')
    if len(y) < sr * 0.8: return None
    P = []
    for s in range(0, max(1, len(y) - 15600 + 1), 8000):
        f = y[s:s + 15600]
        if len(f) < 15600: f = np.pad(f, (0, 15600 - len(f)))
        YI.set_tensor(IIN, f); YI.invoke(); P.append(YI.get_tensor(IOUT)[0].copy())
    P = np.array(P); e = P[:, exp].max(1); an = P[:, [67, 103, 106, 68, 81]].max(1); bad = P[:, BAD].max(1)
    fs = e + 0.3 * an - 1.5 * bad; w = min(9, len(fs)); cs = np.convolve(fs, np.ones(w) / w, 'valid'); i = int(np.argmax(cs))
    return dict(ys=float(cs[i]), start=i * 0.5, dur=min(len(y) / sr - i * 0.5, w * 0.5 + 0.5), bad=float(bad[i:i + w].mean()), exp=float(e[i:i + w].max()))

out = []
for k, nm, cat, sci, titles, exp in A:
    try:
        t = taxon(sci)
        if not t: log('SIN TAXON', k); continue
        res = []
        for c in candidates(k, t['id'], titles)[:13]:
            try:
                fn = fetch(c)
                if not fn: continue
                s = score(fn, exp)
                if s: res.append(dict(c, fn=fn, **s))
            except Exception as e: log('  fallo', k, e)
        res.sort(key=lambda x: -x['ys'])
        good = [r for r in res if r['bad'] < 0.2 and r['exp'] >= 0.4 and r['ys'] >= 0.25][:2]
        clips = []
        for j, r in enumerate(good):
            name = '%s%d.mp3' % (k, j + 1); d = max(2.5, r['dur'])
            af = 'highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.08,afade=t=out:st=%.2f:d=0.3' % (d + 0.1)
            if subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '%.2f' % max(0, r['start'] - 0.2), '-t', '%.2f' % (d + 0.4), '-i', r['fn'],
                               '-ac', '1', '-af', af, '-ar', '44100', '-b:a', '80k', 'sounds/' + name]).returncode == 0:
                clips.append({'file': name, 'src': r['src'], 'by': r['by'], 'lic': r['lic'], 'page': r['page']})
        for f in glob.glob(RAW + '/*'): os.remove(f)
        if not clips: log('SIN SONIDO VALIDO', k); continue
        ph = t.get('default_photo') or {}
        out.append({'k': k, 'name': nm, 'cat': cat, 'sci': t['name'], 'id': t['id'],
                    'photo': (ph.get('medium_url') or '').replace('medium', 'large'), 'photo_by': ph.get('attribution', ''), 'clips': clips})
        log(k, 'ok', len(clips), [(round(r['ys'], 2), round(r['exp'], 2)) for r in good])
    except Exception as e:
        log('FALLO', k, e)

# Gallina y gallo comparten especie: buscamos una foto de hembra y otra de macho.
for a in out:
    if a['k'] in ('gallina', 'gallo'):
        try:
            v = 10 if a['k'] == 'gallina' else 11
            r = getj('https://api.inaturalist.org/v1/observations', {'taxon_id': a['id'], 'term_id': 9, 'term_value_id': v, 'photos': 'true', 'order_by': 'votes', 'per_page': 3})
            p = r['results'][0]['photos'][0]
            a['photo'] = p['url'].replace('square', 'large'); a['photo_by'] = p.get('attribution', '')
        except Exception as e: log('foto', a['k'], e)

used = {c['file'] for a in out for c in a['clips']}
for f in glob.glob('sounds/*.mp3'):
    if os.path.basename(f) not in used: os.remove(f)

log('TOTAL', len(out), 'animales,', len(used), 'sonidos')
if len(out) < 40:
    log('Demasiados fallos: no se publica.'); sys.exit(1)

html = open('tools/template.html', encoding='utf-8').read().replace('__DATA__', json.dumps(out, ensure_ascii=False))
open('index.html', 'w', encoding='utf-8').write(html)

# Iconos de la app
from PIL import Image, ImageDraw
def icon(S):
    im = Image.new('RGB', (S, S), '#FFB23F'); d = ImageDraw.Draw(im); s = S / 180; W = '#FFF4E0'
    d.ellipse([S * 0.08, S * 0.08, S * 0.92, S * 0.92], fill='#F27A5E')
    d.ellipse([60 * s, 88 * s, 120 * s, 140 * s], fill=W)
    for (x, y) in [(48, 62), (74, 44), (106, 44), (132, 62)]:
        d.ellipse([(x - 13) * s, (y - 16) * s, (x + 13) * s, (y + 16) * s], fill=W)
    return im
for S in (180, 192, 512): icon(S).save('icon-olivia-%d.png' % S)
log('Listo')
