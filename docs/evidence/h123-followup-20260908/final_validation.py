"""Validate imports, complete source identity and tests after delta alignment."""
import importlib.util,json,pathlib,time
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
function=__import__('inspect').getsource(helper.source_hashes)
code='import pathlib,hashlib,json,sys,subprocess,os\n'+function+f'''
root=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION')
evidence=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION_RUNTIME\\demo-20260905\\diagnostics')/{('h123-followup-final-validation-'+str(time.time_ns()))!r}
evidence.mkdir(exist_ok=False)
env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
env['PYTHONPATH']=os.pathsep.join(str(root/p/'src') for p in ['device-runtime','book-scanner','document-parser'])
results=[]
for package,tests in [('device-runtime',['tests/unit','tests/integration']),('book-scanner',['tests/unit/video'])]:
    run=subprocess.run([sys.executable,'-B','-m','pytest','-q','--tb=short','-p','no:cacheprovider','--basetemp',str(evidence/('pytest-'+package)),*tests],cwd=root/package,env=env,capture_output=True,text=True,timeout=45)
    results.append({{'package':package,'returncode':run.returncode,'output':run.stdout+'\\n'+run.stderr}})
import asl_device,book_scanner,document_parser
result={{'source_root':str(root),'evidence':str(evidence),'python':sys.executable,'imports':[m.__file__ for m in [asl_device,book_scanner,document_parser]],'hashes':source_hashes(root),'tests':results,'old_environment_manifest_sha256':hashlib.sha256(pathlib.Path(r'C:\\ASL_OCR_INTEGRATION_RUNTIME\\demo-20260905\\integration-environment-manifest.json').read_bytes()).hexdigest()}}
(evidence/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
'''
result=json.loads(helper.remote_python(code))
local=helper.source_hashes(ROOT)
result['mismatches']=[p for p,v in local.items() if result['hashes'].get(p,{}).get('lf')!=v['lf']]
old=json.loads((HERE.parent/'software-diagnostic-20260908/laptop-evidence-inventory.json').read_text(encoding='utf-8'))
result['old_environment_manifest_unchanged']=old['environment_manifest_hash']==result['old_environment_manifest_sha256']
(HERE/'final-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='hashes'},indent=2))
