import concurrent.futures, copy, hashlib, json, os, stat, subprocess, sys
from pathlib import Path
import xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path.cwd()/'scripts'))
from skill_factory.transactions.plantuml import render_integrated
out=Path('docs/reports/TRANSACTION-01-VIS-01-R2'); tmp=Path('/private/tmp/mana-vis-r2'); tmp.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
protected=json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-R1/preservation-before.json').read_text())
for name,v in protected.items():
 p=Path(name); assert sha(p)==v['sha256'] and oct(stat.S_IMODE(p.stat().st_mode))==v['mode'],name
(out/'preservation.json').write_text(json.dumps(protected,indent=2)+'\n')
checks=json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-R1/checks.json').read_text())
def check(item):
 name,v=item; env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'); r=subprocess.run(v['command'],capture_output=True,text=True,env=env)
 (out/(name+'.log')).write_text(r.stdout+r.stderr)
 return name,dict(command=v['command'],exit=r.returncode,tail=(r.stdout+r.stderr)[-500:])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=dict(pool.map(check,checks.items()))
(out/'checks.json').write_text(json.dumps(results,indent=2)+'\n')
assert all(v['exit']==0 for v in results.values()),results
examples=Path('docs/examples/transaction-01-vis-01'); hashes=json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-R1/reviewed-hashes.json').read_text())
print('R1 hash shape',str(hashes)[:200])
render_checks=[]
for run in range(2):
 paths=[]
 for s in 'ABC':
  inp=Path('docs/examples/transaction-01-t02-s02')/s; report=json.loads((inp/'wait-dependency.json').read_bytes())
  raw={i['id']:(inp/'inputs'/(i['id']+'.json')).read_bytes() for i in report['inputs']}; before=copy.deepcopy((report,raw)); views=render_integrated(report,raw)
  assert views==render_integrated(report,raw) and before==(report,raw)
  evidence=json.loads(views['evidence.json']); assert evidence['validatedS02']==report
  assert evidence['relationRefs']=={'R'+str(i):r for i,r in enumerate(report['crossLayerRelations'],1)}
  for name,source in views.items():
   p=tmp/str(run)/s/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source)
   assert p.read_bytes()==(examples/s/name).read_bytes(),str(p)
   if name.endswith('.puml'):paths.append(str(p))
 assert len(paths)==14
 for opt in ['-checkonly','-tsvg']:
  r=subprocess.run(['java','-Djava.awt.headless=true','-XX:-UsePerfData','-jar','/Applications/plantuml-1.2024.8.jar',opt]+paths,capture_output=True,text=True)
  render_checks.append(dict(run=run,option=opt,exit=r.returncode,stderr=r.stderr)); assert r.returncode==0
 for name in paths:
  p=Path(name).with_suffix('.svg'); ET.parse(p); rel=p.relative_to(tmp/str(run));assert p.read_bytes()==(examples/rel).read_bytes()
  if run: assert p.read_bytes()==(tmp/'0'/rel).read_bytes()
  else:
   png=out/(rel.parts[0]+'-'+p.stem+'.png');subprocess.run(['rsvg-convert','--background-color=white',str(p),'-o',str(png)],check=True)
f01=Path('docs/reports/TRANSACTION-01-VIS-01-F01')
for kind in ['before','after']:
 root=ET.parse(f01/(kind+'.svg')).getroot(); print(kind,root.attrib)
 subprocess.run(['rsvg-convert','--background-color=white',str(f01/(kind+'.svg')),'-o',str(out/(kind+'.png'))],check=True)
assert (f01/'after.svg').read_bytes()==(examples/'C/mixed-replacement.svg').read_bytes()
assert (f01/'before.puml').read_text().replace('MIXED / RESUME_REQUIRES_COMPLETION','MIXED / RESUME_REQUIRES_\\nCOMPLETION')==(examples/'C/mixed-replacement.puml').read_text()
# Compare all R1 reviewed artifacts, with only the documented F01 changes allowed.
changed=[]
for name,v in hashes.items():
 expected=v['sha256'] if isinstance(v,dict) else v
 if sha(Path(name))!=expected:changed.append(name)
allowed={'scripts/skill_factory/transactions/plantuml.py','tests/transaction-visualization.py','docs/examples/transaction-01-vis-01/C/mixed-replacement.puml','docs/examples/transaction-01-vis-01/C/mixed-replacement.svg'}
assert set(changed)==allowed,changed
assert subprocess.check_output(['git','diff','--name-only','--','scripts/skill_factory/transactions']).decode().strip()=='scripts/skill_factory/transactions/plantuml.py'
assert not subprocess.check_output(['git','diff','--cached','--name-only'])
(out/'targeted.json').write_text(json.dumps(dict(rendering=render_checks,diagrams=14,determinism='PASS',inputPreservation='PASS',relationIdentity='PASS',otherDiagramsUnchangedFromR1=13,changedSinceR1=changed,protectedFiles=13,browser='NOT_RUN'),indent=2)+'\n')
print('PASS: 113 tests + 23 governance; 14 SVG x2; preservation, identity, determinism')
