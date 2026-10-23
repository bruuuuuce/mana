import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from skill_factory.transactions.plantuml import render_integrated

base = Path('/private/tmp/mana-vis-f01')
out = Path('docs/reports/TRANSACTION-01-VIS-01-F01')
examples = Path('docs/examples/transaction-01-vis-01')
before = json.loads((base / 'before.json').read_text())
checks = json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-R1/checks.json').read_text())
checks.pop('mana-skill-factory')

def run_check(item):
    name, check = item
    p = subprocess.run(check['command'], capture_output=True, text=True)
    (out / (name + '.log')).write_text(p.stdout + p.stderr)
    return name, {'command': check['command'], 'exit': p.returncode,
                  'tail': (p.stdout + p.stderr)[-400:]}

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = dict(pool.map(run_check, checks.items()))
assert all(c['exit'] == 0 for c in results.values()), results
(out / 'checks.json').write_text(json.dumps(results, indent=2) + '\n')
args = ['java', '-Djava.awt.headless=true', '-XX:-UsePerfData', '-jar',
        '/Applications/plantuml-1.2024.8.jar']
changed = []
renders = []
for run in range(2):
    paths = []
    for scenario in 'ABC':
        source = Path('docs/examples/transaction-01-t02-s02') / scenario
        report = json.loads((source / 'wait-dependency.json').read_bytes())
        raw = {i['id']: (source / 'inputs' / (i['id'] + '.json')).read_bytes()
               for i in report['inputs']}
        original = copy.deepcopy((report, raw))
        views = render_integrated(report, raw)
        assert views == render_integrated(report, raw)
        assert original == (report, raw)
        for name, value in views.items():
            p = base / ('repeat-' + str(run)) / scenario / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)
            delivered = examples / scenario / name
            if (scenario, name) == ('C', 'mixed-replacement.puml'):
                assert delivered.read_text().replace(
                    'MIXED / RESUME_REQUIRES_COMPLETION',
                    'MIXED / RESUME_REQUIRES_\\nCOMPLETION') == value
            else:
                assert delivered.read_bytes() == p.read_bytes(), str(delivered)
            if name.endswith('.puml'):
                paths.append(str(p))
    assert len(paths) == 14
    for option in ['-checkonly', '-tsvg']:
        p = subprocess.run(args + [option] + paths, capture_output=True, text=True)
        renders.append({'run': run, 'option': option, 'count': len(paths),
                        'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        assert p.returncode == 0
    for name in paths:
        p = Path(name).with_suffix('.svg')
        ET.parse(p)
        relative = p.relative_to(base / ('repeat-' + str(run)))
        delivered = examples / relative
        if run:
            assert p.read_bytes() == (base / 'repeat-0' / relative).read_bytes()
        elif p.read_bytes() != delivered.read_bytes():
            changed.append(str(relative))
assert changed == ['C/mixed-replacement.svg'], changed
# Publish only the generated pair that changed; all other regenerated outputs match.
for ext in ['puml', 'svg']:
    shutil.copyfile(base / 'repeat-0/C' / ('mixed-replacement.' + ext),
                    examples / 'C' / ('mixed-replacement.' + ext))
for name in ['before.svg', 'before.puml', 'before.png', 'expanded.svg', 'expanded.png',
             'measured.svg', 'measured.png', 'unadjusted.svg', 'unadjusted.png',
             'pango.json', 'pango.png', 'after.png']:
    shutil.copyfile(base / name, out / name)
shutil.copyfile(examples / 'C/mixed-replacement.svg', out / 'after.svg')
shutil.copyfile(examples / 'C/mixed-replacement.puml', out / 'after.puml')
protected = json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-R1/preservation-before.json').read_text())
for name, value in protected.items():
    p = Path(name)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == value['sha256']
    assert oct(stat.S_IMODE(p.stat().st_mode)) == value['mode']
(out / 'preservation.json').write_text(json.dumps(protected, indent=2) + '\n')
allowed = {'scripts/skill_factory/transactions/plantuml.py', 'tests/transaction-visualization.py',
           'docs/examples/transaction-01-vis-01/C/mixed-replacement.puml',
           'docs/examples/transaction-01-vis-01/C/mixed-replacement.svg'}
modified = []
for name, value in before.items():
    if not name.startswith(('docs/', 'scripts/', 'tests/')):
        continue
    p = Path(name)
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != value['sha256']:
        modified.append(name)
assert set(modified) == allowed, modified
assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only'])
assert subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip() == 'a222018fa50a3e1286a01f6da6c224a4dea242ed'
(out / 'targeted.json').write_text(json.dumps({
    'rendering': renders, 'svgCountPerRun': 14, 'svgDeterminism': 'PASS',
    'sourceDeterminismAndInputPreservation': 'PASS',
    'unchangedRegeneratedSVGs': 13, 'changedSVGs': changed,
    'unchangedEvidenceJSONs': 3, 'protectedHashAndModeCount': len(protected),
    'preexistingFilesChanged': sorted(modified), 'indexEmpty': True,
    'browser': {'status': 'NOT_RUN', 'reason': 'No browser is available'},
}, indent=2) + '\n')
# Diff against the actual pre-F01 worktree, not HEAD's pre-VIS renderer.
parts = []
for old, current in [('plantuml-before.py', 'scripts/skill_factory/transactions/plantuml.py'),
                     ('before.puml', 'docs/examples/transaction-01-vis-01/C/mixed-replacement.puml')]:
    p = subprocess.run(['diff', '-u', str(base / old), current], capture_output=True, text=True)
    assert p.returncode == 1
    parts.append(p.stdout)
(out / 'layout.diff').write_text('\n'.join(parts))
print(json.dumps({'checks': {k: v['exit'] for k,v in results.items()},
                  'changed': sorted(modified), 'deterministicSVGs': 14,
                  'protectedFiles': len(protected)}, indent=2))
