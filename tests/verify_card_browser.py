"""Render the shipped Lovelace JS in a real Edge browser without accessing HA."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'www/uninus-greenhouse-fan-card.js'
OUT=ROOT/'tests/evidence'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    default_edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser_path=os.environ.get('HERMES_TEST_BROWSER') or (str(default_edge) if default_edge.exists() else None)
    browser=p.chromium.launch(executable_path=browser_path,headless=True)
    page=browser.new_page(viewport={'width':1530,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<!doctype html><html><body style="margin:0;background:#eee"></body></html>')
    page.add_script_tag(path=str(SCRIPT))
    page.evaluate('''() => {
      window.calls=[];
      const states={};for(let i=1;i<=4;i++){
        states['fan.f'+i]={entity_id:'fan.f'+i,state:i===3?'off':'on',attributes:{friendly_name:'第 '+i+' 區排熱風扇'}};
        states['sensor.t'+i]={entity_id:'sensor.t'+i,state:String(26+i),attributes:{device_class:'temperature',unit_of_measurement:'°C'}};
        states['sensor.h'+i]={entity_id:'sensor.h'+i,state:String(61+i),attributes:{device_class:'humidity',unit_of_measurement:'%'}};
      }
      window.snap={entry_id:'group-1',revision:1,devices:[1,2,3,4].map(i=>({device_id:'d'+i,name:'Configured '+i,fan_entity:'fan.f'+i})),policy:{temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120},bindings:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}])),runtime:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{mode:'auto',pending:null,reason:'threshold_not_met'}]))};
      window.fakeHass={states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return [{entry_id:'group-1',name:'Greenhouse',loaded:true}];if(msg.type.endsWith('/bind')){if(msg.expected_revision!==snap.revision)throw Error('conflict');snap.bindings[msg.fan_entity]={temperature_entity:msg.temperature_entity,humidity_entity:msg.humidity_entity};snap.revision++}if(msg.type.endsWith('/manual'))snap.runtime[msg.fan_entity].mode=msg.mode;return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.appendChild(card);card.style.display='block';card.style.width='720px';card.setConfig({type:'custom:uninus-greenhouse-fan-card',entry_id:'group-1',name:'排熱風扇控制',items:[1,2,3,4].map(i=>({fan_entity:'fan.f'+i,name:'第 '+i+' 區排熱風扇'})),layout:'auto',theme:'dark'});card.hass=fakeHass;
    }''')
    page.wait_for_function("document.querySelector('uninus-greenhouse-fan-card').snapshot?.revision===1")
    # Computed styles, not class names: output feedback alone controls rotation/color.
    visual_checks=[]
    for theme in ('dark','light'):
        for output,sensors in [('off','healthy'),('on','healthy'),('unknown','healthy'),('unavailable','healthy'),('missing','healthy'),('on','absent'),('on','unavailable'),('on','missing')]:
            page.evaluate('''(args)=>{
              const [theme,output,sensors]=args;
              window.visual=document.createElement('uninus-greenhouse-fan-card');document.body.appendChild(visual);
              const target='switch.uss_p130_f5_relay0',v=structuredClone(snap);
              v.devices=[{device_id:'p130',name:'P130',fan_entity:target}];
              v.bindings=sensors==='absent'?{}:{[target]:{temperature_entity:'sensor.t1',humidity_entity:'sensor.h1'}};
              const states={...fakeHass.states};if(output!=='missing')states[target]={state:output};
              if(sensors==='unavailable')states['sensor.t1']={state:'unavailable'};
              if(sensors==='missing')delete states['sensor.t1'];
              visual.setConfig({entry_id:'group-1',theme,items:[{device_id:'p130',fan_entity:'fan.stale'}]});
              visual.hass={states,callWS:async msg=>msg.type.endsWith('/groups')?[{entry_id:'group-1',loaded:true}]:v};
            }''',[theme,output,sensors])
            page.wait_for_function('visual.snapshot && !visual.loading')
            result=page.evaluate('''()=>{
              const s=visual.shadowRoot,r=s.querySelector('.rotor'),h=getComputedStyle(s.querySelector('.hub'));
              return {fill:getComputedStyle(s.querySelector('.rotor path')).fill,animation:getComputedStyle(r).animationPlayState,name:getComputedStyle(r).animationName,hub:h.backgroundImage,hubBorder:h.borderTopColor,selector:!!s.querySelector('select[data-group]'),enabled:!s.querySelector('button[data-mode="on"]').disabled,reason:s.querySelector('.reason').innerText};
            }''')
            running=output=='on'
            assert result['fill']==('rgb(220, 91, 86)' if running else 'rgb(138, 148, 153)'),(theme,output,sensors,result)
            assert result['animation']==('running' if running else 'paused'),(theme,output,sensors,result)
            assert result['selector'] is False,result
            assert result['enabled']==(output in ('on','off','unknown')),result
            assert result['hubBorder']==('rgb(241, 155, 139)' if running else 'rgb(171, 181, 186)'),result
            if output in ('missing','unavailable'):
                assert 'switch.uss_p130_f5_relay0' in result['reason'],result
                assert page.locator('uninus-greenhouse-fan-card').last.locator('a[href="/config/integrations"]').count()==1
            if running:
                page.emulate_media(reduced_motion='reduce')
                assert page.evaluate("()=>getComputedStyle(visual.shadowRoot.querySelector('.rotor')).animationName")=='none'
                assert page.evaluate("()=>getComputedStyle(visual.shadowRoot.querySelector('.rotor path')).fill")=='rgb(220, 91, 86)'
                page.emulate_media(reduced_motion='no-preference')
            visual_checks.append({'theme':theme,'output':output,'sensors':sensors,**result})
            page.evaluate('()=>visual.remove()')
    # Explicit two-column layout must remain two columns on narrow cards.
    fixed_geometry=[]
    for theme in ('dark','light'):
        for width in (390,500,520,630,720):
            page.evaluate('(args)=>{const [w,theme]=args;card.style.width=w+"px";card.setConfig({...card.config,layout:"2",theme});card.hass=fakeHass}',[width,theme])
            page.wait_for_function('card.snapshot && !card.loading')
            geometry=page.evaluate('''()=>{const s=card.shadowRoot,items=[...s.querySelectorAll('.fan-item')],top=items[0].getBoundingClientRect().top;return {row:items.filter(x=>Math.abs(x.getBoundingClientRect().top-top)<2).length,columns:getComputedStyle(s.querySelector('.fans')).gridTemplateColumns,minWidths:items.map(x=>getComputedStyle(x).minWidth),overflow:[s.querySelector('.card'),...items,...s.querySelectorAll('.controls,.live-status,.device-hero,button[data-mode]')].map(x=>x.scrollWidth-x.clientWidth),buttons:[...s.querySelectorAll('button[data-mode]')].map(x=>{const r=x.getBoundingClientRect();return {w:r.width,h:r.height}})}}''')
            assert geometry['row']==2,(width,theme,geometry)
            assert len(geometry['columns'].split())==2,geometry
            assert all(x=='0px' for x in geometry['minWidths']),geometry
            assert max(geometry['overflow'])<=1,(width,theme,geometry)
            assert all(x['h']>=44 and x['w']>=44 for x in geometry['buttons']),geometry
            before=page.evaluate('()=>calls.filter(x=>x.type.endsWith("/manual")).length')
            page.locator('uninus-greenhouse-fan-card').first.locator('button[data-mode="off"]').first.click()
            page.wait_for_function('(n)=>calls.filter(x=>x.type.endsWith("/manual")).length===n+1 && !card.operation',arg=before)
            fixed_geometry.append({'width':width,'theme':theme,**geometry})
    page.evaluate('()=>{snap.runtime["fan.f1"].mode="auto";card.load()}')
    page.evaluate('()=>{card.setConfig({...card.config,layout:"auto"});card.hass=fakeHass}')
    page.wait_for_function('card.snapshot && !card.loading')
    measurements={}
    for width,expected in [(390,1),(720,2),(1080,3),(1380,4)]:
        page.evaluate('(w)=>card.style.width=w+"px"',width)
        result=page.evaluate('''() => {let s=card.shadowRoot,items=[...s.querySelectorAll('.fan-item')],a=items[0].getBoundingClientRect(),g=s.querySelector('.global').getBoundingClientRect(),f=s.querySelector('.fans').getBoundingClientRect(),box=s.querySelector('.card');return {row:items.filter(x=>Math.abs(x.getBoundingClientRect().top-a.top)<2).length,above:g.bottom<=f.top,overflow:box.scrollWidth-box.clientWidth,width:card.getBoundingClientRect().width,readings:items[0].querySelector('.live-status').innerText}}''')
        assert result['row']==expected,(width,result)
        assert result['above'] and result['overflow']<=0,(width,result)
        measurements[width]=result
        if width in (720,1080):page.locator('uninus-greenhouse-fan-card').screenshot(path=str(OUT/f'actual-card-{width}.png'))
    page.evaluate('()=>{card.style.width="720px";card.shadowRoot.querySelector(".global summary").click()}')
    page.wait_for_function("card.shadowRoot.querySelector('.global').open")
    page.evaluate('()=>{card.hass={...fakeHass,states:{...fakeHass.states}}}')
    assert page.evaluate('()=>card.shadowRoot.querySelector(".global").open')
    page.locator('uninus-greenhouse-fan-card').locator('button[data-mode="off"]').first.click()
    page.wait_for_function("snap.runtime['fan.f1'].mode==='off'")
    assert page.locator('uninus-greenhouse-fan-card').locator('button.resume').count()==1
    page.evaluate('''() => {window.editor=document.createElement('uninus-greenhouse-fan-card-editor');document.body.appendChild(editor);editor.setConfig(card.config);editor.hass=fakeHass;window.events=[];editor.addEventListener('config-changed',e=>events.push(e.detail.config))}''')
    page.wait_for_function('editor.snapshot?.revision===1')
    assert page.locator('uninus-greenhouse-fan-card-editor').locator('.slot').count()==4
    first_name=page.locator('uninus-greenhouse-fan-card-editor').locator('input[data-field="name"]').first
    first_name.fill('測試名稱')
    assert first_name.input_value()=='測試名稱'
    assert page.evaluate('()=>events.at(-1).items[0].name')=='測試名稱'
    # Only integration-owned configured devices are selectable; editor never writes bindings.
    editor_locator=page.locator('uninus-greenhouse-fan-card-editor')
    assert editor_locator.locator('[data-field="temperature_entity"], [data-field="humidity_entity"], [data-action="apply"], [data-action="discard"]').count()==0
    assert 'revision' not in editor_locator.inner_text()
    editor_locator.locator('select[data-field="device_id"]').first.select_option('d2')
    assert page.evaluate("()=>editor.config.items[0].device_id")=='d2'
    assert page.evaluate("()=>editor.config.items[0].fan_entity")=='fan.f2'
    assert page.evaluate("()=>!calls.some(msg=>msg.type.endsWith('/bind'))")
    # Offline configured outputs remain choices but never enable manual actuation.
    page.evaluate("()=>{snap.devices.push({device_id:'offline',name:'Offline configured',fan_entity:'switch.offline'});editor.load()}")
    page.wait_for_function("editor.snapshot.devices.some(row=>row.device_id==='offline')")
    device_select=editor_locator.locator('select[data-field="device_id"]').first
    assert 'Offline configured' in device_select.inner_text()
    device_select.select_option('offline')
    assert page.evaluate("()=>editor.config.items[0].device_id")=='offline'
    assert page.evaluate("()=>!calls.some(msg=>msg.type.endsWith('/bind'))")
    # Discovery and lifecycle tests exercise the shipped custom elements in real DOM.
    page.evaluate("()=>{card.remove();editor.remove()}")
    page.evaluate(r'''() => {
      window.groupRows=[{entry_id:'group-1',name:'North greenhouse',loaded:true},{entry_id:'group-2',name:'South greenhouse',loaded:true}];
      window.mountProbe=(kind,rows,saved='',fail=false)=>{
        window.probe?.remove();window.probeCalls=[];window.probeEvents=[];
        window.probe=document.createElement('uninus-greenhouse-fan-card'+(kind==='editor'?'-editor':''));
        probe.addEventListener('config-changed',e=>probeEvents.push(e.detail.config));
        document.body.appendChild(probe);
        probe.setConfig({type:'custom:uninus-greenhouse-fan-card',entry_id:saved,name:'Discovery',items:[{fan_entity:'fan.f1',name:'Front'}]});
        probe.hass={states:fakeHass.states,callWS:async msg=>{
          probeCalls.push(msg);
          if(fail)throw Error('network unavailable');
          if(msg.type.endsWith('/groups'))return structuredClone(rows);
          return {...structuredClone(snap),entry_id:msg.entry_id};
        }};
      };
    }''')
    discovery_checks=[]
    for kind in ('card','editor'):
        tag='uninus-greenhouse-fan-card'+('-editor' if kind=='editor' else '')
        page.evaluate('(kind)=>mountProbe(kind,[groupRows[0]])',kind)
        page.wait_for_function('probe.snapshot?.entry_id==="group-1"')
        assert page.evaluate('()=>probe.resolvedId')=='group-1'
        assert page.locator(tag).locator('input[data-config="entry_id"]').count()==0
        if kind=='editor':
            assert page.evaluate('()=>probeEvents.at(-1).entry_id')=='group-1'
        page.evaluate('(kind)=>mountProbe(kind,groupRows)',kind)
        page.wait_for_function('probe.groups?.length===2 && !probe.loading')
        assert page.evaluate('()=>probe.snapshot===null')
        select=page.locator(tag).locator('select[data-group]')
        if kind=='editor':
            assert 'South greenhouse' in select.inner_text()
            select.select_option('group-2')
        else:
            assert select.count()==0
            assert '多個控制群組' in page.locator(tag).locator('[role="alert"]').inner_text()
            page.evaluate('()=>probe.setConfig({...probe.config,entry_id:"group-2"})')
        page.wait_for_function('probe.snapshot?.entry_id==="group-2"')
        if kind=='editor':
            assert page.evaluate('()=>probeEvents.at(-1).entry_id')=='group-2'
        page.evaluate('(kind)=>mountProbe(kind,[])',kind)
        page.wait_for_function('probe.groups?.length===0 && !probe.loading')
        assert page.locator(tag).locator('a[href="/config/integrations"]').count()>=1
        for saved,unloaded in [('missing',False),('group-1',True)]:
            page.evaluate('(args)=>mountProbe(args.kind,args.unloaded?[{...groupRows[0],loaded:false},groupRows[1]]:groupRows,args.saved)',{'kind':kind,'saved':saved,'unloaded':unloaded})
            page.wait_for_function('!!probe.error && !probe.loading')
            assert page.evaluate('()=>probe.snapshot===null && probe.resolvedId===""')
            assert page.evaluate('(saved)=>probe.config.entry_id===saved',saved)
            assert page.evaluate('()=>probeCalls.every(msg=>msg.type.endsWith("/groups"))')
            if kind=='card':
                assert page.locator(tag).locator('button[data-mode]:enabled').count()==0
                page.evaluate('()=>probe.manual("fan.f1","on")')
                assert page.evaluate('()=>probeCalls.every(msg=>msg.type.endsWith("/groups"))')
            else:
                assert page.locator(tag).locator('select[data-field="device_id"]').is_disabled()
        page.evaluate('(kind)=>mountProbe(kind,[],"",true)',kind)
        page.wait_for_function('!!probe.error && !probe.loading')
        assert 'network unavailable' in page.locator(tag).locator('[role="alert"]').inner_text()
        assert page.locator(tag).get_by_text('尚無控制群組',exact=False).count()==0
        discovery_checks.append(kind+': single/multi/no/missing/unloaded/error passed')

    # Delayed editor read after scope switch cannot overwrite the new group's inventory.
    page.evaluate("()=>mountProbe('editor',groupRows,'group-1')")
    page.wait_for_function('!!probe.snapshot')
    page.evaluate(r'''() => {
      const original=probe.hass.callWS;
      probe.hass={...probe.hass,callWS:msg=>msg.type.endsWith('/get')&&msg.entry_id==='group-1'?new Promise(resolve=>window.completeRead=resolve):original(msg)};
      probe.load();
    }''')
    page.wait_for_function('typeof completeRead==="function"')
    editor_locator=page.locator('uninus-greenhouse-fan-card-editor')
    editor_locator.locator('input[data-field="name"]').fill('Pending display name')
    editor_locator.locator('select[data-group]').select_option('group-2')
    page.wait_for_function('probe.snapshot?.entry_id==="group-2"')
    page.evaluate('()=>completeRead({...snap,entry_id:"group-1",revision:99})')
    page.wait_for_timeout(20)
    assert page.evaluate('()=>probe.snapshot.entry_id==="group-2" && probe.snapshot.revision!==99')
    assert editor_locator.locator('input[data-field="name"]').input_value()=='Pending display name'

    # Delayed manual rejection after switching cannot show a stale error or reload.
    page.evaluate("()=>mountProbe('card',groupRows,'group-1')")
    page.wait_for_function('!!probe.snapshot')
    page.evaluate(r'''() => {
      const original=probe.hass.callWS;
      probe.hass={...probe.hass,callWS:msg=>msg.type.endsWith('/manual')?new Promise((resolve,reject)=>window.rejectManual=reject):original(msg)};
    }''')
    card_locator=page.locator('uninus-greenhouse-fan-card')
    card_locator.locator('button[data-mode="off"]').click()
    page.wait_for_function('typeof rejectManual==="function"')
    assert card_locator.locator('select[data-group]').count()==0
    page.evaluate('()=>probe.setConfig({...probe.config,entry_id:"group-2"})')
    page.wait_for_function('probe.snapshot?.entry_id==="group-2"')
    page.evaluate('()=>{window.beforeReject=probeCalls.length;rejectManual(Error("stale manual error"))}')
    page.wait_for_timeout(20)
    assert page.evaluate('()=>probe.error==="" && probeCalls.length===beforeReject')

    # Out-of-order snapshots and disconnect during read are ignored.
    for kind in ('card','editor'):
        page.evaluate('(kind)=>mountProbe(kind,groupRows,"group-1")',kind)
        page.wait_for_function('!!probe.snapshot')
        page.evaluate(r'''() => {
          let reads=0;
          probe.hass={...probe.hass,callWS:msg=>msg.type.endsWith('/groups')?Promise.resolve(groupRows):++reads===1?new Promise(resolve=>window.oldRead=resolve):Promise.resolve({...snap,revision:7})};
          probe.load();
        }''')
        page.wait_for_function('typeof oldRead==="function"')
        page.evaluate('()=>probe.load()')
        page.wait_for_function('probe.snapshot?.revision===7')
        page.evaluate('()=>{oldRead({...snap,revision:99});window.oldRead=undefined}')
        page.wait_for_timeout(20)
        assert page.evaluate('()=>probe.snapshot.revision===7')
        page.evaluate(r'''() => {
          probe.hass={...probe.hass,callWS:()=>new Promise(resolve=>window.disconnectRead=resolve)};
          probe.load();probe.remove();disconnectRead(groupRows);
        }''')
        page.wait_for_timeout(20)
        assert page.evaluate('()=>probe.snapshot===null && probe.loading===false')
    # YAML automatic re-resolution drops the old snapshot before a new group read.
    page.evaluate("()=>mountProbe('card',[groupRows[0]])")
    page.wait_for_function('probe.snapshot?.entry_id==="group-1"')
    page.evaluate(r'''() => {
      probe.hass={...probe.hass,callWS:msg=>{
        probeCalls.push(msg);
        if(msg.type.endsWith('/groups'))return Promise.resolve([groupRows[1]]);
        return new Promise(resolve=>window.resolveNextGroup=resolve);
      }};
      probe.load();
    }''')
    page.wait_for_function('probe.resolvedId==="group-2"')
    assert page.locator('uninus-greenhouse-fan-card').locator('button[data-mode]:enabled').count()==0
    page.evaluate('()=>probe.manual("fan.f1","on")')
    assert page.evaluate('()=>!probeCalls.some(msg=>msg.type.endsWith("/manual"))')
    page.evaluate('()=>resolveNextGroup({...snap,entry_id:"group-2"})')
    page.wait_for_function('probe.snapshot?.entry_id==="group-2"')

    # Disconnect must invalidate outstanding mutation completions too.
    for kind in ('card','editor'):
        page.evaluate('(kind)=>mountProbe(kind,groupRows,"group-1")',kind)
        page.wait_for_function('!!probe.snapshot')
        page.evaluate(r'''(kind) => {
          const original=probe.hass.callWS;
          probe.hass={...probe.hass,callWS:msg=>msg.type.endsWith('/groups')?original(msg):new Promise(resolve=>window.lateMutation=resolve)};
          if(kind==='editor'){probe.setItemField(0,'name','Detached display name');probe.load()}else probe.manual('fan.f1','off');
          window.detachedHtml=probe.shadowRoot.innerHTML;
        }''',kind)
        page.wait_for_function('typeof lateMutation==="function"')
        page.evaluate('()=>{window.detachedHtml=probe.shadowRoot.innerHTML;probe.remove();lateMutation({...snap,revision:99});window.lateMutation=undefined}')
        page.wait_for_timeout(20)
        assert page.evaluate('()=>probe.snapshot===null && probe.error==="" && probe.shadowRoot.innerHTML===detachedHtml')
        if kind=='editor':
            assert page.evaluate('()=>probe.config.items[0].name')=='Detached display name'
    # Manual-only relay: actual visible clicks, HA mocked, no hardware/network.
    page.evaluate('''() => {
      window.unboundCalls=[];
      const target='switch.uss_p130_f5_relay0';
      window.manualSnap={entry_id:'01M4TJESXTB1DRBYG80VTF3SNG',revision:0,devices:[{device_id:'ee34fec4b5b45cc882181801bbd4e71a',name:'Manual only',fan_entity:target}],policy:snap.policy,bindings:{},runtime:{}};
      window.manualCard=document.createElement('uninus-greenhouse-fan-card');
      document.body.appendChild(manualCard);
      manualCard.style.width='500px';
      manualCard.setConfig({entry_id:manualSnap.entry_id,layout:'2',items:[{device_id:'ee34fec4b5b45cc882181801bbd4e71a',fan_entity:target,name:'Manual-only relay'}]});
      manualCard.hass={states:{[target]:{state:'off',attributes:{}}},callWS:async msg=>{
        if(msg.type.endsWith('/groups'))return [{entry_id:manualSnap.entry_id,name:'Mock group',loaded:true}];
        if(msg.type.endsWith('/manual')){
          unboundCalls.push(msg);manualSnap.revision++;
          manualSnap.runtime[target]={mode:msg.mode,reason:msg.mode==='auto'?'unbound':'manual'};
        }
        return structuredClone(manualSnap);
      }};
    }''')
    page.wait_for_function('manualCard.snapshot?.revision===0 && !manualCard.loading')
    manual_locator=page.locator('uninus-greenhouse-fan-card').last
    assert manual_locator.locator('button[data-mode="on"]').is_enabled()
    assert '僅手動控制' in manual_locator.locator('.reason').inner_text()
    for mode in ('on', 'off'):
        manual_locator.locator(f'button[data-mode="{mode}"]').click()
        page.wait_for_function('(mode)=>manualCard.snapshot.runtime["switch.uss_p130_f5_relay0"].mode===mode',arg=mode)
        assert manual_locator.locator('button.resume').is_enabled()
    manual_locator.locator('button.resume').click()
    page.wait_for_function('manualCard.snapshot.runtime["switch.uss_p130_f5_relay0"].mode==="auto"')
    assert '自動未啟用' in manual_locator.locator('.reason').inner_text()
    assert manual_locator.locator('button.resume').count()==0
    assert page.evaluate('()=>unboundCalls.map(x=>[x.entry_id,x.fan_entity,x.mode])')==[
        ['01M4TJESXTB1DRBYG80VTF3SNG','switch.uss_p130_f5_relay0','on'],['01M4TJESXTB1DRBYG80VTF3SNG','switch.uss_p130_f5_relay0','off'],['01M4TJESXTB1DRBYG80VTF3SNG','switch.uss_p130_f5_relay0','auto']]
    manual_matrix=[]
    for theme,output in ((theme,output) for theme in ('dark','light') for output in ('on','off','unknown')):
        for sensors in ('absent','healthy','unavailable'):
            page.evaluate('''args=>{
              const [output,sensors,theme]=args,target='switch.uss_p130_f5_relay0';
              manualCard.setConfig({...manualCard.config,theme});
              manualSnap.bindings=sensors==='absent'?{}:{[target]:{temperature_entity:'sensor.sensor_8d_s0_batt',humidity_entity:'sensor.sensor_8d_s1_air4_vms_t_214'}};
              const states={...fakeHass.states,[target]:{state:output},'sensor.sensor_8d_s0_batt':{state:'27.7',attributes:{device_class:'temperature',unit_of_measurement:'°C'}},'sensor.sensor_8d_s1_air4_vms_t_214':{state:'58.2',attributes:{device_class:'humidity',unit_of_measurement:'%'}}};
              if(sensors==='unavailable')states['sensor.sensor_8d_s0_batt']={state:'unavailable'};
              manualCard.hass={...manualCard.hass,states};
              manualCard.load();
            }''',[output,sensors,theme])
            page.wait_for_function('!manualCard.loading')
            for mode in ('on','off','auto'):
                button=manual_locator.locator('button.resume' if mode=='auto' else f'button[data-mode="{mode}"]')
                assert button.is_enabled(),(output,sensors,mode)
                before=page.evaluate('()=>unboundCalls.length')
                button.click()
                page.wait_for_function('(n)=>unboundCalls.length===n+1 && !manualCard.operation',arg=before)
                assert page.evaluate('()=>unboundCalls.at(-1).mode')==mode
                assert page.evaluate("()=>getComputedStyle(manualCard.shadowRoot.querySelector('.rotor')).animationPlayState")==('running' if output=='on' else 'paused')
                assert page.evaluate("()=>getComputedStyle(manualCard.shadowRoot.querySelector('.rotor path')).fill")==('rgb(220, 91, 86)' if output=='on' else 'rgb(138, 148, 153)')
                if sensors=='healthy':
                    assert '27.7' in manual_locator.locator('.live-status').inner_text()
                    assert '58.2' in manual_locator.locator('.live-status').inner_text()
            if output=='unknown':
                assert '狀態未知' in manual_locator.locator('.reason').inner_text()
                assert '明確手動' in manual_locator.locator('.reason').inner_text()
                assert '已開啟' not in manual_locator.locator('.badge').inner_text()
                assert '已關閉' not in manual_locator.locator('.badge').inner_text()
                assert page.evaluate("()=>getComputedStyle(manualCard.shadowRoot.querySelector('.rotor')).animationPlayState")=='paused'
            assert manual_locator.locator('.fan-item').count()==1
            assert page.evaluate("()=>getComputedStyle(manualCard.shadowRoot.querySelector('.fans')).gridTemplateColumns.split(' ').length")==2
            single=page.evaluate("()=>{const s=manualCard.shadowRoot,item=s.querySelector('.fan-item'),grid=s.querySelector('.fans');return {width:item.getBoundingClientRect().width,grid:grid.getBoundingClientRect().width,overflow:item.scrollWidth-item.clientWidth}}")
            assert single['width']<single['grid']*.55 and single['overflow']<=1,single
            manual_matrix.append([theme,output,sensors])
    page.evaluate('()=>manualCard.remove()')
    assert page.evaluate("()=>customElements.get('uninus-greenhouse-fan-card').buildVersion")=='0.2.2'
    assert page.evaluate("()=>customElements.get('uninus-greenhouse-fan-card-editor').buildVersion")=='0.2.2'
    (OUT/'runtime-state-matrix.json').write_text(json.dumps({'visual_checks':visual_checks,'fixed_geometry':fixed_geometry,'manual_matrix':manual_matrix,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,errors
    browser.close()
print(json.dumps({'browser':'Edge headless','measurements':{str(w):{'row':m['row'],'global_above':m['above'],'overflow':m['overflow']} for w,m in measurements.items()},'discovery':discovery_checks,'lifecycle_races':'passed','editor_configured_devices':'passed','manual':'passed','unbound_manual_on_off_resume':'passed','errors':errors},ensure_ascii=False))
