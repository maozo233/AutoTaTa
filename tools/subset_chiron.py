"""Subset Chiron GoRound TC for the shipped UI; preserve OFL font naming."""
from pathlib import Path
import argparse
from fontTools import subset
from fontTools.ttLib import TTFont

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
text = ''.join(p.read_text(encoding='utf-8') for folder, glob in
               (('autotata', '*.py'), ('treasure', '*.py'), ('fishing', '*.py'), ('rafting', '*.py'), ('lineup','*.py'), ('assets/ui', '*.qml'), ('tests', '*.py'))
               for p in (root / folder).glob(glob))
text += (root/'assets/lineup/catalog.json').read_text(encoding='utf8')
text += ''.join(chr(c) for c in range(32, 127))
for weight in ('500M', '700B', '900H'):
    name = f'ChironGoRoundTC-{weight}.ttf'
    font = TTFont(args.source / name)
    options = subset.Options()
    options.name_IDs = ['*']
    options.name_languages = ['*']
    options.name_legacy = True
    worker = subset.Subsetter(options=options)
    worker.populate(text=text)
    worker.subset(font)
    font.save(root / 'assets/fonts' / name)
    print(name, len(font.getBestCmap()))
