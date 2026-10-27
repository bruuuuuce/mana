import importlib.util,json
from pathlib import Path
w=Path('/private/tmp/mana-exact-001-dev')
s=importlib.util.spec_from_file_location('prep',w/'acceptance.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
base,r,g=p.prepare('negative-reserved-grant')
(base/'authority/grant.json.used').write_text('test reservation retained')
before=p.inventory(Path(r['destination']))
res=p.invoke(base,r,g)
assert res['exit']==2 and res['result']['stop_reason']=='AUTHORIZATION_CONSUMED'
assert p.inventory(Path(r['destination']))==before and not list(Path(r['outputs']).iterdir())
res['no_execution_effects']=True;res['case']='reserved-canonical-grant';res['synthetic_test_reservation']=True
(w/'reserved-grant.json').write_text(json.dumps(res,indent=2)+'\n')
print(res['result'])
