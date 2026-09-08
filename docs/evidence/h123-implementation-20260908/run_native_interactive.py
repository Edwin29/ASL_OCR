import importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
root=json.loads((HERE/'latest-stage.json').read_text())['root']
script=(HERE/'native_probe.py').read_text(encoding='utf-8')
code=f'''import json,pathlib,subprocess,time,os,xml.etree.ElementTree as ET
root=pathlib.Path({root!r})
(root/'native_probe.py').write_text({script!r},encoding='utf-8')
name='ASL-H123-native-'+str(time.time_ns())
pythonw=pathlib.Path(r'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\pythonw.exe')
assert pythonw.is_file()
xml=ET.Element('Task',version='1.2',xmlns='http://schemas.microsoft.com/windows/2004/02/mit/task')
p=ET.SubElement(ET.SubElement(xml,'Principals'),'Principal',id='Author')
ET.SubElement(p,'UserId').text=os.environ['USERNAME']
ET.SubElement(p,'LogonType').text='InteractiveToken'
ET.SubElement(p,'RunLevel').text='LeastPrivilege'
settings=ET.SubElement(xml,'Settings')
ET.SubElement(settings,'DisallowStartIfOnBatteries').text='false'
ET.SubElement(settings,'StopIfGoingOnBatteries').text='false'
ET.SubElement(settings,'ExecutionTimeLimit').text='PT45S'
action=ET.SubElement(ET.SubElement(xml,'Actions',Context='Author'),'Exec')
ET.SubElement(action,'Command').text=str(pythonw)
ET.SubElement(action,'Arguments').text='-B "'+str(root/'native_probe.py')+'"'
ET.SubElement(action,'WorkingDirectory').text=str(root)
ET.ElementTree(xml).write(root/'native-task.xml',encoding='utf-16',xml_declaration=True)
def task(*args):return subprocess.run(['schtasks',*args],capture_output=True,text=True)
created=task('/Create','/TN',name,'/XML',str(root/'native-task.xml'))
if created.returncode:raise RuntimeError('interactive diagnostic task registration failed')
try:
    started=task('/Run','/TN',name)
    end=time.monotonic()+40
    while not (root/'native-result.json').exists() and time.monotonic()<end:time.sleep(.2)
    if (root/'native-result.json').exists():result=json.loads((root/'native-result.json').read_text())
    else:
        task('/End','/TN',name)
        result={{'status':'timed_out','start_record_exists':(root/'native-start.json').exists()}}
    result['task_name']=name
finally:
    task('/Delete','/TN',name,'/F')
print(json.dumps(result))
'''
result=json.loads(helper.remote_python(code))
(HERE/'native-interactive-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2))
print('event_count='+str(len(result.get('events',[]))))
