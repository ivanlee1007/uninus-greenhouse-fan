"""Opt-in right readings: real geometry, editor, and refresh identity."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/evidence'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser=p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None),headless=True)
    page=browser.new_page(viewport={'width':1400,'height':1400})
    page.clock.install()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<!doctype html><body><button id="save">Dashboard Save fixture</button></body>')
    page.add_script_tag(path=os.environ.get('CARD_TEST_SOURCE',str(ROOT/'www/uninus-greenhouse-fan-card.js')))
    page.evaluate('''()=>{
      window.calls=[];window.queue=[];window.defer=false;
      window.saved={entry_id:'g',layout:'2',items:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i}))};
      window.snap={entry_id:'g',control_mode:'auto',revision:1,policy_revision:0,policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},devices:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i,name:'Fan '+i})),runtime:{},bindings:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}]))};
      const states={};for(let i=1;i<=4;i++){states['fan.f'+i]={state:'on',attributes:{}};states['sensor.t'+i]={state:i===4?'unavailable':'-20.0',attributes:{unit_of_measurement:'°C',device_class:'temperature'}};states['sensor.h'+i]={state:i===4?'unavailable':'100.0',attributes:{unit_of_measurement:'%',device_class:'humidity'}}}
      window.h={user:{is_admin:true},states,callWS:async m=>{calls.push(m);if(m.type.endsWith('/groups'))return [{entry_id:'g',name:'Greenhouse',loaded:true}];return defer?new Promise(r=>queue.push(r)):structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);card.style.width='390px';card.setConfig(saved);card.hass=h;
      window.reopen=()=>{window.editor?.remove();window.editor=document.createElement('uninus-greenhouse-fan-card-editor');editor.addEventListener('config-changed',e=>window.draft=structuredClone(e.detail.config));document.body.append(editor);editor.setConfig(saved);editor.hass=h};
      document.querySelector('#save').onclick=()=>{saved=structuredClone(draft);card.setConfig(saved);reopen()};
      window.measure=()=>{const s=card.shadowRoot,rect=n=>{let r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};return {height:rect(s.querySelector('.card')).height,columns:getComputedStyle(s.querySelector('.fans')).gridTemplateColumns.split(' ').length,details:s.querySelectorAll('.device-details').length,badges:s.querySelectorAll('.badge').length,buttons:s.querySelectorAll('.controls button:enabled').length,overflow:Math.max(...[s.querySelector('.card'),...s.querySelectorAll('.fan-item,.device-hero,.live-status,.live-line strong,.controls')].map(n=>n.scrollWidth-n.clientWidth)),fans:[...s.querySelectorAll('.fan-item')].map(n=>({hero:rect(n.querySelector('.device-hero')),scene:rect(n.querySelector('.scene')),machine:rect(n.querySelector('.fan-machine')),status:rect(n.querySelector('.live-status')),lines:[...n.querySelectorAll('.live-line strong')].map(rect)}))}};
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    # First tracer: missing option must fail because narrow fixed-2 stacks.
    baseline=page.evaluate('measure()')
    page.evaluate('()=>card.setConfig({...saved,lock_readings_right:true})')
    page.wait_for_function('card.snapshot && !card.loading')
    enabled=page.evaluate('measure()')
    red={'baseline':baseline,'enabled':enabled,'build':page.evaluate("customElements.get('uninus-greenhouse-fan-card').buildVersion")}
    (OUT/'readings-first-probe.json').write_text(json.dumps(red,indent=2),encoding='utf-8')
    assert page.evaluate('card.config.readings_layout')=='split'
    assert all(abs(f['scene']['x']+f['scene']['width']/2-(f['hero']['x']+f['hero']['width']/4))<=1 and abs(f['status']['x']+f['status']['width']/2-(f['hero']['x']+3*f['hero']['width']/4))<=1 for f in enabled['fans']),red
    measurements=[]
    for theme in ('light','dark'):
        for layout in ('auto','1','2'):
            for width in (320,390,500,630,720,1080):
                for details in (True,False):
                    results={}
                    for lock in (False,True):
                        page.evaluate('''a=>{const [theme,layout,width,details,lock]=a;card.style.width=width+'px';card.setConfig({...saved,theme,layout,show_device_details:details,lock_readings_right:lock})}''',[theme,layout,width,details,lock])
                        page.wait_for_function('card.snapshot && !card.loading')
                        r=page.evaluate('measure()');results[str(lock)]=r
                        assert r['overflow']<=1,(theme,layout,width,details,lock,r)
                        assert r['details']==(4 if details else 0) and r['badges']==4 and r['buttons']==8,r
                        if layout=='2':assert r['columns']==2,r
                        if lock:
                            text=page.locator('uninus-greenhouse-fan-card').locator('.live-status').all_inner_texts()
                            assert all('-20.0' in x and '100.0' in x and '°C' in x and '%' in x for x in text[:3]),text
                            assert text[3].count('—')==2,text
                            for f in r['fans']:
                                assert abs(f['scene']['x']+f['scene']['width']/2-(f['hero']['x']+f['hero']['width']/4))<=1,(width,layout,f)
                                assert abs(f['status']['x']+f['status']['width']/2-(f['hero']['x']+3*f['hero']['width']/4))<=1,(width,layout,f)
                                assert abs(f['scene']['y']+f['scene']['height']/2-f['status']['y']-f['status']['height']/2)<=1,f
                                assert f['status']['x']>=f['scene']['right']-1,(width,layout,f)
                                assert f['status']['y']<f['scene']['bottom'] and f['scene']['y']<f['status']['bottom'],f
                                assert f['machine']['x']>=f['hero']['x']-1 and f['machine']['right']<=f['status']['x']+1,f
                                for line in f['lines']:
                                    assert line['right']<=f['hero']['right']+1 and line['x']>=f['scene']['right']-1,f
                    if layout=='2' and width in (390,500):assert results['True']['height']<results['False']['height'],results
                    measurements.append({'theme':theme,'layout':layout,'width':width,'details':details,'legacy_height':results['False']['height'],'locked_height':results['True']['height'],'reduction':results['False']['height']-results['True']['height']})
    # Omitted and explicit false retain exactly the legacy geometry.
    for layout in ('auto','1','2'):
        for width in (320,390,500,630,720,1080):
            page.evaluate('''a=>{card.style.width=a[1]+'px';card.setConfig({...saved,layout:a[0]})}''',[layout,width]);page.wait_for_function('card.snapshot && !card.loading')
            omitted=page.evaluate('measure()')
            page.evaluate('()=>card.setConfig({...card.config,lock_readings_right:false})');page.wait_for_function('card.snapshot && !card.loading')
            assert page.evaluate('measure()')==omitted
    page.evaluate('reopen()');page.wait_for_function('editor.snapshot && !editor.loading')
    check=page.locator('uninus-greenhouse-fan-card-editor').get_by_label('溫濕度固定在風扇右側',exact=True)
    assert not check.is_checked()
    box=check.bounding_box()
    assert 0<box['width']<=24 and 0<box['height']<=24,box
    for checked in (True,False):
        before_click=page.evaluate('calls.length')
        check.set_checked(checked)
        assert page.evaluate('calls.length')==before_click,'Display checkbox must not call backend'
        assert page.evaluate('typeof draft.lock_readings_right')=='boolean'
        assert page.evaluate('draft.lock_readings_right')==checked
        page.locator('#save').click();page.wait_for_function('editor.snapshot && card.snapshot && !card.loading && !editor.loading')
        assert check.is_checked()==checked
    # Initial false -> clicked true -> clicked false all survive Save/reopen.
    page.evaluate('()=>card.setConfig({...card.config,lock_readings_right:true})')
    page.wait_for_function('card.snapshot && !card.loading')
    # End on enabled mode; three real scheduled polls and 18 hass updates.
    page.evaluate('''()=>{editor.remove();const s=card.shadowRoot;s.querySelector('.global').open=true;card.expanded=true;card.editThreshold('temperature_on',31);window.refs=[...s.querySelectorAll('.fan-item,.rotor,.controls button,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')];window.animations=[...s.querySelectorAll('.rotor')].map(n=>n.getAnimations()[0]);window.focus=s.querySelector('[data-save]');focus.focus();window.removals=0;window.disabledFlips=0;new MutationObserver(rs=>{for(const r of rs){if(r.type==='attributes'&&refs.includes(r.target))disabledFlips++;for(const n of r.removedNodes)if(refs.some(x=>n===x||n.contains?.(x)))removals++}}).observe(s,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});defer=true}''')
    cycles=[]
    for cycle in range(3):
        page.clock.run_for(5000);page.wait_for_function('queue.length===1')
        for tick in range(6):page.evaluate('''v=>{h.states['sensor.t1'].state=String(v);card.hass={...h}}''',27+tick/10)
        assert '27.5' in page.locator('uninus-greenhouse-fan-card').locator('.live-status').first.inner_text()
        page.evaluate('()=>queue.shift()(structuredClone(snap))');page.wait_for_function('!card.loading')
        r=page.evaluate('''()=>({identity:[...card.shadowRoot.querySelectorAll('.fan-item,.rotor,.controls button,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')].every((n,i)=>n===refs[i]),animations:[...card.shadowRoot.querySelectorAll('.rotor')].every((n,i)=>n.getAnimations()[0]===animations[i]),focused:card.shadowRoot.activeElement===focus,removals,disabledFlips})''')
        assert r['identity'] and r['animations'] and r['focused'] and r['removals']==r['disabledFlips']==0,r
        cycles.append(r)
    writes=page.evaluate("calls.filter(x=>!x.type.endsWith('/get')&&!x.type.endsWith('/groups'))")
    assert writes==[] and errors==[],(writes,errors)
    report={'measurements':measurements,'cycles':cycles,'round_trip':[False,True,False],'checkbox_backend_calls':0,'backend_writes':writes,'errors':errors,'scope':'Actual editor and card in synthetic dashboard Save/reopen host, not live HA storage UI','supported_minimum_card_width':320}
    (OUT/'readings-browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    browser.close()
print(json.dumps({'readings':'passed','geometry_cases':len(measurements)*2,'cycles':cycles,'backend_writes':writes}))
