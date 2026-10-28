import importlib.util,json,sys,tempfile,time
from pathlib import Path
root=Path('/Users/zel/projects/mana'); out=Path('/private/tmp/mana-exact-001-dev')
spec=importlib.util.spec_from_file_location('exact',root/'scripts/lib/exact_repair.py');x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
base=Path(tempfile.mkdtemp(prefix='mana-exact-native-qualification-',dir='/private/tmp')).resolve()
dest=base/'copy';outputs=base/'outputs';dest.mkdir(mode=0o700);outputs.mkdir(mode=0o700);(outputs/'classes').mkdir(mode=0o700)
src='src/main/java/example/Example.java';test='src/test/java/example/ExampleTest.java'
for p,t in [(src,'package example; public final class Example { public static int value() { return 1; } }\n'),(test,'package example; public final class ExampleTest { public static void main(String[] args) { if (Example.value()!=1) throw new AssertionError(); System.out.println("PASS native qualification"); } }\n'),('README.md','public disposable native probe\n')]:
 f=dest/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(t)
r={'destination':str(dest),'outputs':str(outputs),'proposal':{'edit':{'path':src},'handoff':{'snapshot':{src:{},test:{},'README.md':{}}}},'protected_files':[str(root/'scripts/mana-repair.sh'),str(root/'README.md'),'/Users/zel/projects/mana-o-matic/AGENTS.md'],'budget':{'timeout_seconds':5,'output_bytes':16384,'file_bytes':1048576},'verification':{'catalog':'java-jdk-pair/v1','test_path':test,'main_class':'example.ExampleTest'}}
(outputs/'control.json').write_text('native-protected-receipt')
r['runtime']=x.runtime()
results={'root':str(base),'policy':x.policy(r),'python':sys.executable,'boundary':x.probe(r)}
if x.passed(results['boundary']):
 for i,argv in enumerate(x.commands(r)):
  results['jdk-'+str(i)]=x.supervise(r,argv,'jdk-'+str(i))
  if not x.passed(results['jdk-'+str(i)]):break
(out/'native-qualification.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
print(json.dumps(results,indent=2))
