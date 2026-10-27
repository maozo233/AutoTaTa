"""Fail packaging when shipped UI fonts omit Chinese text used by the app."""
from pathlib import Path
from fontTools.ttLib import TTFont


def check(root):
    text = ''.join(p.read_text(encoding='utf-8') for folder, pattern in
                   (('autotata', '*.py'), ('treasure', '*.py'), ('fishing', '*.py'), ('rafting', '*.py'), ('lineup','*.py'), ('assets/ui', '*.qml'))
                   for p in (root / folder).glob(pattern))
    catalog=root/'assets/lineup/catalog.json'
    if catalog.is_file():text+=catalog.read_text(encoding='utf8')
    required = {ord(c) for c in text if '\u3400' <= c <= '\u9fff'}
    for weight in ('500M', '700B', '900H'):
        path = root / 'assets/fonts' / f'ChironGoRoundTC-{weight}.ttf'
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            missing = sorted(c for c in required if not cmap.get(c) or cmap[c] == '.notdef')
        if missing:
            raise RuntimeError(f'{path.name} 缺字: ' + ''.join(map(chr, missing)))
    print(f'Chinese UI font coverage passed: {len(required)} characters across all weights')


if __name__ == '__main__':
    check(Path(__file__).resolve().parents[1])
