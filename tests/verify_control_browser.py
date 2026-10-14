"""Local real-browser global toggle, boundary colors, compact geometry gates."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/evidence'
OUT.mkdir(exist_ok=True)
# Exact before-change measurements from fea58d4 with this identical fixture.
BASE={'2':{390:886.09375,500:919.109375,720:848.171875,1080:848.171875},'auto':{390:1481.15625,500:1478.171875,720:848.171875,1080:848.171875}}
with sync_playwright() as p:
    edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser=p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None),headless=True)
    page=browser.new_page(viewport={'width':1530,'height':1200})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<!doctype html><html><body style="margin:0;background:#eee"></body></html>')
    page.add_script_tag(path=str(ROOT/'www/uninus-greenhouse-fan-card.js'))
    page.evaluate('''()=>{
      window.calls=[];const states={};for(let i=1;i<=4;i++){
        states['fan.f'+i]={entity_id:'fan.f'+i,state:i===3?'off':'on',attributes:{friendly_name:'第 '+i+' 區排熱風扇'}};
        states['sensor.t'+i]={entity_id:'sensor.t'+i,state:String(26+i),attributes:{device_class:'temperature',unit_of_measurement:'°C'}};
        states['sensor.h'+i]={entity_id:'sensor.h'+i,state:String(61+i),attributes:{device_class:'humidity',unit_of_measurement:'%'}};
      }
      window.snap={entry_id:'group-1',revision:1,control_mode:'auto',devices:[1,2,3,4].map(i=>({device_id:'d'+i,name:'Configured '+i,fan_entity:'fan.f'+i})),policy:{temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120},bindings:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{temperature_entity:'sensor.t'+i,humidity_entity:'sensor.h'+i}])),runtime:Object.fromEntries([1,2,3,4].map(i=>['fan.f'+i,{mode:'auto',pending:null,reason:'threshold_not_met'}]))};
      window.fakeHass={user:{is_admin:true},states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return [{entry_id:'group-1',name:'Greenhouse',loaded:true}];if(msg.type.endsWith('/set_control_mode')){return new Promise(resolve=>window.completeToggle=()=>{snap.control_mode=msg.control_mode;for(const v of Object.values(snap.runtime)){v.mode=msg.control_mode==='auto'?'auto':'manual';v.pending=null;}resolve(structuredClone(snap));});}return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.appendChild(card);card.style.display='block';card.style.width='720px';card.setConfig({type:'custom:uninus-greenhouse-fan-card',entry_id:'group-1',name:'排熱風扇控制',items:[1,2,3,4].map(i=>({fan_entity:'fan.f'+i,name:'第 '+i+' 區排熱風扇'})),layout:'auto',theme:'dark'});card.hass=fakeHass;
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    locator=page.locator('uninus-greenhouse-fan-card')
    toggle=locator.get_by_role('switch',name='全域自動控制')
    toggle.click()
    assert toggle.is_disabled()
    assert toggle.get_attribute('aria-checked')=='true'
    assert not page.evaluate('()=>card.shadowRoot.querySelector(".global").open')
    page.evaluate('()=>completeToggle()')
    page.wait_for_function('!card.operation')
    assert toggle.get_attribute('aria-checked')=='false'
    assert locator.locator('button.resume:disabled').count()==4
    assert locator.locator('button[data-mode="on"]:enabled').count()==4
    toggle.focus();page.keyboard.press('Space')
    assert toggle.get_attribute('aria-checked')=='false'
    assert not page.evaluate('()=>card.shadowRoot.querySelector(".global").open')
    page.evaluate('()=>completeToggle()')
    page.wait_for_function('!card.operation')
    assert toggle.get_attribute('aria-checked')=='true'
    assert page.evaluate('()=>calls.filter(x=>x.type.endsWith("/set_control_mode")).map(x=>x.control_mode)')==['manual','auto']
    # Expanded disclosure remains expanded on the same real control click.
    locator.locator('.global summary').click()
    page.wait_for_function('card.expanded')
    toggle.click();assert page.evaluate('()=>card.shadowRoot.querySelector(".global").open')
    page.evaluate('()=>completeToggle()');page.wait_for_function('!card.operation')
    toggle.click();page.evaluate('()=>completeToggle()');page.wait_for_function('!card.operation')
    assert page.evaluate('()=>card.shadowRoot.querySelector(".global").open')
    locator.locator('.global summary').click();page.wait_for_function('!card.expanded')
    # A rejected transaction keeps the authoritative checked state and shows an error.
    page.evaluate("()=>{window.originalWS=fakeHass.callWS;fakeHass.callWS=msg=>msg.type.endsWith('/set_control_mode')?Promise.reject(Error('disk offline')):originalWS(msg)}")
    toggle.click();page.wait_for_function('!card.operation && !!card.error')
    assert toggle.get_attribute('aria-checked')=='true'
    assert 'disk offline' in locator.get_by_role('alert').inner_text()
    page.evaluate('()=>{fakeHass.callWS=originalWS;card.load()}');page.wait_for_function('!card.loading && !card.error')
    # Separate value-based colors, not rounded text or current actuator state.
    colors=[]
    for theme in ('dark','light'):
        for t,h,mode,global_mode,expected in [(29,93.4,'auto','auto',[False,False]),(29.001,93.4,'auto','auto',[True,False]),(29,93.401,'auto','auto',[False,True]),(30,94,'on','auto',[False,False]),(30,94,'auto','manual',[False,False]),(None,'unknown','auto','auto',[False,False])]:
            page.evaluate('''args=>{const [theme,t,h,mode,g]=args;snap.control_mode=g;snap.runtime['fan.f1'].mode=mode;fakeHass.states['sensor.t1'].state=t;fakeHass.states['sensor.h1'].state=h;card.setConfig({...card.config,theme});card.hass=fakeHass;card.load()}''',[theme,t,h,mode,global_mode])
            page.wait_for_function('card.snapshot && !card.loading')
            result=page.evaluate('''()=>[...card.shadowRoot.querySelector('.fan-item').querySelectorAll('.live-line')].map(x=>({high:x.classList.contains('threshold-high'),color:getComputedStyle(x.querySelector('strong')).color,underline:getComputedStyle(x.querySelector('strong')).textDecorationLine}))''')
            assert [x['high'] for x in result]==expected,result
            for row,high in zip(result,expected):
                if high:
                    assert row['color']==('rgb(255, 173, 165)' if theme=='dark' else 'rgb(168, 50, 32)')
                    assert row['underline']=='underline'
            colors.append({'theme':theme,'t':t,'h':h,'mode':mode,'global':global_mode,'result':result})
            if t is None:
                page.evaluate("()=>{window.savedBinding=snap.bindings['fan.f1'];delete snap.bindings['fan.f1'];fakeHass.states['sensor.t1'].state='50';fakeHass.states['sensor.h1'].state='99';card.load()}")
                page.wait_for_function('!card.loading')
                assert locator.locator('.fan-item').first.locator('.threshold-high').count()==0
                page.evaluate("()=>{snap.bindings['fan.f1']=savedBinding}")
    page.evaluate("()=>{snap.control_mode='auto';snap.runtime['fan.f1'].mode='auto';fakeHass.states['sensor.t1'].state='27';fakeHass.states['sensor.h1'].state='62';}")
    measurements=[]
    for theme in ('dark','light'):
        for layout in ('2','auto'):
            for width in (390,500,720,1080):
                page.evaluate('(args)=>{const [width,theme,layout]=args;card.style.width=width+"px";card.setConfig({...card.config,theme,layout});card.hass=fakeHass}',[width,theme,layout])
                page.wait_for_function('card.snapshot && !card.loading')
                page.wait_for_timeout(30)
                result=page.evaluate('''()=>{const s=card.shadowRoot,box=s.querySelector('.card');return {height:box.getBoundingClientRect().height,width:card.getBoundingClientRect().width,overflow:[box,...s.querySelectorAll('.fan-item,.controls,.device-hero,.live-status,.global')].map(x=>x.scrollWidth-x.clientWidth),buttons:[...s.querySelectorAll('button')].map(x=>({w:x.getBoundingClientRect().width,h:x.getBoundingClientRect().height})),textClipped:[...s.querySelectorAll('.reason,.mode-row,.live-line,.limit-pair')].filter(x=>x.scrollHeight>x.clientHeight+1).length}}''')
                assert result['height']<BASE[layout][width],(theme,layout,width,result)
                assert result['width']==width
                assert max(result['overflow'])<=1,result
                assert result['textClipped']==0,result
                assert all(x['w']>=44 and x['h']>=44 for x in result['buttons']),result
                measurements.append({'theme':theme,'layout':layout,'width':width,'before':BASE[layout][width],'after':result['height'],'reduction':BASE[layout][width]-result['height'],**result})
    assert not errors,errors
    (OUT/'control-mode-layout.json').write_text(json.dumps({'measurements':measurements,'colors':colors,'toggle':'click and keyboard space passed','errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print(json.dumps({'measurements':[{k:r[k] for k in ('theme','layout','width','before','after','reduction')} for r in measurements],'colors':len(colors),'toggle':'passed','errors':errors}))
