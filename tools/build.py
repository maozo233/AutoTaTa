"""Build the all package and retain the newest three published versions."""
import argparse
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autotata import __version__
from tools.release_policy import checked_path, prune_releases, version_key


def build(root=ROOT, dist_root=None, version=__version__):
    root = Path(root).resolve()
    version_key(version)
    (root / 'validation').mkdir(exist_ok=True)
    dist = (Path(dist_root).resolve() if dist_root else root / 'dist') / 'all'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(dist),
        '--workpath', str(root / 'build' / 'all'), str(root / 'packaging' / 'AutoTaTa.spec'),
    ], cwd=root, check=True)
    release = checked_path(root, root / 'releases' / version / 'all')
    release.mkdir(parents=True, exist_ok=True)
    archive = release / f'AutoTaTa-{version}-windows-x64.zip'
    pending = release / f'.{archive.name}.{uuid4().hex}.pending'
    try:
        with ZipFile(pending, 'w', ZIP_DEFLATED, compresslevel=6) as package:
            package.write(dist / 'AutoTaTa.exe', 'AutoTaTa.exe')
            for document in ('README.md', 'RELEASE_NOTES.md'):
                package.write(root / document, document)
        pending.replace(archive)
    finally:
        pending.unlink(missing_ok=True)
    plan = prune_releases(root)
    print(f'Release: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MiB)')
    print('Retained versions: ' + ', '.join(plan['retainedVersions']))
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['all'], default='all', nargs='?')
    parser.add_argument('--dist-root', type=Path)
    arguments = parser.parse_args()
    build(dist_root=arguments.dist_root)


if __name__ == '__main__':
    main()
