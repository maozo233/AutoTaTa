"""Keep the three newest published all packages; never follow directory links."""
import os
from pathlib import Path
import re
import shutil

RETAIN_VERSIONS = 3
VERSION = re.compile(r'\d+\.\d+\.\d+\Z')
STANDALONE_TARGETS = ('fishing', 'treasure', 'rafting', 'lineup')


def version_key(value):
    if not VERSION.fullmatch(value):
        raise ValueError(f'Invalid release version: {value}')
    return tuple(map(int, value.split('.')))


def checked_path(root, path):
    root = Path(root).resolve()
    path = Path(path).absolute()
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f'Cleanup path must stay inside {root}: {path}')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError(f'Cleanup refuses directory links: {part}')
    return resolved


def published_versions(root):
    root = Path(root).resolve()
    releases = checked_path(root, root / 'releases')
    if not releases.is_dir():
        return []
    versions = []
    for directory in releases.iterdir():
        if VERSION.fullmatch(directory.name):
            directory = checked_path(root, directory)
            archive = checked_path(root, directory / 'all' / f'AutoTaTa-{directory.name}-windows-x64.zip')
            if archive.is_file():
                versions.append(directory.name)
    return sorted(versions, key=version_key, reverse=True)


def cleanup_plan(root, keep=RETAIN_VERSIONS):
    if keep < 1:
        raise ValueError('At least one published version must be retained')
    root = Path(root).resolve()
    retained = published_versions(root)[:keep]
    removals = []
    if retained:
        for directory in (root / 'releases').iterdir():
            if not VERSION.fullmatch(directory.name):
                continue
            if directory.name not in retained:
                removals.append(checked_path(root, directory))
            else:
                for target in STANDALONE_TARGETS:
                    child = directory / target
                    if child.exists() or child.is_symlink():
                        removals.append(checked_path(root, child))
        work = checked_path(root, root / 'build')
        if work.is_dir():
            for directory in work.glob('release-*'):
                version = directory.name.removeprefix('release-')
                if VERSION.fullmatch(version) and version not in retained:
                    removals.append(checked_path(root, directory))
    return {'retainedVersions': retained, 'removed': [str(path) for path in removals]}


def prune_releases(root, keep=RETAIN_VERSIONS):
    plan = cleanup_plan(root, keep)
    # Preflight every tree before removing anything. A junction must never turn
    # release cleanup into deletion in another directory.
    for value in plan['removed']:
        path = checked_path(root, value)
        if path.is_dir():
            for directory, dirs, files in os.walk(path, followlinks=False):
                for name in (*dirs, *files):
                    checked_path(root, Path(directory) / name)
    for value in plan['removed']:
        path = checked_path(root, value)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return plan
