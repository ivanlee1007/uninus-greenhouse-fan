"""A/B/C card-only layouts: actual browser RED, geometry and editor."""
from pathlib import Path
import hashlib
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
    source=Path(os.environ.get('CARD_TEST_SOURCE',str(ROOT/'www/uninus-greenhouse-fan-card.js')))
    page.add_script_tag(path=str(source))
    page.evaluate('''()=>{
      window.calls=[];window.queue=[];window.defer=false;window.events=0;
      window.saved={entry_id:'g',layout:'1',lock_readings_right:true,items:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i}))};
      window.snap={entry_id:'g',control_mode:'auto',revision:1,policy_revision:0,policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},devices:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i,name:'Fan '+i})),runtime:{},bindings:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}]))};
      const states={};for(let i=1;i<=4;i++){states['fan.f'+i]={state:'on',attributes:{}};states['sensor.t'+i]={state:i===4?'unavailable':'-10.5',attributes:{unit_of_measurement:'°C',device_class:'temperature'}};states['sensor.h'+i]={state:i===4?'unknown':'100.0',attributes:{unit_of_measurement:'%',device_class:'humidity'}}}
      window.h={user:{is_admin:true},states,callWS:async m=>{calls.push(m);if(m.type.endsWith('/groups'))return [{entry_id:'g',name:'Greenhouse',loaded:true}];return defer?new Promise(r=>queue.push(r)):structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);card.style.width='640px';card.setConfig(saved);card.hass=h;
      window.reopen=()=>{window.editor?.remove();window.editor=document.createElement('uninus-greenhouse-fan-card-editor');editor.addEventListener('config-changed',e=>{events++;window.draft=structuredClone(e.detail.config)});document.body.append(editor);editor.setConfig(saved);editor.hass=h};
      document.querySelector('#save').onclick=()=>{saved=structuredClone(draft);card.setConfig(saved);reopen()};
      window.measure=()=>{const s=card.shadowRoot,rect=n=>{let r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,cx:r.x+r.width/2,cy:r.y+r.height/2}};return {columns:getComputedStyle(s.querySelector('.fans')).gridTemplateColumns.split(' ').length,overflow:Math.max(...[s.querySelector('.card'),...s.querySelectorAll('.fan-item,.device-hero,.live-status,.live-line,.live-line strong,.controls')].map(n=>n.scrollWidth-n.clientWidth)),fans:[...s.querySelectorAll('.fan-item')].map(n=>({hero:rect(n.querySelector('.device-hero')),scene:rect(n.querySelector('.scene')),status:rect(n.querySelector('.live-status')),fields:[...n.querySelectorAll('.live-line')].map(rect),fonts:[...n.querySelectorAll('.live-line strong')].map(n=>parseFloat(getComputedStyle(n).fontSize))}))}};
      reopen();
    }''')
    page.wait_for_function('card.snapshot && editor.snapshot && !card.loading && !editor.loading')
    probe=page.evaluate('''()=>({select:!!editor.shadowRoot.querySelector('[data-config="readings_layout"]'),selected:editor.shadowRoot.querySelector('[data-config="readings_layout"]')?.value,migrated:card.config.readings_layout,geometry:measure()})''')
    (OUT/'layouts-first-probe.json').write_text(json.dumps(probe,indent=2),encoding='utf-8')
    assert probe['select'],'Missing native editor A/B/C layout select'
    assert probe['selected']==probe['migrated']=='split',probe
    f=probe['geometry']['fans'][0]
    assert abs(f['scene']['cx']-(f['hero']['x']+f['hero']['width']*.25))<1,f
    assert abs(f['status']['cx']-(f['hero']['x']+f['hero']['width']*.75))<1,f
    growth=[]
    for width in (500,640,900,1080):
        page.evaluate('''w=>{card.style.width=w+'px';card.setConfig({...saved,readings_layout:'columns'})}''',width)
        page.wait_for_function('card.snapshot && !card.loading')
        growth.append({'width':width,'viewport':page.viewport_size['width'],'measurement':page.evaluate('measure()')})
    (OUT/'layouts-font-probe.json').write_text(json.dumps(growth,indent=2),encoding='utf-8')
    assert growth[-1]['measurement']['fans'][0]['fonts'][0]>growth[0]['measurement']['fans'][0]['fonts'][0]+5,growth
    f=growth[-1]['measurement']['fans'][0]
    assert abs(f['scene']['cx']-(f['hero']['x']+(f['hero']['width']-24)/6))<1,f
    assert abs(f['fields'][0]['cx']-f['hero']['cx'])<1,f
    assert abs(f['fields'][1]['cx']-(f['hero']['right']-(f['hero']['width']-24)/6))<1,f
    # Editor: initially selected, one event/change, Save/reopen, off/on memory, fresh hass.
    editor=page.locator('uninus-greenhouse-fan-card-editor')
    select=editor.get_by_label('風扇與溫濕度排版',exact=True)
    check=editor.get_by_label('溫濕度固定在風扇右側',exact=True)
    editor_cases=[]
    for choice in ('compact','columns','split'):
        before=page.evaluate('events')
        select.select_option(choice)
        assert page.evaluate('events')==before+1
        assert page.evaluate('draft.readings_layout')==choice
        for enabled in (False,True):
            before=page.evaluate('events')
            if not enabled:page.evaluate("window.staleSelect=editor.shadowRoot.querySelector('[data-config=readings_layout]')")
            check.set_checked(enabled)
            assert page.evaluate('events')==before+1
            if not enabled:
                page.evaluate("editor.handleChange({type:'change',target:staleSelect})")
                assert page.evaluate('events')==before+1,'Detached select may not emit stale config'
            assert select.count()==int(enabled)
            assert page.evaluate('draft.readings_layout')==choice
            assert page.evaluate('typeof draft.lock_readings_right')=='boolean'
        page.locator('#save').click()
        page.wait_for_function('card.snapshot && editor.snapshot && !card.loading && !editor.loading')
        assert select.input_value()==choice
        select.focus()
        page.evaluate('''()=>{window.selectRef=editor.shadowRoot.activeElement;for(let i=0;i<18;i++)editor.hass={...h}}''')
        assert page.evaluate('editor.shadowRoot.activeElement===selectRef')
        page.evaluate('editor.load()')
        page.wait_for_function('!editor.loading')
        assert page.evaluate('editor.shadowRoot.activeElement===selectRef'),'Native select focus lost on refresh'
        assert select.count()==1 and select.input_value()==choice
        editor_cases.append(choice)
    # All layouts are global; fixed two columns stay two, no hidden overflow.
    matrix=[]
    for theme in ('light','dark'):
        for layout in ('auto','1','2'):
            for width in (320,390,500,640,720,900,1080):
                for count in (1,2,4):
                    for reading_layout in ('compact','columns','split'):
                        page.evaluate('''a=>{const [theme,layout,width,count,readings_layout]=a;card.style.width=width+'px';card.setConfig({...saved,theme,layout,readings_layout,lock_readings_right:true,items:saved.items.slice(0,count)})}''',[theme,layout,width,count,reading_layout])
                        page.wait_for_function('card.snapshot && !card.loading')
                        r=page.evaluate('measure()')
                        case={'theme':theme,'layout':layout,'width':width,'devices':count,'readings_layout':reading_layout}
                        assert len(r['fans'])==count and r['overflow']<=1,(case,r)
                        if layout=='2':assert r['columns']==2,(case,r)
                        texts=page.locator('uninus-greenhouse-fan-card').locator('.live-status').all_inner_texts()
                        assert all('-10.5' in x and '100.0' in x and '°C' in x and '%' in x for x in texts[:min(count,3)]),(case,texts)
                        if count==4:assert texts[3].count('—')==2,texts
                        for f in r['fans']:
                            if reading_layout=='compact':
                                assert abs(f['status']['x']-f['scene']['right']-20)<1,(case,f)
                                assert abs((f['scene']['x']+f['status']['right'])/2-f['hero']['cx'])<1,(case,f)
                            elif reading_layout=='split':
                                assert abs(f['scene']['cx']-(f['hero']['x']+f['hero']['width']*.25))<1,(case,f)
                                assert abs(f['status']['cx']-(f['hero']['x']+f['hero']['width']*.75))<1,(case,f)
                                assert abs(f['scene']['cy']-f['status']['cy'])<1,(case,f)
                            else:
                                narrow=width-34<=440 or layout=='2' and width-34<=630
                                if narrow:
                                    assert abs(f['scene']['cx']-(f['hero']['x']+f['hero']['width']*.25))<1,(case,f)
                                    assert all(abs(line['cx']-(f['hero']['x']+f['hero']['width']*.75))<1 for line in f['fields']),(case,f)
                                    assert f['fields'][1]['y']>=f['fields'][0]['bottom'],(case,f)
                                else:
                                    assert abs(f['scene']['cx']-(f['hero']['x']+(f['hero']['width']-24)/6))<1,(case,f)
                                    assert abs(f['fields'][0]['cx']-f['hero']['cx'])<1,(case,f)
                                    assert abs(f['fields'][1]['cx']-(f['hero']['right']-(f['hero']['width']-24)/6))<1,(case,f)
                                assert 13<=f['fonts'][0]<=36 and 14<=f['fonts'][1]<=40,(case,f)
                        matrix.append({**case,'columns':r['columns'],'overflow':r['overflow'],'fonts':r['fans'][0]['fonts']})
    # Same card and viewport; force only one field narrower, proving local units.
    page.evaluate('''()=>{card.style.width='900px';card.setConfig({...saved,layout:'1',readings_layout:'columns',lock_readings_right:true})}''')
    page.wait_for_function('!card.loading && card.snapshot')
    local_before=page.evaluate('measure().fans[0]')
    page.evaluate("card.shadowRoot.querySelector('.live-line').style.width='90px'")
    local_after=page.evaluate('measure().fans[0]')
    assert local_after['fonts'][0]<local_before['fonts'][0] and local_after['fonts'][1]==local_before['fonts'][1],(local_before,local_after)
    assert local_after['hero']==local_before['hero']
    # Reference bytes were copied from the approved external artifacts before editing.
    provenance=json.loads((ROOT/'tests/fixtures/approved-readings-provenance.json').read_text())
    reference_cases=[];baseline_cases=[]
    geometry_js='''()=>{const root=card.shadowRoot,base=root.querySelector('.card').getBoundingClientRect();const rect=n=>{const r=n.getBoundingClientRect();return [r.x-base.x,r.y-base.y,r.width,r.height]};return Object.fromEntries(['.card','.header','.global','.fan-item','.device-title','.device-hero','.scene','.fan-machine','.live-status','.live-line','.controls','.controls button','.action-icon','.card-note'].map(s=>[s,[...root.querySelectorAll(s)].map(rect)]))}'''
    reference=browser.new_page(viewport={'width':1400,'height':1400})
    actual=browser.new_page(viewport={'width':1400,'height':1400})
    actual.add_script_tag(path=str(source))
    actual.evaluate('''()=>{window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);window.install=a=>{card.style.width=a.width+'px';card.setConfig({...a.config,readings_layout:a.choice});card.hass={user:{is_admin:true},states:a.states,callWS:async m=>m.type.endsWith('/groups')?[{entry_id:a.config.entry_id,name:'Demo',loaded:true}]:structuredClone(a.snapshot)}}}''')
    for key,choice in zip('abc',('compact','columns','split')):
        frozen=ROOT/'tests/fixtures'/f'approved-readings-{key}.html'
        assert hashlib.sha256(frozen.read_bytes()).hexdigest()==provenance['sha256'][key]
        reference.close()
        reference=browser.new_page(viewport={'width':1400,'height':1400})
        reference.set_content(frozen.read_text(encoding='utf-8'))
        reference.wait_for_function('card.snapshot && !card.loading')
        for theme in ('light','dark'):
            for width in (320,390,500,640,720,900,1080):
                for count in (1,2,4):
                    reference.evaluate('''a=>{card.style.width=a.width+'px';applyPreview({theme:a.theme,count:a.count})}''',{'width':width,'theme':theme,'count':count})
                    reference.wait_for_function('card.snapshot && !card.loading')
                    data=reference.evaluate('''()=>({config:card.config,states:fakeHass.states,snapshot:view})''')
                    actual.evaluate('install',dict(data,width=width,choice=choice))
                    actual.wait_for_function('card.snapshot && !card.loading')
                    expected=reference.evaluate(geometry_js);received=actual.evaluate(geometry_js)
                    case={'choice':choice,'theme':theme,'width':width,'count':count}
                    if key in 'ac':
                        for selector in expected:
                            assert len(expected[selector])==len(received[selector]),(case,selector)
                            for a,b in zip(expected[selector],received[selector]):
                                assert max(abs(x-y) for x,y in zip(a,b))<=1,(case,selector,a,b)
                    else:
                        # B deliberately changes readout typography/height, not card chrome.
                        for selector in ('.header','.global','.device-title','.controls button','.action-icon'):
                            for a,b in zip(expected[selector],received[selector]):
                                assert abs(a[0]-b[0])<=1 and abs(a[2]-b[2])<=1 and abs(a[3]-b[3])<=1,(case,selector,a,b)
                        for a,b in zip(expected['.scene'],received['.scene']):
                            assert abs(a[0]-b[0])<=1 and abs(a[2]-b[2])<=1,(case,a,b)
                        for a,b in zip(expected['.live-line'],received['.live-line']):
                            assert abs(a[0]+a[2]/2-b[0]-b[2]/2)<=1,(case,a,b)
                    reference_cases.append(case)
                    if key=='a':
                        reference.evaluate('card.setConfig({...card.config,lock_readings_right:false})')
                        reference.wait_for_function('!card.loading')
                        data=reference.evaluate('''()=>({config:card.config,states:fakeHass.states,snapshot:view})''')
                        actual.evaluate('install',dict(data,width=width,choice='columns'))
                        actual.wait_for_function('!card.loading')
                        old_geometry=reference.evaluate(geometry_js);off_geometry=actual.evaluate(geometry_js)
                        for selector in old_geometry:
                            assert len(old_geometry[selector])==len(off_geometry[selector]),(case,selector)
                            for a,b in zip(old_geometry[selector],off_geometry[selector]):
                                assert max(abs(x-y) for x,y in zip(a,b))<=.02,(case,selector,a,b)
                        baseline_cases.append(case)
    reference.close();actual.close()
    # Three polls and 18 hass updates for EACH layout preserve roots, controls,
    # animation objects, open state, keyboard focus, scroll and a live drag.
    page.evaluate('''()=>{editor.remove();window.wrap=document.createElement('div');wrap.style.cssText='height:750px;overflow:auto;width:1000px';document.body.append(wrap);wrap.append(card)}''')
    cycles=[]
    for choice in ('compact','columns','split'):
        page.evaluate('''choice=>{defer=false;card.style.width='900px';card.setConfig({...saved,items:saved.items,layout:'2',readings_layout:choice,lock_readings_right:true})}''',choice)
        page.wait_for_function('card.snapshot && !card.loading')
        page.evaluate('''()=>{card.expanded=true;card.shadowRoot.querySelector('.global').open=true;card.editThreshold('temperature_on',31);wrap.scrollTop=20;window.scrollRef=wrap.scrollTop;window.refs=[...card.shadowRoot.querySelectorAll('.fan-item,.device-hero,.scene,.fan-machine,.rotor,.rotor svg,.controls,.controls button,.action-icon,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')];window.animations=[...card.shadowRoot.querySelectorAll('.rotor')].map(n=>n.getAnimations()[0]);window.removals=0;window.flips=0;window.observer=new MutationObserver(rs=>{for(const r of rs){if(r.type==='attributes'&&refs.includes(r.target))flips++;for(const n of r.removedNodes)if(refs.some(x=>n===x||n.contains?.(x)))removals++}});observer.observe(card.shadowRoot,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});defer=true}''')
        slider=page.locator('uninus-greenhouse-fan-card').locator('#temperature_on')
        slider.focus()
        box=slider.bounding_box()
        page.mouse.move(box['x']+box['width']*.55,box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']*.65,box['y']+box['height']/2,steps=3)
        start_drag=page.evaluate('card.thresholdDraft.values.temperature_on')
        for cycle in range(3):
            page.clock.run_for(5000);page.wait_for_function('queue.length===1')
            for tick in range(6):page.evaluate('''v=>{h.states['sensor.t1'].state=String(v);card.hass={...h}}''',27+tick/10)
            assert '27.5' in page.locator('uninus-greenhouse-fan-card').locator('.live-status').first.inner_text()
            page.evaluate('queue.shift()(structuredClone(snap))')
            page.wait_for_function('!card.loading')
            r=page.evaluate('''()=>({identity:[...card.shadowRoot.querySelectorAll('.fan-item,.device-hero,.scene,.fan-machine,.rotor,.rotor svg,.controls,.controls button,.action-icon,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')].every((n,i)=>n===refs[i]),animations:[...card.shadowRoot.querySelectorAll('.rotor')].every((n,i)=>n.getAnimations()[0]===animations[i]),focused:card.shadowRoot.activeElement?.id==='temperature_on',expanded:card.expanded&&card.shadowRoot.querySelector('.global').open,scroll:wrap.scrollTop===scrollRef,removals,disabledFlips:flips})''')
            assert r['identity'] and r['animations'] and r['focused'] and r['expanded'] and r['scroll'] and r['removals']==r['disabledFlips']==0,(choice,r)
            cycles.append({'choice':choice,'cycle':cycle,**r})
        page.mouse.move(box['x']+box['width']*.8,box['y']+box['height']/2,steps=5)
        page.mouse.up()
        final_drag=page.evaluate('card.thresholdDraft.values.temperature_on')
        assert final_drag>start_drag,(choice,start_drag,final_drag)
        page.evaluate('observer.disconnect();defer=false')
    # All layouts reject pending/error/unloaded UI scopes without sending writes.
    safety=[];invalid_readings=[]
    for choice in ('compact','columns','split'):
        page.evaluate('''choice=>{card.style.width='320px';card.setConfig({...saved,items:saved.items,layout:'2',readings_layout:choice,lock_readings_right:true})}''',choice)
        page.wait_for_function('card.snapshot && !card.loading')
        for fault in ('pending','error','unloaded'):
            r=page.evaluate('''async fault=>{const snapshot=card.snapshot,id=card.resolvedId,before=calls.length;if(fault==='pending')card.operation={};if(fault==='error')card.error='Synthetic read failure';if(fault==='unloaded'){card.snapshot=null;card.resolvedId=''}card.render();const disabled=[...card.shadowRoot.querySelectorAll('.controls button,.mode-switch')].every(n=>n.disabled),manual=card.canManual('fan.f1','on'),global=card.canSetControlMode();await card.manual('fan.f1','on');await card.setControlMode('manual');card.operation=null;card.error='';card.snapshot=snapshot;card.resolvedId=id;card.render();return {disabled,manual,global,backend_calls:calls.length-before}}''',fault)
            assert r['disabled'] and not r['manual'] and not r['global'] and r['backend_calls']==0,(choice,fault,r)
            safety.append({'choice':choice,'fault':fault,**r})
        page.evaluate('window.originalStates=structuredClone(h.states)')
        for value in ('unknown','unavailable','wrong-units'):
            page.evaluate('''v=>{for(let i=1;i<=4;i++){h.states['sensor.t'+i].state=v==='wrong-units'?'-10.5':v;h.states['sensor.h'+i].state=v==='wrong-units'?'100.0':v;if(v==='wrong-units'){h.states['sensor.t'+i].attributes.unit_of_measurement='°F';h.states['sensor.h'+i].attributes.unit_of_measurement='watts'}}card.hass={...h}}''',value)
            assert all(x.count('—')==2 for x in page.locator('uninus-greenhouse-fan-card').locator('.live-status').all_inner_texts())
            assert page.evaluate('measure().overflow')<=1,(choice,value)
            invalid_readings.append({'choice':choice,'value':value,'overflow':page.evaluate('measure().overflow')})
        page.evaluate('h.states=originalStates;card.hass={...h}')
    writes=page.evaluate("calls.filter(x=>!x.type.endsWith('/get')&&!x.type.endsWith('/groups'))")
    assert writes==[] and errors==[],(writes,errors)
    report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'matrix':matrix,'geometry_cases':len(matrix),'editor_choices':editor_cases,'reference_cases':reference_cases,'baseline_cases':baseline_cases,'growth':growth,'local_field_resize':{'before':local_before,'after':local_after},'cycles':cycles,'simulated_ui_safety_states':safety,'invalid_readings':invalid_readings,'browser_version':browser.version,'backend_writes':writes,'errors':errors,'approved_fixtures':provenance,'authorized_B_difference':'Field-relative numeric fonts 13–36 / 14–40 px, smaller units/labels; track centers, scene size and chrome remain approved. Increased readout height may move controls vertically. A/C match all measured full-card/control rectangles.','scope':'Actual custom elements in isolated browser, synthetic dashboard Save/reopen, not live HA or hosted CI'}
    (OUT/'layouts-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print(json.dumps({'layouts':'passed','matrix_cases':len(matrix),'reference_cases':len(reference_cases),'baseline_cases':len(baseline_cases),'editor_choices':editor_cases,'poll_cycles':len(cycles),'backend_writes':writes}))
