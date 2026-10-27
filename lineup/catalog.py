import json
from functools import lru_cache
from autotata.paths import ASSETS


@lru_cache(maxsize=1)
def load_catalog():
    data = json.loads((ASSETS/'lineup/catalog.json').read_text(encoding='utf-8'))
    items = data['items']
    if len(items) != data['count'] or len({r['id'] for r in items}) != len(items):
        raise ValueError('塔塔资料库不完整')
    return items


def choose_available(wanted, inventory, used=()):
    """Exact stage first, then highest owned stage in the same evolution chain."""
    by_id = {r['id']: r for r in load_catalog()}
    if wanted not in by_id:
        return None
    candidates = [r for r in inventory if r['id'] in by_id and r['id'] not in used
                  and by_id[r['id']]['family'] == by_id[wanted]['family']]
    return min(candidates, key=lambda r: (r['id'] != wanted, -by_id[r['id']]['stage'], r['id'])) if candidates else None


def deployment_plan(cells, inventory, limit):
    placed = []; issues = []; used = set()
    for index, wanted in enumerate(cells):
        if wanted is None:
            continue
        if not wanted or wanted == '?':
            issues.append({'index': index, 'reason': '识别不确定'}); continue
        candidate = choose_available(wanted, inventory, used)
        if candidate is None:
            issues.append({'index': index, 'reason': '库存未找到'}); continue
        if len(placed) >= limit:
            issues.append({'index': index, 'reason': '超过上阵上限'}); continue
        used.add(candidate['id'])
        placed.append({'index': index, 'wanted': wanted, 'actual': candidate['id'],
                       'substituted': wanted != candidate['id']})
    return {'placements': placed, 'issues': issues}
