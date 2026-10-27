"""Inspect omitted local resources; never download assets or connect a device."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def inspect(root):
    root=Path(root).resolve();manifest=root/'docs/RESOURCE_MANIFEST.json'
    if not manifest.is_file():raise FileNotFoundError('Resource manifest is missing; read docs/SOURCE_DISTRIBUTION.md')
    data=json.loads(manifest.read_text('utf8'));missing=[];mismatch=[];present=0
    for entry in data['omittedRuntimeResources']:
        relative=entry['path'];path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Resource path escaped project')
        if not path.is_file():missing.append(relative);continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:mismatch.append(relative)
        else:present+=1
    integrations=[p for p in data['omittedIntegrationSources'] if not (root/p).is_dir()]
    return {'present':present,'missing':missing,'mismatched':mismatch,
            'missingIntegrationSources':integrations,'downloaded':False,'deviceConnected':False,
            'runtimeResourcesComplete':not missing and not mismatch and not integrations}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict',action='store_true',help='Fail when full runtime resources are unavailable')
    parser.add_argument('--json',action='store_true')
    arguments=parser.parse_args();result=inspect(ROOT)
    if arguments.json:print(json.dumps(result,ensure_ascii=True,indent=2))
    else:
        print('AutoTaTa 0.2.36 source showcase resource check')
        print(f"Present: {result['present']}; omitted/missing: {len(result['missing'])}; mismatched: {len(result['mismatched'])}")
        print('No downloads or device connections were attempted.')
        print('Read docs/SOURCE_DISTRIBUTION.md before attempting full runtime or redistribution.')
        for path in (result['missing']+result['mismatched']+result['missingIntegrationSources'])[:8]:print(' - '+path)
    raise SystemExit(2 if arguments.strict and not result['runtimeResourcesComplete'] else 0)
