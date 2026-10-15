"""Approved demo A fidelity, accessible button labels, interaction and stable icons."""
from pathlib import Path
import hashlib
import json
import os
import re
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/evidence'
OUT.mkdir(exist_ok=True)
fixture=ROOT/'tests/fixtures/approved-button-icons-a.html'
approved=fixture.read_text(encoding='utf-8')
assert "buildVersion(){return '0.5.4'}" in approved, 'Approval fixture must remain frozen'
source=(ROOT/'www/uninus-greenhouse-fan-card.js').read_text(encoding='utf-8')
# The fixture stays independent; only the production test page receives the new bundle.
production=re.sub(r'<script>.*?</script>',lambda _: '<script>'+source+'</script>',approved,count=1,flags=re.S)
with sync_playwright() as p:
    edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser=p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None),headless=True)
    reference=browser.new_page()
    page=browser.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    cases=[]
    geometry="""()=>[...card.shadowRoot.querySelectorAll('.controls button[data-mode=on],.controls button[data-mode=off]')].map(e=>{const b=e.getBoundingClientRect(),s=e.querySelector('svg'),i=s.getBoundingClientRect();return {text:e.textContent.trim(),width:b.width,height:b.height,iconWidth:i.width,iconHeight:i.height,iconLeft:i.left-b.left,iconTop:i.top-b.top,gap:getComputedStyle(e).gap,hidden:s.getAttribute('aria-hidden'),focusable:s.getAttribute('focusable'),shape:s.innerHTML}})"""
    for theme in ('dark','light'):
        for layout in ('auto','1','2'):
            for width in (320,390,500,720,1080):
                for target,html in ((reference,approved),(page,production)):
                    target.set_viewport_size({'width':width,'height':1300})
                    target.goto('about:blank')
                    target.set_content(html)
                    target.wait_for_function('card.snapshot && !card.loading')
                    target.evaluate("([theme,layout])=>{applyTheme(theme);card.setConfig({...card.config,layout});card.hass=fakeHass}",[theme,layout])
                    target.wait_for_function('card.snapshot && !card.loading')
                expected,actual=reference.evaluate(geometry),page.evaluate(geometry)
                assert len(actual)==4
                max_delta=0
                for old,new in zip(expected,actual):
                    for key in ('width','height','iconWidth','iconHeight','iconLeft','iconTop'):
                        delta=abs(old[key]-new[key]);max_delta=max(max_delta,delta)
                        assert delta<=0.1,(theme,layout,width,key,old,new)
                    for key in ('text','gap','hidden','focusable','shape'):
                        assert old[key]==new[key],(key,old,new)
                    assert new['width']>=44 and new['height']>=44
                    assert new['iconWidth']==16 and new['iconHeight']==16
                    assert new['hidden']=='true' and new['focusable']=='false'
                host=page.locator('uninus-greenhouse-fan-card')
                assert host.get_by_role('button',name='開啟',exact=True).count()==2
                assert host.get_by_role('button',name='關閉',exact=True).count()==2
                assert page.evaluate('card.scrollWidth<=card.clientWidth+1')
                cases.append({'theme':theme,'layout':layout,'width':width,'max_geometry_delta':max_delta})
    # Exercise real controls only through the isolated request adapter.
    host.get_by_role('button',name='開啟',exact=True).first.click()
    page.wait_for_function("!card.operation && fakeHass.states['switch.demo_a'].state==='on'")
    assert '已開啟' in host.locator('.badge').first.inner_text()
    assert page.evaluate("card.snapshot.runtime['switch.demo_a'].mode")=='on'
    host.get_by_role('button',name='關閉',exact=True).first.click()
    page.wait_for_function("!card.operation && fakeHass.states['switch.demo_a'].state==='off'")
    assert '已關閉' in host.locator('.badge').first.inner_text()
    writes=page.evaluate("demoCalls.filter(x=>x.type.endsWith('/manual')).map(x=>({fan_entity:x.fan_entity,mode:x.mode}))")
    assert writes==[{'fan_entity':'switch.demo_a','mode':'on'},{'fan_entity':'switch.demo_a','mode':'off'}]
    # SVG and button ownership must survive ordinary same-scope snapshots.
    page.evaluate("window.originalIcon=card.shadowRoot.querySelector('.controls .action-icon');window.originalButton=originalIcon.closest('button');originalButton.focus()")
    for _ in range(3):
        page.evaluate('async()=>{card.hass={...fakeHass};await card.load({background:true})}')
        assert page.evaluate("originalIcon.isConnected && originalIcon===card.shadowRoot.querySelector('.controls .action-icon') && originalButton===card.shadowRoot.activeElement")
    page.set_viewport_size({'width':500,'height':1000})
    page.goto('about:blank');page.set_content(production);page.wait_for_function('card.snapshot && !card.loading')
    page.screenshot(path=str(OUT/'button-icons-a.png'),full_page=True)
    assert not errors,errors
    report={'passed':True,'approved_fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'geometry_cases':cases,'interaction':'on/off payloads and authoritative displayed state passed','refresh':'same SVG/button/focus through three background reads','errors':errors}
    (OUT/'button-icons.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'geometry_cases':len(cases),'maximum_delta':max(x['max_geometry_delta'] for x in cases),'errors':errors}))
    browser.close()
