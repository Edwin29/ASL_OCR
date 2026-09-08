"""Stage the candidate in a new Laptop C: diagnostic root; never overwrite integration."""
import base64,hashlib,importlib.util,io,json,pathlib,sys,time,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    for package in ['device-runtime','book-scanner','document-parser']:
        for sub in ['src','tests']:
            for p in (ROOT/package/sub).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                    z.write(p,p.relative_to(ROOT).as_posix())
        z.write(ROOT/package/'pyproject.toml',package+'/pyproject.toml')
        for p in (ROOT/package).glob('*.example.toml'):
            z.write(p,p.relative_to(ROOT).as_posix())
    for relative in ['book-scanner/experiment_inputs/scanner_video_v3a2_model_manifest.json',
                     'book-scanner/models/page_number_digit_v1.onnx']:
        z.write(ROOT/relative,relative)
    for p in (ROOT/'tools/windows').glob('*'):
        if p.is_file() and p.suffix in {'.py','.ps1','.bat'}:
            z.write(p,p.relative_to(ROOT).as_posix())
    for p in (ROOT/'hardware/stm32/kitel2026final').rglob('*'):
        if p.is_file() and p.suffix in {'.c','.h','.ioc'}:
            z.write(p,p.relative_to(ROOT).as_posix())
run_id='h123-correction-'+str(time.time_ns())
root=r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics'+'\\'+run_id
code=f'''import base64,io,json,pathlib,sys,zipfile,os,subprocess
root=pathlib.Path({root!r})
root.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(io.BytesIO(base64.b64decode({base64.b64encode(buf.getvalue()).decode()!r}))) as z:
    z.extractall(root)
env=os.environ.copy()
env['PYTHONDONTWRITEBYTECODE']='1'
env['PYTHONPATH']=os.pathsep.join(str(root/p/'src') for p in ['device-runtime','book-scanner','document-parser'])
tests={sys.argv[1:]!r}
groups={{}}
for test in tests:
    package,relative=test.split('/',1)
    groups.setdefault(package,[]).append(relative)
results=[]
for package,items in groups.items():
    result=subprocess.run([sys.executable,'-B','-m','pytest','-q','--tb=short','-p','no:cacheprovider','--basetemp',str(root/('pytest-temp-'+package)),*items],cwd=root/package,env=env,capture_output=True,text=True,timeout=45)
    results.append({{'package':package,'returncode':result.returncode,'output':result.stdout+'\\n'+result.stderr}})
(root/'tests.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({{'root':str(root),'interpreter':sys.executable,'returncode':max(r['returncode'] for r in results),'results':results}}))
'''
result=json.loads(helper.remote_python(code))
(HERE/('stage-'+run_id+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
(HERE/'latest-stage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
