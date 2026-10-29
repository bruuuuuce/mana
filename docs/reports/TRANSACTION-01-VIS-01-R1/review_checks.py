import sys,json,hashlib,subprocess,re,stat,copy
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path.cwd()/'scripts'))
from skill_factory.transactions.plantuml import render_integrated,render
from skill_factory.transactions.wait_dependencies import build_report
base=Path('/private/tmp/mana-vis-r1-20261023'); details={}; paths=[]
for s in 'ABC':
 inp=Path('docs/examples/transaction-01-t02-s02')/s
 dest=Path('docs/examples/transaction-01-vis-01')/s
 report=json.loads((inp/'wait-dependency.json').read_bytes())
 scenario=json.loads((inp/'scenario.json').read_bytes());assert report['scenario']==scenario
 raw={i['id']:(inp/'inputs'/(i['id']+'.json')).read_bytes() for i in report['inputs']}
 before=copy.deepcopy((report,raw));views=render_integrated(report,raw)
 assert views==render_integrated(report,raw);assert before==(report,raw)
 assert json.loads(views['evidence.json'])['validatedS02']==report
 assert json.loads(views['evidence.json'])['relationRefs']=={'R'+str(i):r for i,r in enumerate(report['crossLayerRelations'],1)}
 for name,source in views.items():
  assert (dest/name).read_bytes()==source.encode(),(s,name)
  if not name.endswith('.puml'):continue
  p=base/(s+'-'+name);p.write_text(source);paths.append(str(p))
  assert source.count('@startuml')==source.count('@enduml')==1
  assert not re.search(r'(?im)^\s*!|https?://|%load|\[\[',source)
 for participant in scenario['participants']:
  timeline=json.loads(raw[participant['input']]);source=views['sequence-'+participant['id']+'.puml'];cursor=0
  for event in timeline['transactionModel']['events']:
   if event['kind'] in {'FRAME_ENTER','FRAME_EXIT','RESOURCE_LEAF_CALL','UNRESOLVED_CALL'}:continue
   token=str(event['sequence'])+' '+event['kind']+' '+event.get('entity','')
   cursor=source.index(token,cursor)+len(token)
  for o in timeline['observations']:
   assert 'JDBC '+o['id'] in source
   assert 'context='+o['transactionContext']['physicalId'] in source
 for cut in report['assessment']['cuts']:
  source=views['database-'+cut['cut']+'.puml'];edges=[e for e in report['databaseGraph']['edges'] if e['cut']==cut['cut']]
  assert source.count('-[#B03030,dashed]->')==len(edges)
  for edge in edges:
   claim=next(c for c in report['claims'] if c['id']==edge['claim'])
   assert 'DEPENDENCY '+claim['id'] in source
   assert 'candidate='+claim['candidate'] in source
   assert all(p in source for p in claim['premises'])
 current=build_report(raw,scenario)
 details[s]={'sourceAndEvidenceExact':True,'deterministicAndReadOnly':True,'eventsOperationsEdgesPremisesChecked':True,'assessment':report['assessment'],'currentProof':current['assessment']}
args=['java','-Djava.awt.headless=true','-XX:-UsePerfData','-jar','/Applications/plantuml-1.2024.8.jar']
for option in ['-checkonly','-tsvg']:
 p=subprocess.run(args+[option]+paths,capture_output=True,text=True);assert p.returncode==0,p.stderr;details[option]={'exit':p.returncode,'sources':len(paths)}
for p in paths:
 p=Path(p);s=p.name[0];svg=p.with_suffix('.svg'); original=Path('docs/examples/transaction-01-vis-01')/s/p.name[2:];original=original.with_suffix('.svg')
 assert svg.read_bytes()==original.read_bytes(),str(original)
original=json.loads((base/'preservation-before.json').read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256'] and oct(stat.S_IMODE(Path(p).stat().st_mode))==v['mode'] for p,v in original.items())
delivery=json.loads(Path('docs/reports/TRANSACTION-01-VIS-01-results.json').read_bytes())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in delivery['deliveryHashes'].items())
assert subprocess.check_output(['git','diff','--name-only','--','scripts/skill_factory/transactions']).decode().strip()=='scripts/skill_factory/transactions/plantuml.py'
assert not subprocess.check_output(['git','diff','--cached','--name-only'])
details['preservation']={'preexistingFiles':13,'hashAndMode':'PASS','visDeliveryHashes':'PASS','semanticEnginesUnchanged':True,'indexEmpty':True}
(base/'targeted.json').write_text(json.dumps(details,indent=2));print(json.dumps(details,indent=2))
