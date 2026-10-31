"""Export a new, filtered source showcase; never upload or change visibility."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES=('README.md','README.en.md','LICENSE','NOTICE.md','.gitignore','requirements.txt','main.py')
SUPPORT_FILES=('.github/CONTRIBUTING.md','requirements/build.txt','scripts/setup.bat',
               'scripts/build.bat','scripts/start.bat','scripts/start-autofish.bat',
               'scripts/start-lineup.bat','scripts/start-rafting.bat','scripts/start-treasure.bat')
DOCS=('DESIGN_AND_AI.md','VALIDATION_SUMMARY.md','SOURCE_DISTRIBUTION.md',
      'USAGE.md','RESOURCE_MANIFEST.json','KNOWN_ISSUES.md','KNOWN_ISSUES.en.md',
      'MAINTENANCE.md','RELEASE_NOTES.md','legal/DISCLAIMER.md','legal/LICENSE_SCOPE.md',
      'legal/THIRD_PARTY_NOTICES.md')
TOOLS=('build.py','release_policy.py','verify_release.py','check_ui_fonts.py',
       'subset_chiron.py','make_app_icon.py','prepare_lineup_catalog.py',
       'check_source_assets.py','prepare_source_review.py')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_files(root):
    duplicate=root/'licenses/MaaAgentBinary-1.0.1.dist-info-LICENSE'
    canonical=root/'licenses/MaaAgentBinary-LICENSE'
    if duplicate.exists() and digest(duplicate)!=digest(canonical):
        raise ValueError('License copies differ; review both before excluding either copy')
    paths={root/name for name in (*ROOT_FILES,*SUPPORT_FILES)}
    for package in ('autotata','fishing','lineup','rafting','treasure','tests'):
        paths.update(p for p in (root/package).rglob('*.py') if '__pycache__' not in p.parts)
    paths.update(root/'docs'/name for name in DOCS)
    paths.update(root/'tools'/name for name in TOOLS)
    paths.update(p for p in (root/'assets/ui').rglob('*') if p.suffix in ('.qml','.svg'))
    paths.update((root/'assets/fonts').glob('*.ttf'))
    # The dist-info copy is byte-identical to the retained canonical license.
    paths.update(p for p in (root/'licenses').iterdir() if p.is_file()
                 and p.name!='MaaAgentBinary-1.0.1.dist-info-LICENSE')
    paths.update(p for p in (root/'packaging').glob('*.spec'))
    paths.update(root/name for name in ('assets/app-icon.png','assets/app.ico','assets/README.md',
                                      'design/figma/app-wordmark-0.1.38.png'))
    paths.update(p for p in (root/'docs/media').iterdir() if p.suffix in ('.svg','.png'))
    return sorted(paths)


def resource_manifest(root, selected):
    omitted=[]
    for path in sorted((root/'assets').rglob('*')):
        if not path.is_file() or path in selected:continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Refusing linked resource: {path}')
        relative=path.relative_to(root).as_posix()
        if relative.startswith('assets/fixtures/'):continue
        omitted.append({'path':relative,'bytes':path.stat().st_size,'sha256':digest(path),
                        'category':'integration-binary' if path.suffix=='.dex' else 'unbundled-game-resource'})
    return {'schema':'autotata-source-review-resources-v1','version':'0.2.36',
            'purpose':'Inventory only; no permission to download or redistribute the resources is implied.',
            'omittedRuntimeResources':omitted,
            'omittedIntegrationSources':['tools/maatouch-display/'],
            'omittedPrivateEvidence':['assets/fixtures/','tests/fixtures/','validation/','logs/'],
            'notACompleteRuntimeDistribution':True}


def export(output):
    root=ROOT.resolve();output=output.resolve();build=(root/'build').resolve()
    if output==build or not output.is_relative_to(build):
        raise ValueError('Source review output must be a new folder inside this project build directory')
    if output.exists():raise FileExistsError('Choose a new empty destination; existing reviews are never overwritten')
    for parent in (output,*output.parents):
        if parent==root:break
        if parent.is_symlink() or parent.is_junction():raise ValueError(f'Refusing linked output: {parent}')
    selected=set(selected_files(root))
    resources=resource_manifest(root,selected)
    manifest=root/'docs/RESOURCE_MANIFEST.json'
    manifest.write_text(json.dumps(resources,ensure_ascii=False,indent=2)+'\n','utf8')
    paths=selected_files(root)
    # Preflight the complete list before copying. Unlisted inputs never enter
    # the repository; secrets and field evidence are not filtered after upload.
    for source in paths:
        if not source.is_file():raise FileNotFoundError(source)
        if source.is_symlink() or not source.resolve().is_relative_to(root):raise ValueError(source)
        for parent in source.parents:
            if parent==root:break
            if parent.is_symlink() or parent.is_junction():raise ValueError(parent)
        if source.suffix=='.py':ast.parse(source.read_text('utf8'),filename=str(source))
    output.mkdir(parents=True)
    entries=[]
    for source in paths:
        relative=source.relative_to(root);destination=output/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        entries.append({'path':relative.as_posix(),'bytes':source.stat().st_size,'sha256':digest(source)})
    summary={'schema':'autotata-source-showcase-v1','version':'0.2.36','author':'maozo',
             'snapshotDate':'2026-11-01','license':'PolyForm-Noncommercial-1.0.0',
             'lastFunctionalMaintenanceDate':'2026-10-24','maintenanceDeclarationDate':'2026-10-28',
             'maintenance':'ended','includesThirdPartyRuntimeBinaries':False,
             'includesGameSourceArtwork':False,'files':entries}
    (output/'docs/SOURCE_MANIFEST.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({'files':len(entries)+1,'bytes':sum(e['bytes'] for e in entries),
                      'omittedRuntimeResources':len(resources['omittedRuntimeResources']),
                      'destination':str(output)},ensure_ascii=True))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/github-review-20261028/source')
    export(parser.parse_args().output)
