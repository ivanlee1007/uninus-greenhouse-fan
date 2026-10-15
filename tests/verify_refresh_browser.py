"""Real DOM lifecycle gate: controlled 5-second polls, deferred WS, live HA state."""
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
    page=browser.new_page(viewport={'width':1200,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.clock.install()
    page.set_content('<!doctype html><body style="margin:0"><div id="scroller" style="height:600px;overflow:auto"></div></body>')
    page.add_script_tag(path=os.environ.get('CARD_TEST_SOURCE',str(ROOT/'www/uninus-greenhouse-fan-card.js')))
    page.evaluate('''()=>{
      window.calls=[];window.queue=[];window.defer=false;window.fail=false;window.loaded=true;
      window.snap={entry_id:'g',revision:1,policy_revision:0,control_mode:'auto',policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},devices:[1,2].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i,name:'Fan '+i})),bindings:Object.fromEntries([1,2].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}])),runtime:Object.fromEntries([1,2].map(i=>['fan.f'+i,{mode:'on',reason:'threshold_not_met',pending:null}]))};
      const states={};for(let i=1;i<=2;i++){states['fan.f'+i]={state:'on',attributes:{}};states['sensor.t'+i]={state:'27',attributes:{unit_of_measurement:'°C',device_class:'temperature'}};states['sensor.h'+i]={state:'65',attributes:{unit_of_measurement:'%',device_class:'humidity'}}}
      window.h={user:{is_admin:true},states,callWS:async m=>{calls.push(m);if(m.type.endsWith('/groups'))return [{entry_id:'g',name:'Group',loaded}];if(m.type.endsWith('/manual'))return new Promise(r=>window.finishCommand=()=>{snap.runtime[m.fan_entity].mode=m.mode;r(structuredClone(snap))});if(fail)throw Error('read offline');if(defer)return new Promise(r=>queue.push(r));return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.querySelector('#scroller').append(card);card.style.width='720px';card.setConfig({entry_id:'g',layout:'2',items:[1,2].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i}))});card.hass=h;
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    page.evaluate('''()=>{
      const s=card.shadowRoot;s.querySelector('.global').open=true;card.expanded=true;card.editThreshold('temperature_on',31);
      window.refs=[...s.querySelectorAll('.fan-item,.rotor,.controls button,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')];
      window.animations=[...s.querySelectorAll('.rotor')].map(x=>x.getAnimations()[0]);
      window.sameControls=()=>{const current=[...s.querySelectorAll('.fan-item,.rotor,.controls button,.mode-switch,.threshold-demo input,.threshold-actions button,.global summary')];return current.length===refs.length && current.every((x,i)=>x===refs[i])};
      window.focus=s.querySelector('[data-save]');focus.focus();document.querySelector('#scroller').scrollTop=30;window.scrollBefore=document.querySelector('#scroller').scrollTop;
      window.removals=0;window.disabledFlips=0;window.records=[];
      window.observer=new MutationObserver(rs=>{for(const r of rs){if(r.type==='attributes' && refs.includes(r.target) && r.attributeName==='disabled')disabledFlips++;for(const n of r.removedNodes)if(refs.some(x=>n===x || n.contains?.(x)))removals++}});observer.observe(s,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});defer=true;
    }''')
    cycles=[]
    for cycle in range(3):
        page.evaluate('''i=>{focus=card.shadowRoot.querySelector(['[data-save]','[data-mode="on"]','.mode-switch'][i]);focus.focus({preventScroll:true})}''',cycle)
        page.clock.run_for(5000)
        page.wait_for_function('queue.length===1')
        for tick in range(6):
            page.evaluate('''v=>{h.states['sensor.t1'].state=String(v);card.hass={...h};}''',27+tick/10)
        assert '27.5' in page.locator('uninus-greenhouse-fan-card').locator('.live-status').first.inner_text()
        cycles.append(page.evaluate('''()=>({connected:refs.every(x=>x.isConnected),identity:sameControls(),focused:card.shadowRoot.activeElement===focus,enabled:!focus.disabled,removals,disabledFlips})'''))
        page.evaluate('()=>queue.shift()(structuredClone(snap))')
        page.wait_for_function('!card.loading')
    idle=page.evaluate('''()=>({cycles:3,removals,disabledFlips,connected:refs.every(x=>x.isConnected),focused:card.shadowRoot.activeElement===focus,scrollRetained:document.querySelector('#scroller').scrollTop===scrollBefore,expanded:card.shadowRoot.querySelector('.global').open,readCalls:calls.filter(x=>x.type.endsWith('/get')).length,writes:calls.filter(x=>!x.type.endsWith('/get')&&!x.type.endsWith('/groups')).length})''')
    (OUT/'refresh-idle.json').write_text(json.dumps({'idle':idle,'cycles':cycles},indent=2),encoding='utf-8')
    print(json.dumps({'idle':idle,'cycles':cycles}),flush=True)
    assert all(c['connected'] and c['identity'] and c['focused'] and c['enabled'] for c in cycles),cycles
    assert idle['removals']==0 and idle['disabledFlips']==0,idle
    assert idle['focused'] and idle['scrollRetained'] and idle['expanded'] and idle['writes']==0,idle
    assert page.evaluate('''()=>[...card.shadowRoot.querySelectorAll('.rotor')].every((x,i)=>x.getAnimations()[0]===animations[i])''')
    # Read storms are coalesced; an actual action invalidates the older read.
    page.clock.run_for(5000);page.wait_for_function('queue.length===1')
    before=page.evaluate('calls.length')
    page.clock.run_for(15000)
    assert page.evaluate('calls.length')==before
    page.locator('uninus-greenhouse-fan-card').locator('[data-mode="off"]').first.click()
    assert page.evaluate('!!card.operation')
    assert page.locator('uninus-greenhouse-fan-card').locator('.controls button:enabled').count()==0
    page.evaluate('()=>finishCommand()');page.wait_for_function('!card.operation')
    page.evaluate('()=>{const stale=structuredClone(snap);stale.revision=999;queue.shift()(stale)}')
    page.evaluate('()=>Promise.resolve()')
    assert page.evaluate('card.snapshot.revision')==1
    assert page.evaluate("card.snapshot.runtime['fan.f1'].mode")=='off'
    # Real backend changes patch existing articles, buttons, animation, and global nodes.
    page.evaluate('''()=>{defer=false;snap.runtime['fan.f1']={mode:'auto',pending:'on',reason:'server <diagnostic>'};snap.control_mode='manual';snap.policy.humidity_on=81;h.states['fan.f1'].state='off';h.states['sensor.t1'].state='35';card.hass={...h};card.load()}''')
    page.wait_for_function("card.snapshot.control_mode==='manual'")
    loc=page.locator('uninus-greenhouse-fan-card')
    assert loc.locator('.fan-item').first.locator('.badge').inner_text()=='● 已關閉'
    assert '35.0' in loc.locator('.fan-item').first.locator('.live-status').inner_text()
    assert loc.locator('.mode-switch').get_attribute('aria-checked')=='false'
    page.evaluate("()=>{snap.control_mode='auto';snap.runtime['fan.f1']={mode:'auto',reason:'server <diagnostic>',pending:'on'};card.load()}")
    page.wait_for_function("card.snapshot.control_mode==='auto'")
    assert 'server <diagnostic>' in loc.locator('.reason').first.inner_text()
    assert loc.locator('.reason diagnostic').count()==0
    assert loc.locator('.fan-item').first.locator('.threshold-high').count()==1
    # Failure / unloaded inventory fail closed; latest scope cannot consume old completion.
    page.evaluate('()=>{fail=true;card.load()}');page.wait_for_function('!!card.error')
    assert loc.locator('.controls button:enabled').count()==0
    page.evaluate('()=>{fail=false;loaded=false;card.load()}');page.wait_for_function('!card.loading')
    assert page.evaluate('card.snapshot===null && !card.resolvedId')
    assert loc.locator('.controls button:enabled').count()==0
    page.evaluate('()=>{loaded=true;card.load()}');page.wait_for_function('card.snapshot && !card.loading')
    page.evaluate('()=>{defer=true;card.load()}');page.wait_for_function('queue.length===1')
    page.evaluate("()=>{card.setConfig({...card.config,entry_id:'missing'});queue.shift()(structuredClone(snap))}")
    page.wait_for_function('!card.loading')
    assert page.evaluate("!card.resolvedId && !card.snapshot && card.config.entry_id==='missing'")
    page.evaluate('()=>card.remove()');count=page.evaluate('calls.length');page.clock.run_for(15000)
    assert page.evaluate('calls.length')==count
    assert not errors,errors
    (OUT/'refresh-browser.json').write_text(json.dumps({'idle':idle,'cycles':cycles,'race_cases':['coalesced polls','action invalidates read','real state + diagnostics + colors','error fail closed','unload fail closed','new scope ignores old read','disconnect cancels poll'],'errors':errors},indent=2),encoding='utf-8')
    browser.close()
print('refresh browser passed')
