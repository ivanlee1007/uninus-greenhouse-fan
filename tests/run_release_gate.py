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
BROWSER=os.environ.get('BROWSER_TEST_PYTHON', sys.executable)
commands={
    'offline_python':[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],
    'native_ha':[HA,'-m','unittest','discover','-s','tests_ha','-v'],
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
    (OUT/f'0.4.0-{name}.log').write_text(output,encoding='utf-8')
    match=re.search(r'Ran (\d+) tests|tests (\d+)',output)
    results[name]={'exit_code':result.returncode,'tests':int(next(x for x in match.groups() if x is not None)) if match else None,'log':f'tests/evidence/0.4.0-{name}.log'}
    print(name,json.dumps(results[name]),flush=True)
    if result.returncode:
        print(output[-16000:],flush=True)

files=list((ROOT/'custom_components').rglob('*.json'))+[ROOT/'hacs.json']
for file in files: json.loads(file.read_text(encoding='utf-8'))
source=(ROOT/'www/uninus-greenhouse-fan-card.js').read_bytes()
bundle=(ROOT/'custom_components/uninus_greenhouse_fan/card.js').read_bytes()
assert source==bundle
assert json.loads((ROOT/'custom_components/uninus_greenhouse_fan/manifest.json').read_text())['version']=='0.4.0'
assert b"buildVersion(){return '0.4.0'}" in source
tracked=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(tracked)) if name and name!='docs/verification/0.4.0-thresholds.json'}
fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
threshold_file=OUT/'threshold-layout.json'
report={'version':'0.4.0','head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'gates':results,'json_files_validated':len(files),'shipped_copies_equal':True,'js_sha256':hashlib.sha256(source).hexdigest(),'js_bytes':len(source),'approved_a_fixture_sha256':hashlib.sha256((ROOT/'tests/fixtures/approved-threshold-a.html').read_bytes()).hexdigest(),'working_tree_content_fingerprint':fingerprint,'fingerprint_definition':'SHA256 of canonical path-to-SHA256 mapping for git tracked + nonignored untracked files, excluding this report','file_hashes':hashes,'scope':'Repository-only isolated actual HA/Store/ServiceRegistry and browser fixtures; no live HA, commit, push, release, deployment, restart or hardware actuation','threshold_browser':json.loads(threshold_file.read_text(encoding='utf-8')) if threshold_file.exists() else None,'passed':all(x['exit_code']==0 for x in results.values())}
(ROOT/'docs/verification/0.4.0-thresholds.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('file_hashes','threshold_browser','gates')},ensure_ascii=False))
sys.exit(0 if report['passed'] else 1)
