import importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
old=HERE.parent/'software-diagnostic-20260908'
spec=importlib.util.spec_from_file_location('helper',old/'collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
data=json.loads((old/'raw-evidence.json').read_text(encoding='utf-8'))
def selected(value):
    if isinstance(value,dict):
        return {k:(v if k in {'operator_preview_enabled','profile','camera_snapshot_timeout_seconds','opaque_identity_max_collection_ms'} else selected(v)) for k,v in value.items() if k in {'operator_preview_enabled','profile','camera_snapshot_timeout_seconds','opaque_identity_max_collection_ms'} or isinstance(v,(dict,list))}
    if isinstance(value,list):return [selected(v) for v in value if isinstance(v,(dict,list))]
print(json.dumps({'recorded_profiles':{k:selected(v) for k,v in data['configs'].items()}},indent=2))
code='''import json,sys,asl_device,book_scanner,document_parser,inspect,sounddevice as sd
print(json.dumps({'python':sys.executable,'imports':[m.__file__ for m in (asl_device,book_scanner,document_parser)],'audio_version':sd.__version__,'raw_output_signature':str(inspect.signature(sd.RawOutputStream)),'devices':list(sd.query_devices()),'default_device':list(sd.default.device),'hostapis':list(sd.query_hostapis())}))'''
result=json.loads(helper.remote_python(code))
(HERE/'runtime-context.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
