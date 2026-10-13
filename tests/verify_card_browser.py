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
      window.snap={entry_id:'group-1',revision:1,policy:{temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120},bindings:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}])),runtime:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{mode:'auto',pending:null,reason:'threshold_not_met'}]))};
      window.fakeHass={states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/bind')){if(msg.expected_revision!==snap.revision)throw Error('conflict');snap.bindings[msg.fan_entity]={temperature_entity:msg.temperature_entity,humidity_entity:msg.humidity_entity};snap.revision++}if(msg.type.endsWith('/manual'))snap.runtime[msg.fan_entity].mode=msg.mode;return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.appendChild(card);card.style.display='block';card.style.width='720px';card.setConfig({type:'custom:uninus-greenhouse-fan-card',entry_id:'group-1',name:'排熱風扇控制',items:[1,2,3,4].map(i=>({fan_entity:'fan.f'+i,name:'第 '+i+' 區排熱風扇'})),layout:'auto',theme:'dark'});card.hass=fakeHass;
    }''')
    page.wait_for_function("document.querySelector('uninus-greenhouse-fan-card').snapshot?.revision===1")
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
    # Use a different valid source, apply backend binding, ensure Lovelace config contains no sensor copy.
    page.locator('uninus-greenhouse-fan-card-editor').locator('select[data-field="temperature_entity"]').first.select_option('sensor.t2')
    page.locator('uninus-greenhouse-fan-card-editor').locator('button[data-action="apply"]').first.click()
    page.wait_for_function('editor.snapshot?.revision===2')
    assert page.evaluate("()=>snap.bindings['fan.f1'].temperature_entity")=="sensor.t2"
    assert page.evaluate("()=>editor.config.items[0].temperature_entity===undefined")
    assert not errors,errors
    browser.close()
print(json.dumps({'browser':'Edge headless','measurements':{str(w):{'row':m['row'],'global_above':m['above'],'overflow':m['overflow']} for w,m in measurements.items()},'editor_binding':'passed','manual':'passed','errors':errors},ensure_ascii=False))
