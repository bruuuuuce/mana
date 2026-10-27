"""Prepare explicit test authority; exercise public CLI, never replace native admission."""
import copy
import difflib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path('/Users/zel/projects/mana');MOM=Path('/Users/zel/projects/mana-o-matic');WORK=Path('/private/tmp/mana-exact-001-dev')
spec=importlib.util.spec_from_file_location('exact',ROOT/'scripts/lib/exact_repair.py');x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
package=x.load(MOM/'docs/reports/evidence/MOM-E2E-002/proposal.json')
review=(MOM/'docs/reports/evidence/MOM-E2E-002/review.txt').read_text()
assert json.loads(review.split('Exact review content (JSON, authoritative replacement string):\n',1)[1])==package
source=package['edit']['path'];snapshot=package['handoff']['snapshot']
expected_diff=''.join(difflib.unified_diff(snapshot[source]['text'].splitlines(keepends=True),package['edit']['replacement'].splitlines(keepends=True),fromfile='a/'+source,tofile='b/'+source))
assert '\n\n'+expected_diff+'\nExact review content' in review
assert 'Result SHA-256: '+x.digest(package['edit']['replacement'].encode()) in review
baseline=x.load(MOM/'docs/reports/evidence/MOM-E2E-001/baseline-r2.json')['commands'][-1]
for name,record in snapshot.items():
 assert x.digest(x.read_file(MOM/'tests/fixtures/mom-e2e-001'/name))==record['sha256']
rt=x.runtime()

def prepare(label):
 base=Path(tempfile.mkdtemp(prefix='mana-exact-'+label+'-',dir='/private/tmp')).resolve()
 dest=base/'fixture';out=base/'outputs';host=base/'authority'
 for p in (dest,out,host):p.mkdir(mode=0o700)
 for name,record in snapshot.items():
  p=dest/name;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(x.read_file(MOM/'tests/fixtures/mom-e2e-001'/name))
 ds=dest.stat()
 r={'schema':'mana.exact-request/v1','id':label,'proposal':copy.deepcopy(package),'destination':str(dest),
    'destination_identity':{'device':ds.st_dev,'inode':ds.st_ino},'outputs':str(out),
    'result_sha256':x.digest(package['edit']['replacement'].encode()),
    'verification':{'catalog':'java-jdk-pair/v1','test_path':package['handoff']['regression_test'],'main_class':'example.ShippingPolicyTest'},
    'budget':{'attempts':1,'verification_commands':4,'timeout_seconds':20,'total_seconds':180,'output_bytes':16384,'file_bytes':1048576},
    'runtime':rt,'authorization_reference':label+'-host-test','protected_files':[str(MOM/'tests/fixtures/mom-e2e-001'/p) for p in snapshot]+[str(MOM/'AGENTS.md'),str(MOM/'config/mana-reference.json'),str(ROOT/'config/divination-domains.tsv')],
    'provider':'none','operation':'repair-verify',
    'baseline':{'test_exit':baseline['exit_code'],'stdout_sha256':x.digest(baseline['stdout'].encode())}}
 g={'schema':'mana.exact-host-grant/v1','id':r['authorization_reference'],'authority':'explicit-public-fixture-test','approved':True,'request_sha256':x.identity(r),'expires_at':int(time.time())+1800,'uses':1}
 return base,r,g

def invoke(base,r,g,missing=False,entry='repair'):
 rp=base/'request.json';gp=base/'authority/grant.json'
 rp.write_bytes(x.encoded(r));rp.chmod(0o600)
 if not missing:gp.write_bytes(x.encoded(g));gp.chmod(0o600)
 argv=['/bin/bash',str(ROOT/('scripts/mana-'+entry+'.sh')),'--exact-request',str(rp),'--host-grant',str(gp),'--provider','none','--json']
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
 return {'argv':argv,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'result':json.loads(p.stdout)}

def inventory(dest):
 return {str(p.relative_to(dest)):('symlink:'+os.readlink(p) if p.is_symlink() else x.digest(x.read_file(p))) for p in dest.rglob('*') if p.is_symlink() or p.is_file()}

if __name__=='__main__':
 results=[]
 for case in ('missing','denied','other-effects','proposal','base','result','destination','revision','budget','symlink','test-edit','commands'):
  base,r,g=prepare('negative-'+case);dest=Path(r['destination'])
  if case=='denied':g['approved']=False
  if case=='other-effects':g['request_sha256']='0'*64
  if case=='proposal':r['proposal']['edit']['replacement']+='changed'
  if case=='base':(dest/source).write_text('stale')
  if case=='result':r['result_sha256']='0'*64
  if case=='destination':r['destination']=str(MOM/'tests/fixtures/mom-e2e-001')
  if case=='revision':r['runtime']['base_revision']='0'*40;r['runtime']=copy.deepcopy(r['runtime']);rt=x.runtime()
  if case=='budget':r['budget']['attempts']=0
  if case=='symlink':(dest/source).unlink();(dest/source).symlink_to(MOM/'tests/fixtures/mom-e2e-001'/source)
  if case=='test-edit':
   r['proposal']['edit']['path']=package['handoff']['regression_test']
   p=r['proposal'];p['fingerprint']=x.identity({k:v for k,v in p.items() if k!='fingerprint'})
  if case=='commands':r['verification']['argv']=['/bin/sh','-c','exit 0']
  before=inventory(dest)
  res=invoke(base,r,g,missing=case=='missing');res['case']=case
  assert res['exit']==2 and res['result']['status']=='BLOCKED',res
  assert res['result']['applied'] is False and not res['result']['application_started']
  assert inventory(dest)==before and not list(Path(r['outputs']).iterdir()) and not (base/'authority/grant.json.used').exists()
  res['no_execution_effects']=True;results.append(res)
 (WORK/'native-negatives.json').write_text(json.dumps(results,indent=2)+'\n')
 print([(r['case'],r['result']['stop_reason']) for r in results])
 # Prepare only. The positive candidate is launched separately once gates are checked.
 base,r,g=prepare('MANA-EXACT-001-positive')
 rp=base/'request.json';gp=base/'authority/grant.json'
 rp.write_bytes(x.encoded(r));rp.chmod(0o600);gp.write_bytes(x.encoded(g));gp.chmod(0o600)
 (WORK/'positive-location.json').write_text(json.dumps({'root':str(base),'request':str(rp),'grant':str(gp),'outputs':r['outputs'],'destination':r['destination']},indent=2)+'\n')
 (WORK/'proposal-equivalence.json').write_text(json.dumps({'proposal_fingerprint':package['fingerprint'],'review_matches':True,'replacement_sha256':r['result_sha256'],'snapshot_matches_original':True,'diff':expected_diff,'proposal_file_sha256':x.digest(x.read_file(MOM/'docs/reports/evidence/MOM-E2E-002/proposal.json'))},indent=2)+'\n')
