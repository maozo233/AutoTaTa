"""Prepare the browser-exported public TataDex catalog without scraping hidden APIs."""
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
base = ROOT/'assets/lineup'
source = json.loads((ROOT/'design/lineup/catalog-source.json').read_text(encoding='utf-8'))
target = base/'tatari'; target.mkdir(exist_ok=True)
items = []; family = None; previous = None
for item in source['items']:
    row = dict(item); row['name'] = row['name'].strip()
    if row['stage'] == 1: family = row['id']
    elif not previous or row['stage'] != previous['stage']+1 or row['elementKey'] != previous['elementKey'] or row['roleKey'] != previous['roleKey']:
        raise ValueError('Inconsistent evolution order: '+row['id'])
    original = next((ROOT/'design/lineup/source-images').glob(row['id']+'.*'))
    with Image.open(original) as im:
        rgba = im.convert('RGBA'); lo, hi = rgba.getchannel('A').getextrema()
        if lo != 0 or hi < 127: raise ValueError('Missing transparency: '+row['id'])
        output = target/(row['id']+'.png')
        if original.suffix == '.png':
            if original.resolve()!=output.resolve():shutil.copyfile(original, output)
        else: rgba.save(output)
        row.update(family=family,imagePath='lineup/tatari/'+output.name,width=rgba.width,height=rgba.height,
                   sourceSha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                   sha256=hashlib.sha256(output.read_bytes()).hexdigest(),transparent=True,
                   familySource='TataDex default evolution order; stages/element/role continuity checked')
    items.append(row); previous = row
catalog = {'source':source['source'],'retrieved':source['retrieved'],'count':len(items),'items':items,
           'attribution':'TataDex 非官方玩家资料站；游戏素材版权归原作者所有。仅使用公开图鉴资料和原图。'}
(base/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'characters':len(items),'families':len({r['family'] for r in items}),'transparentPngs':len(items)}))
