"""Release retention must not discard the last working archives on failure."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.build import build, main
from tools.release_policy import checked_path, cleanup_plan, prune_releases

ROOT = Path(__file__).resolve().parents[1]


class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'validation' / 'test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def publish(self, version):
        archive = self.root / 'releases' / version / 'all' / f'AutoTaTa-{version}-windows-x64.zip'
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b'previous complete archive')
        return archive

    def fake_builder(self, *args, **kwargs):
        exe = self.root / 'dist' / 'all' / 'AutoTaTa.exe'
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b'new executable')

    def documents(self):
        for name in ('README.md', 'RELEASE_NOTES.md'):
            (self.root / name).write_text(name, encoding='utf-8')

    def test_numeric_retention_and_only_all(self):
        for version in ('0.2.9', '0.2.10', '0.2.11', '0.2.12'):
            self.publish(version)
            (self.root / 'releases' / version / 'lineup').mkdir()
            (self.root / 'build' / f'release-{version}').mkdir(parents=True)
        unrelated = self.root / 'releases' / 'notes.txt'
        unrelated.write_text('keep')
        plan = prune_releases(self.root)
        self.assertEqual(plan['retainedVersions'], ['0.2.12', '0.2.11', '0.2.10'])
        self.assertFalse((self.root / 'releases' / '0.2.9').exists())
        self.assertFalse((self.root / 'build' / 'release-0.2.9').exists())
        for version in plan['retainedVersions']:
            archive = self.root / 'releases' / version / 'all' / f'AutoTaTa-{version}-windows-x64.zip'
            self.assertEqual(archive.read_bytes(), b'previous complete archive')
            self.assertFalse((self.root / 'releases' / version / 'lineup').exists())
        self.assertTrue(unrelated.exists())

    def test_unpublished_versions_do_not_displace_published(self):
        for version in ('0.2.33', '0.2.34', '0.2.35'):
            self.publish(version)
        (self.root / 'releases' / '9.0.0' / 'all').mkdir(parents=True)
        self.assertEqual(cleanup_plan(self.root)['retainedVersions'], ['0.2.35', '0.2.34', '0.2.33'])

    def test_no_published_archive_means_no_deletion(self):
        (self.root / 'releases' / '0.2.1').mkdir(parents=True)
        self.assertEqual(prune_releases(self.root)['removed'], [])

    def test_cleanup_rejects_root_and_escape(self):
        for path in (self.root, self.root / '..' / 'outside'):
            with self.assertRaises(ValueError):
                checked_path(self.root, path)
        with self.assertRaises(ValueError):
            cleanup_plan(self.root, keep=0)

    def test_junction_preflight_preserves_every_archive(self):
        archives = [self.publish(f'0.2.{n}') for n in range(31, 35)]
        preserved = self.root / 'preserved'
        preserved.mkdir()
        evidence = preserved / 'evidence.txt'
        evidence.write_text('keep')
        junction = archives[0].parent / 'linked-directory'
        junction.mkdir()
        with patch.object(Path, 'is_junction', autospec=True, side_effect=lambda path: path == junction):
            with self.assertRaises(ValueError):
                prune_releases(self.root)
            self.assertTrue(all(path.exists() for path in archives))
            self.assertEqual(evidence.read_text(), 'keep')

    def test_build_failure_preserves_all_versions(self):
        archives = [self.publish(f'0.2.{n}') for n in range(31, 35)]
        with patch('tools.build.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'build')):
            with self.assertRaises(subprocess.CalledProcessError):
                build(self.root, version='0.2.35')
        self.assertTrue(all(path.exists() for path in archives))

    def test_zip_failure_preserves_previous_archive(self):
        previous = self.publish('0.2.35')
        self.documents()
        with patch('tools.build.subprocess.run', side_effect=self.fake_builder), patch('tools.build.ZipFile.write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                build(self.root, version='0.2.35')
        self.assertEqual(previous.read_bytes(), b'previous complete archive')
        self.assertEqual(list(previous.parent.iterdir()), [previous])

    def test_success_publishes_complete_zip_before_pruning(self):
        for n in range(31, 35):
            self.publish(f'0.2.{n}')
        self.documents()
        with patch('tools.build.subprocess.run', side_effect=self.fake_builder):
            plan = build(self.root, version='0.2.35')
        self.assertEqual(plan['retainedVersions'], ['0.2.35', '0.2.34', '0.2.33'])
        archive = self.root / 'releases' / '0.2.35' / 'all' / 'AutoTaTa-0.2.35-windows-x64.zip'
        with ZipFile(archive) as package:
            self.assertEqual(set(package.namelist()), {'AutoTaTa.exe', 'README.md', 'RELEASE_NOTES.md'})
            self.assertEqual(package.read('AutoTaTa.exe'), b'new executable')
        self.assertFalse((self.root / 'releases' / '0.2.31').exists())
        self.assertFalse((self.root / 'releases' / '0.2.32').exists())

    def test_standalone_cli_rejected_before_build(self):
        with patch('sys.argv', ['build.py', 'fishing']), patch('tools.build.build') as builder:
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        builder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
