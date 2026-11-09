"""Bind shipped threshold styles to the user-approved offline V2 demo."""
from pathlib import Path
import hashlib
import json
import os
import re
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/approved-threshold-capsules-v2.html'
EXPECTED_SHA256 = '669da04b73891cc3f63170753d6b057a17e78dbaf05cbf25521a514644d55ac8'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_SHA256
approved = FIXTURE.read_text(encoding='utf-8')
source = Path(os.environ.get('CARD_TEST_SOURCE', str(ROOT / 'www/uninus-greenhouse-fan-card.js')))
# Same synthetic host/data, but the candidate must supply its own styles:
# remove the preview-only render override, never add the proposed CSS to it.
actual = re.sub(r'<script>.*?</script>', lambda _: '<script>' + source.read_text(encoding='utf-8') + '</script>', approved, count=1, flags=re.S)
actual = re.sub(r"\nconst original=customElements.*?\nconst snap=", "\nlet proposed=true,theme='light';\nconst snap=", actual, count=1, flags=re.S)
actual = re.sub(r"document.querySelector\('#design'\).onclick=.*?;\n</script>", '</script>', actual, count=1, flags=re.S)
MEASURE = r'''()=>{const root=document.querySelector('uninus-greenhouse-fan-card').shadowRoot;
const base=root.querySelector('.card').getBoundingClientRect();
const rect=n=>{const r=n.getBoundingClientRect();return [r.x-base.x,r.y-base.y,r.width,r.height]};
const read=n=>{const s=getComputedStyle(n),arrow=getComputedStyle(n,'::before');return {color:s.color,bg:s.backgroundColor,border:s.borderColor,radius:s.borderRadius,padding:s.padding,borderWidth:s.borderWidth,weight:s.fontWeight,decoration:s.textDecorationLine,font:parseFloat(s.fontSize),lineHeight:parseFloat(s.lineHeight),unit:getComputedStyle(n.querySelector('small')).color,arrow:arrow.content,arrowFont:parseFloat(arrow.fontSize),arrowWeight:arrow.fontWeight,arrowGap:arrow.marginRight}};
return {styles:[...root.querySelectorAll('.live-line strong')].map(read),geometry:Object.fromEntries(['.card','.header','.global','.fan-item','.device-hero','.scene','.live-line strong','.controls','.controls button'].map(s=>[s,[...root.querySelectorAll(s)].map(rect)])),overflow:Math.max(...[...root.querySelectorAll('.card,.fan-item,.device-hero,.live-line,.live-line strong')].map(n=>n.scrollWidth-n.clientWidth))}}
'''
OUT = Path(os.environ.get('CAPSULE_TEST_OUTPUT', str(ROOT / 'tests/evidence/threshold-capsules')))
OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None), headless=True)
    reference = browser.new_page(viewport={'width':1128,'height':1000})
    candidate = browser.new_page(viewport={'width':1128,'height':1000})
    errors = []
    for page in (reference,candidate):
        page.on('pageerror', lambda e: errors.append(str(e)))
    reference.set_content(approved)
    candidate.set_content(actual)
    for page in (reference,candidate):
        page.wait_for_function("document.querySelector('uninus-greenhouse-fan-card').snapshot && !document.querySelector('uninus-greenhouse-fan-card').loading")
    cases=[]
    for theme in ('light','dark'):
        for width in (360,420,760,1128):
            for page in (reference,candidate):
                page.set_viewport_size({'width':width,'height':1000})
                page.evaluate("t=>{theme=t;document.body.classList.toggle('dark',t==='dark');card.setConfig({...card.config,theme:t})}",theme)
                page.wait_for_function('card.snapshot && !card.loading')
            expected=reference.evaluate(MEASURE)
            received=candidate.evaluate(MEASURE)
            case={'theme':theme,'width':width}
            assert received['styles']==expected['styles'],(case,'approved numeric style mismatch',expected['styles'],received['styles'])
            for selector, rects in expected['geometry'].items():
                assert len(rects)==len(received['geometry'][selector])
                for a,b in zip(rects,received['geometry'][selector]):
                    assert max(abs(x-y) for x,y in zip(a,b))<=1,(case,selector,a,b)
            assert received['overflow']<=1,(case,received)
            cases.append(case)
            if width in (360,1128):
                for label,page in [('approved',reference),('shipped',candidate)]:
                    page.locator('uninus-greenhouse-fan-card').screenshot(path=str(OUT/f'{theme}-{width}-{label}.png'),animations='disabled')
    assert errors==[],errors
    browser.close()
report={'passed':True,'cases':cases,'approved_fixture_sha256':EXPECTED_SHA256,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'page_errors':errors,'scope':'Offline synthetic host; exact V2 numeric styles and <=1px card/control geometry; no live HA'}
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
