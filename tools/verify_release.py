"""Verify source, assets, smoke report and archive for the unified all package.

Run after tools/build.py and --smoke-test. No device input is sent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types
from zipfile import ZipFile

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotata import __version__


def signature(code):
    return (code.co_code, code.co_names, code.co_varnames,
            tuple(signature(v) if isinstance(v, types.CodeType) else v for v in code.co_consts))


def verify(report_dir, main_exe=None, dist_root=None):
    packages = []
    for target, name in [('all', 'AutoTaTa')]:
        exe = main_exe if target == 'all' and main_exe is not None else (dist_root or ROOT / 'dist') / target / (name + '.exe')
        archive = ROOT / 'releases' / __version__ / target / f'{name}-{__version__}-windows-x64.zip'
        smoke = json.loads((report_dir / ('packaged-' + target) / 'smoke.json').read_text(encoding='utf-8'))
        assert smoke['passed'] and not smoke['errors'] and smoke['version'] == __version__, smoke
        frames = smoke.get('nativeFrames') or {'fishing': smoke['nativeFrame']}
        for label, state in frames.items():
            assert (state['enabled'] and state['frameStyles'] and state['nativeRendering']
                    and state['opaque'] and not state['layered'] and not state['errors']), (target, label, state)
        reader = CArchiveReader(str(exe))
        assert not any(n.replace('\\', '/').startswith(('assets/fixtures/', 'tests/', 'validation/')) for n in reader.toc)
        pyz = reader.open_embedded_archive(next(n for n in reader.toc if n.endswith('.pyz')))
        required = ['autotata.window_frame', 'autotata.popup_windows', 'autotata.runtime', 'autotata.activity_shop']
        required += ['autotata.app', 'autotata.smoke', 'fishing.gpu_app', 'fishing.startup',
                     'rafting.engine', 'rafting.backend', 'rafting.runner', 'rafting.vision',
                     'treasure.backend', 'treasure.solver', 'lineup.backend', 'lineup.catalog',
                     'lineup.vision', 'lineup.runner', 'lineup.engine', 'lineup.input']
        assert smoke['lineupEditor']['independentWindow'] and smoke['lineupEditor']['nativeRendering'] and smoke['lineupEditor']['nativeCaption']
        assert all(module in pyz.toc for module in required), (target, required)
        # Check every shipped project module, rather than a hand-selected fix list.
        checked = []
        for module in pyz.toc:
            if module.split('.')[0] not in ('autotata', 'fishing', 'rafting', 'treasure','lineup'):
                continue
            source = ROOT / (module.replace('.', '/') + '.py')
            if not source.exists():
                source = ROOT / module.replace('.', '/') / '__init__.py'
            assert source.is_file(), (target, module, source)
            expected = compile(source.read_text(encoding='utf-8'), str(source), 'exec')
            assert signature(expected) == signature(pyz.extract(module)), (target, module)
            checked.append(module)
        assets = []
        for key in reader.toc:
            relative = key.replace('\\', '/')
            if relative.startswith(('assets/', 'licenses/')):
                source = ROOT / relative
                assert source.is_file() and reader.extract(key) == source.read_bytes(), (target, relative)
                assets.append(relative)
        lineup_assets=[a for a in assets if a.startswith('assets/lineup/')]
        assert len([a for a in lineup_assets if a.startswith('assets/lineup/tatari/')])==248
        assert len(lineup_assets)==257
        digest = hashlib.sha256(exe.read_bytes()).hexdigest()
        with ZipFile(archive) as package:
            assert hashlib.sha256(package.read(name + '.exe')).hexdigest() == digest
            for document in ('README.md', 'RELEASE_NOTES.md'):
                assert package.read(document) == (ROOT / document).read_bytes()
        packages.append({'target': target, 'exe': str(exe), 'archive': str(archive),
                         'sha256': digest, 'modulesChecked': checked, 'assetsChecked': len(assets),
                         'nativeFrames': frames, 'passed': True})
    report = {'version': __version__, 'passed': True, 'packages': packages, 'mainStaged': main_exe is not None or dist_root is not None,
              'gameInputSent': False, 'systemShutdownExecuted': False}
    (report_dir / 'release.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_dir', type=Path)
    parser.add_argument('--main-exe', type=Path, help='Verify a staged main program before replacing a locked executable')
    parser.add_argument('--dist-root',type=Path,help='Verify the all package in a staged output folder')
    arguments = parser.parse_args()
    result = verify(arguments.report_dir.resolve(), arguments.main_exe.resolve() if arguments.main_exe else None, arguments.dist_root.resolve() if arguments.dist_root else None)
    print(json.dumps({'version': __version__, 'packagesPassed': len(result['packages']),
                      'archivesMatch': True, 'fixturesInPackages': 0}))
