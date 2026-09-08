"""Existing targeted tests; only a new C: diagnostic temp root is writable."""
import pathlib,datetime,pytest,json,sys,os
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION')
os.chdir(root)
temp=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics')/('software-audit-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
assert not temp.exists()
files=['device-runtime/tests/unit/'+n for n in ['test_reading_audio.py','test_reading_audio_adapters.py','test_stm_serial.py','test_application.py','test_hold_repeat.py','test_laptop_acceptance.py','test_book_scanner_runtime.py']]
files+=['book-scanner/tests/unit/video/'+n for n in ['test_sources.py','test_opaque_identity.py','test_engine_v3a5.py']]
print(json.dumps({'test_files':files,'new_temp_root':str(temp),'python':sys.executable}))
rc=pytest.main(['-q','-p','no:cacheprovider','--import-mode=importlib','--basetemp='+str(temp),*files])
print('DIAGNOSTIC_PYTEST_EXIT='+str(rc))
raise SystemExit(rc)
