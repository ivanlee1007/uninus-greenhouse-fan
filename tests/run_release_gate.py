"""Run repository release gates, recording only actual subprocess results."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/evidence'
OUT.mkdir(exist_ok=True)
HA=os.environ.get('HA_TEST_PYTHON', str(ROOT/'.venv-ha/bin/python'))
MODERN=os.environ.get('HA_MODERN_TEST_PYTHON', str(ROOT/'.venv-ha-modern/bin/python'))
BROWSER=os.environ.get('BROWSER_TEST_PYTHON', sys.executable)
commands={
    'offline_python':[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],
    'native_ha_legacy':[HA,'-m','unittest','discover','-s','tests_ha','-v'],
    'native_ha_modern':[MODERN,'-m','unittest','discover','-s','tests_ha','-v'],
    'node':['node','--test','tests/test_card.mjs'],
    'browser_card':[BROWSER,'tests/verify_card_browser.py'],
    'browser_control':[BROWSER,'tests/verify_control_browser.py'],
    'browser_subtitle':[BROWSER,'tests/verify_subtitle_browser.py'],
    'browser_threshold':[BROWSER,'tests/verify_threshold_browser.py'],
    'compile':[sys.executable,'-m','compileall','-q','custom_components/uninus_greenhouse_fan'],
    'node_source_syntax':['node','--check','www/uninus-greenhouse-fan-card.js'],
    'node_bundle_syntax':['node','--check','custom_components/uninus_greenhouse_fan/card.js'],
    'diff_check':['git','diff','--check'],
}
results={}
for name,cmd in commands.items():
    result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
    output=result.stdout+result.stderr
    (OUT/f'0.5.1-{name}.log').write_text(output,encoding='utf-8')
    match=re.search(r'Ran (\d+) tests|tests (\d+)',output)
    results[name]={'exit_code':result.returncode,'tests':int(next(x for x in match.groups() if x is not None)) if match else None,'log':f'tests/evidence/0.5.1-{name}.log'}
    print(name,json.dumps(results[name]),flush=True)
    if result.returncode:
        print(output[-16000:],flush=True)

runtime_probe = "import sys,platform,json,hashlib,inspect,importlib.metadata as m; from pathlib import Path; from homeassistant.components.input_number import InputNumber; packages={d.metadata['Name']:d.version for d in m.distributions()}; print(json.dumps({'executable':sys.executable,'python':platform.python_version(),'os':platform.platform(),'homeassistant':m.version('homeassistant'),'input_number_source_sha256':hashlib.sha256(Path(inspect.getfile(InputNumber)).read_bytes()).hexdigest(),'input_number_mro':[c.__name__ for c in InputNumber.__mro__],'packages':packages,'packages_sha256':hashlib.sha256(json.dumps(packages,sort_keys=True).encode()).hexdigest()}))"
runtimes = {name:json.loads(subprocess.check_output([executable,'-c',runtime_probe],cwd=ROOT,text=True)) for name,executable in [('legacy',HA),('modern',MODERN)]}
files=list((ROOT/'custom_components').rglob('*.json'))+[ROOT/'hacs.json']
for file in files: json.loads(file.read_text(encoding='utf-8'))
source=(ROOT/'www/uninus-greenhouse-fan-card.js').read_bytes()
bundle=(ROOT/'custom_components/uninus_greenhouse_fan/card.js').read_bytes()
assert source==bundle
assert json.loads((ROOT/'custom_components/uninus_greenhouse_fan/manifest.json').read_text())['version']=='0.5.1'
assert b"buildVersion(){return '0.5.1'}" in source
tracked=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(tracked)) if name and name!='docs/verification/0.5.1-thresholds.json'}
fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
threshold_file=OUT/'threshold-layout.json'
report={'version':'0.5.1','acceptance_complete':all(x['exit_code']==0 for x in results.values()),'known_limitations':['HA 2025.12 native input_number.set_value coerces booleans to floats before entity dispatch; strict native-service boolean rejection cannot be delivered without changing its global schema.','Integration-managed input_number entities are not editable native helper storage collection records; use Entities/Options for IDs/names and native value controls.','Isolated native-HA backend and browser fixtures only; native live Helpers/Entities UI was not exercised.'],'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'runtimes':runtimes,'gates':results,'json_files_validated':len(files),'shipped_copies_equal':True,'js_sha256':hashlib.sha256(source).hexdigest(),'js_bytes':len(source),'approved_a_fixture_sha256':hashlib.sha256((ROOT/'tests/fixtures/approved-threshold-a.html').read_bytes()).hexdigest(),'working_tree_content_fingerprint':fingerprint,'fingerprint_definition':'SHA256 of canonical path-to-SHA256 mapping for git tracked + nonignored untracked files, excluding this report','file_hashes':hashes,'scope':'Repository-only isolated actual HA/Store/ServiceRegistry and browser fixtures; no live HA, commit, push, release, deployment, restart or hardware actuation','threshold_browser':json.loads(threshold_file.read_text(encoding='utf-8')) if threshold_file.exists() else None,'passed':all(x['exit_code']==0 for x in results.values())}
(ROOT/'docs/verification/0.5.1-thresholds.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('file_hashes','threshold_browser','gates')},ensure_ascii=False))
sys.exit(0 if report['passed'] else 1)
