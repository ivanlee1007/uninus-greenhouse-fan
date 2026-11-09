"""No-details readouts retain an 8px minimum gap above bottom-aligned controls."""
from pathlib import Path
import hashlib
import json
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('CARD_TEST_SOURCE', str(ROOT / 'www/uninus-greenhouse-fan-card.js')))
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None), headless=True)
    page = browser.new_page(viewport={'width':1400,'height':1400})
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_content('<!doctype html><body></body>')
    page.add_script_tag(path=str(SOURCE))
    page.evaluate('''()=>{
      window.calls=[];
      window.snapshot={entry_id:'g',revision:1,policy_revision:0,control_mode:'auto',policy:{temperature_on:29,temperature_off:25,humidity_on:90,humidity_off:81,duration_seconds:120},devices:[1,2].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i,name:'Fan '+i})),bindings:Object.fromEntries([1,2].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}])),runtime:{}};
      const states={};for(let i=1;i<=2;i++){states['fan.f'+i]={state:'off',attributes:{}};states['sensor.t'+i]={state:i===1?'24.3':'31.6',attributes:{unit_of_measurement:'°C',device_class:'temperature'}};states['sensor.h'+i]={state:i===1?'66.8':'93.2',attributes:{unit_of_measurement:'%',device_class:'humidity'}}}
      window.h={user:{is_admin:true},states,callWS:async m=>{calls.push(m);if(m.type.endsWith('/groups'))return [{entry_id:'g',name:'Group',loaded:true}];if(m.type.endsWith('/get'))return structuredClone(snapshot);throw Error('No writes allowed')}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);
      card.setConfig({entry_id:'g',theme:'light',layout:'auto',show_device_details:false,items:snapshot.devices.map(d=>({device_id:d.device_id}))});card.style.width='500px';card.hass=h;
      window.measure=()=>[...card.shadowRoot.querySelectorAll('.fan-item')].map(n=>{
        const hero=n.querySelector('.device-hero'),controls=n.querySelector('.controls'),details=n.querySelector('.device-details'),r=n.getBoundingClientRect(),cs=getComputedStyle(n),cr=controls.getBoundingClientRect();
        return {y:r.y,heroMargin:parseFloat(getComputedStyle(hero).marginBottom),details:!!details,gap:cr.top-Math.max(...[...n.querySelectorAll('.live-line strong')].map(x=>x.getBoundingClientRect().bottom)),bottomInset:r.bottom-cr.bottom,paddingBottom:parseFloat(cs.paddingBottom)+parseFloat(cs.borderBottomWidth),controlsBottom:cr.bottom,buttons:[...controls.querySelectorAll('button')].map(b=>b.getBoundingClientRect().height),overflow:Math.max(...[n,hero,controls,...n.querySelectorAll('.live-line')].map(x=>x.scrollWidth-x.clientWidth))}
      });
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    initial=page.evaluate('measure()')
    assert all(row['gap'] >= 7.9 for row in initial), ('reported live configuration', initial)
    cases=[]
    for theme in ('light','dark'):
        for layout in ('auto','1','2'):
            for width in (320,390,500,720,1080):
                for reading_layout in (None,'compact','columns','split'):
                    for details in (False,True):
                        page.evaluate('''a=>{card.style.width=a.width+'px';card.setConfig({...card.config,theme:a.theme,layout:a.layout,readings_layout:a.reading_layout,lock_readings_right:a.reading_layout!==null,show_device_details:a.details})}''',dict(theme=theme,layout=layout,width=width,reading_layout=reading_layout,details=details))
                        page.wait_for_function('card.snapshot && !card.loading')
                        result=page.evaluate('measure()')
                        case=dict(theme=theme,layout=layout,width=width,readings_layout=reading_layout,details=details)
                        for row in result:
                            assert row['details']==details,(case,row)
                            assert row['heroMargin']==(0 if details else 8),(case,row)
                            assert row['gap']>=7.9,(case,row)
                            assert abs(row['bottomInset']-row['paddingBottom'])<=1,(case,row)
                            assert min(row['buttons'])>=44,(case,row)
                            assert row['overflow']<=1,(case,row)
                        if abs(result[0]['y']-result[1]['y'])<=1:
                            assert abs(result[0]['controlsBottom']-result[1]['controlsBottom'])<=1,(case,result)
                        cases.append(case)
    # Healthy hass updates keep the guard for low, normal, high and missing readings.
    page.evaluate("card.setConfig({...card.config,layout:'auto',lock_readings_right:false,show_device_details:false})")
    page.wait_for_function('card.snapshot && !card.loading')
    page.evaluate("window.refs=[...card.shadowRoot.querySelectorAll('.controls button')]")
    for temperature,humidity in [('24.3','66.8'),('27','85'),('31.6','93.2'),('unavailable','unknown')]:
        page.evaluate("a=>{h.states['sensor.t1'].state=a[0];h.states['sensor.h1'].state=a[1];card.hass={...h}}",[temperature,humidity])
        assert all(row['gap']>=7.9 for row in page.evaluate('measure()'))
        assert page.evaluate("[...card.shadowRoot.querySelectorAll('.controls button')].every((n,i)=>n===refs[i])")
    assert page.evaluate("calls.every(m=>m.type.endsWith('/get') || m.type.endsWith('/groups'))")
    assert errors==[],errors
    browser.close()
report={'passed':True,'matrix_cases':len(cases),'hidden_details_hero_margin_px':8,'visible_details_hero_margin_px':0,'controls_bottom_aligned':True,'buttons_min_height_px':44,'reading_transition_cases':4,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'page_errors':errors,'scope':'Offline actual renderer and synthetic HA state; no live configuration or device changes'}
out=ROOT/'tests/evidence/reading-spacing.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
