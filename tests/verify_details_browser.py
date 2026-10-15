"""Display-only checkbox round trip and compact all-fan omission in Chromium."""
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
    page=browser.new_page(viewport={'width':1200,'height':1200})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<!doctype html><body><button id="save">Dashboard Save fixture</button></body>')
    page.add_script_tag(path=str(ROOT/'www/uninus-greenhouse-fan-card.js'))
    page.evaluate('''()=>{
      window.calls=[];window.saved={entry_id:'g',layout:'2',name:'<img src=x onerror=alert(1)>',items:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i}))};
      window.snap={entry_id:'g',control_mode:'auto',revision:1,policy_revision:0,policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},devices:[1,2,3,4].map(i=>({device_id:'d'+i,fan_entity:'fan.f'+i,name:'Fan '+i})),runtime:{},bindings:{}};
      window.h={user:{is_admin:true},states:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{state:'on',attributes:{}}])),callWS:async m=>{calls.push(m);return m.type.endsWith('/groups')?[{entry_id:'g',name:'Greenhouse',loaded:true}]:structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);card.setConfig(saved);card.hass=h;
      window.reopen=()=>{window.editor?.remove();window.editor=document.createElement('uninus-greenhouse-fan-card-editor');editor.addEventListener('config-changed',e=>window.draft=structuredClone(e.detail.config));document.body.append(editor);editor.setConfig(saved);editor.hass=h};reopen();
      document.querySelector('#save').onclick=()=>{saved=structuredClone(draft);card.setConfig(saved);reopen()};
    }''')
    page.wait_for_function('editor.snapshot && card.snapshot && !card.loading && !editor.loading')
    loc=page.locator('uninus-greenhouse-fan-card')
    check=page.locator('uninus-greenhouse-fan-card-editor').get_by_label('顯示控制模式與診斷訊息',exact=True)
    assert check.is_checked()
    checkbox_box=check.bounding_box()
    assert checkbox_box['width']<=24 and checkbox_box['height']<=24,checkbox_box
    assert loc.locator('.device-details').count()==4
    for checked in (False,True,False):
        check.set_checked(checked)
        assert page.evaluate('typeof draft.show_device_details')=='boolean'
        assert page.evaluate('draft.show_device_details')==checked
        page.locator('#save').click()
        page.wait_for_function('editor.snapshot && card.snapshot && !card.loading && !editor.loading')
        assert check.is_checked()==checked
        assert loc.locator('.device-details').count()==(4 if checked else 0)
        page.evaluate('()=>{card.hass={...h};editor.hass={...h};card.load();editor.load()}')
        page.wait_for_function('!card.loading && !editor.loading')
        assert check.is_checked()==checked
        assert loc.locator('.device-details').count()==(4 if checked else 0)
    measurements=[]
    for theme in ('dark','light'):
        for width in (390,500,720):
            heights={}
            for visible in (True,False):
                page.evaluate('''a=>{const [theme,width,visible]=a;card.style.width=width+'px';card.setConfig({...card.config,theme,show_device_details:visible})}''',[theme,width,visible])
                page.wait_for_function('card.snapshot && !card.loading')
                result=page.evaluate('''()=>{const s=card.shadowRoot;return {height:s.querySelector('.card').getBoundingClientRect().height,details:s.querySelectorAll('.device-details').length,reason:s.querySelectorAll('.reason').length,mode:s.querySelectorAll('.mode-row').length,badges:s.querySelectorAll('.badge').length,buttons:s.querySelectorAll('.controls button:enabled').length,readings:s.querySelectorAll('.live-status').length,note:s.querySelectorAll('.card-note').length,overflow:Math.max(...[s.querySelector('.card'),...s.querySelectorAll('.fan-item,.controls,.global')].map(n=>n.scrollWidth-n.clientWidth)),columns:getComputedStyle(s.querySelector('.fans')).gridTemplateColumns.split(' ').length}}''')
                assert result['details']==(4 if visible else 0),result
                assert result['reason']==result['mode']==result['details'],result
                assert result['badges']==result['readings']==4 and result['buttons']==8 and result['note']==1,result
                assert result['overflow']<=1 and result['columns']==2,result
                assert loc.locator('img').count()==0
                heights[str(visible)]=result['height']
            assert heights['False']<heights['True'],heights
            measurements.append({'theme':theme,'width':width,'heights':heights,'reduction':heights['True']-heights['False']})
    writes=page.evaluate("calls.filter(x=>!x.type.endsWith('/get')&&!x.type.endsWith('/groups'))")
    assert writes==[],writes
    assert not errors,errors
    (OUT/'device-details-browser.json').write_text(json.dumps({'round_trip':[False,True,False],'measurements':measurements,'backend_writes':writes,'errors':errors,'scope':'Real custom editor click + config-changed + synthetic Dashboard Save host; not live HA dashboard storage UI'},indent=2),encoding='utf-8')
    browser.close()
print(json.dumps({'details':'passed','measurements':measurements,'backend_writes':writes,'errors':errors}))
