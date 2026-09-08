"""Read-only assurance driver. Only new Desktop diagnostic artifacts are written."""
import hashlib, importlib.util, inspect, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = HERE.parent / 'software-diagnostic-20260908'
spec = importlib.util.spec_from_file_location('identity_helper', OLD / 'collect_identity.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

if sys.argv[1] == 'identity':
    code = ('import pathlib,hashlib,json,sys,asl_device,book_scanner,document_parser\n'
            + inspect.getsource(helper.source_hashes)
            + "\nprint(json.dumps({'interpreter':sys.executable,'imports':[m.__file__ for m in (asl_device,book_scanner,document_parser)],'hashes':source_hashes(pathlib.Path(r'C:\\ASL_OCR_INTEGRATION'))}))")
    laptop = json.loads(helper.remote_python(code))
    desktop = helper.source_hashes(ROOT)
    previous = json.loads((OLD/'source-identity-after.json').read_text())
    result = {'desktop':desktop,'laptop':laptop,
              'desktop_changed_since_diagnosis':[k for k in desktop if desktop[k] != previous['desktop'].get(k)],
              'laptop_changed_since_diagnosis':[k for k in laptop['hashes'] if laptop['hashes'][k] != previous['laptop']['hashes'].get(k)],
              'import_mismatch':[k for k in desktop if desktop[k]['lf'] != laptop['hashes'].get(k,{}).get('lf')]}
    (HERE/sys.argv[2]).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('desktop','laptop')}))
    print(json.dumps({'files':len(desktop),'interpreter':laptop['interpreter'],'imports':laptop['imports']}))
elif sys.argv[1] == 'probe':
    text = helper.remote_python((HERE/'probes.py').read_text(encoding='utf-8'))
    result = json.loads(text)
    (HERE/'laptop-probes.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
