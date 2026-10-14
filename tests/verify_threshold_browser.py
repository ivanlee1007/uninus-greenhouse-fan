"""Shipped production card: real pointer/keyboard, draft races and approved A geometry."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/evidence'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None), headless=True)
    page = browser.new_page(viewport={'width':1530, 'height':1200})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content('<!doctype html><body style="margin:0"></body>')
    page.add_script_tag(path=str(ROOT/'www/uninus-greenhouse-fan-card.js'))
    page.evaluate('''()=>{
      window.calls=[];
      window.snap={entry_id:'demo-group',revision:1,policy_revision:0,control_mode:'auto',policy:{temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120},devices:[{device_id:'a',name:'A1 排熱風扇',fan_entity:'switch.demo_a'},{device_id:'b',name:'A2 排熱風扇',fan_entity:'switch.demo_b'}],bindings:{'switch.demo_a':{temperature_entity:'sensor.temp_a',humidity_entity:'sensor.hum_a'},'switch.demo_b':{temperature_entity:'sensor.temp_b',humidity_entity:'sensor.hum_b'}},runtime:{'switch.demo_a':{mode:'auto'},'switch.demo_b':{mode:'auto'}}};
      window.fakeHass={user:{is_admin:true},states:{'switch.demo_a':{state:'on',attributes:{}},'switch.demo_b':{state:'off',attributes:{}},'sensor.temp_a':{state:'30.2',attributes:{device_class:'temperature',unit_of_measurement:'°C'}},'sensor.hum_a':{state:'88',attributes:{device_class:'humidity',unit_of_measurement:'%'}},'sensor.temp_b':{state:'26.8',attributes:{device_class:'temperature',unit_of_measurement:'°C'}},'sensor.hum_b':{state:'76',attributes:{device_class:'humidity',unit_of_measurement:'%'}}},callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return[{entry_id:'demo-group',name:'Demo',loaded:true}];if(msg.type.endsWith('/save_thresholds'))return new Promise((resolve,reject)=>{window.finishSave=()=>{Object.assign(snap.policy,msg.thresholds);snap.policy_revision++;resolve(structuredClone(snap))};window.failSave=code=>reject({code,message:code})});return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');card.style.width='720px';document.body.append(card);card.setConfig({entry_id:'demo-group',name:'Greenhouse fans',subtitle_text:'前台門檻調整 · 設計審核 Demo',items:snap.devices,layout:'2',theme:'light'});card.hass=fakeHass;
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    host = page.locator('uninus-greenhouse-fan-card')
    host.locator('.global summary').click()
    page.wait_for_function('card.expanded')
    assert host.locator('.threshold-group').count() == 2
    assert host.locator('.global-body input[type=range]').count() == 4
    assert host.locator('.fans input[type=range]').count() == 0
    slider = host.get_by_role('slider', name='溫度啟動上限')
    page.evaluate('()=>window.originalInput=card.shadowRoot.querySelector("#temperature_on")')
    # Pointer remains on the same connected node across live hass and snapshot refresh.
    box = slider.bounding_box()
    page.mouse.move(box['x']+box['width']*.58, box['y']+box['height']/2)
    page.mouse.down()
    page.mouse.move(box['x']+box['width']*.7, box['y']+box['height']/2, steps=8)
    page.evaluate('async()=>{card.hass={...fakeHass};await card.load()}')
    assert page.evaluate('()=>originalInput===card.shadowRoot.querySelector("#temperature_on") && originalInput.isConnected')
    page.mouse.move(box['x']+box['width']*.75, box['y']+box['height']/2, steps=8)
    page.mouse.up()
    value = float(slider.input_value())
    assert value > 30
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 29
    assert host.locator('.limit-pair').first.inner_text().endswith('29 / 25 °C')
    assert host.locator('.fan-item').first.locator('.threshold-high').count() == 1
    assert page.evaluate('()=>calls.filter(x=>x.type.endsWith("/save_thresholds")).length') == 0
    slider.focus()
    page.keyboard.press('ArrowRight')
    page.evaluate('async()=>{card.hass={...fakeHass};await card.load()}')
    assert page.evaluate('()=>card.shadowRoot.activeElement===originalInput')
    host.get_by_role('button', name='取消修改').click()
    page.wait_for_function('!card.loading')
    assert float(slider.input_value()) == 29
    assert page.evaluate('()=>calls.filter(x=>x.type.endsWith("/save_thresholds")).length') == 0
    # Keyboard validation: start below stop rejects without a network write.
    slider.focus(); page.keyboard.press('Home')
    assert host.get_by_role('button', name='儲存門檻').is_disabled()
    assert '停止下限不可高於' in host.locator('.validation').inner_text()
    host.get_by_role('button', name='取消修改').click();page.wait_for_function('!card.loading')
    slider.focus();page.keyboard.press('ArrowRight')
    host.get_by_role('button', name='儲存門檻').click()
    assert host.get_by_role('button', name='儲存門檻').is_disabled()
    assert host.get_by_role('button', name='取消修改').is_disabled()
    assert host.get_by_role('switch').is_disabled()
    assert host.locator('[data-mode=on]').first.is_disabled()
    page.evaluate('()=>card.saveThresholds()')
    assert page.evaluate('()=>calls.filter(x=>x.type.endsWith("/save_thresholds")).length') == 1
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 29
    page.evaluate('()=>finishSave()');page.wait_for_function('!card.operation')
    assert page.evaluate('()=>card.thresholdDraft') is None
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 29.1
    assert page.evaluate('()=>card.snapshot.policy.duration_seconds') == 120
    # Failed persistence keeps draft and effective policy, conflict recovery is explicit.
    slider.focus();page.keyboard.press('ArrowRight');host.get_by_role('button', name='儲存門檻').click()
    page.evaluate("()=>failSave('save_failed')");page.wait_for_function('!card.operation')
    assert float(slider.input_value()) == 29.2
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 29.1
    assert '草稿保留' in host.locator('.validation').inner_text()
    page.evaluate('async()=>{snap.policy.temperature_on=33;snap.policy_revision++;await card.load()}')
    assert float(slider.input_value()) == 29.2
    assert host.get_by_role('button', name='儲存門檻').is_disabled()
    assert '其他介面修改' in host.locator('.validation').inner_text()
    assert page.evaluate('()=>card.thresholdDraft.revision') == 1
    host.get_by_role('button', name='取消修改').click();page.wait_for_function('!card.loading')
    assert float(slider.input_value()) == 33
    slider.focus();page.keyboard.press('ArrowRight');host.get_by_role('button', name='儲存門檻').click()
    page.evaluate("()=>failSave('conflict')");page.wait_for_function('!card.operation')
    assert '其他介面修改' in host.locator('.validation').inner_text()
    host.get_by_role('button', name='取消修改').click();page.wait_for_function('!card.loading')
    # Valid legacy native endpoints expand the display range rather than clipping.
    page.evaluate('async()=>{snap.policy.temperature_on=70;snap.policy.temperature_off=-10;snap.policy_revision++;await card.load()}')
    assert slider.get_attribute('max') == '70'
    assert slider.input_value() == '70'
    assert host.get_by_role('slider', name='溫度停止下限').input_value() == '-10'
    assert slider.get_attribute('min') == '-10'
    assert '−10～70' in host.locator('.threshold-group').first.inner_text()
    # Dirty scope is invalidated; detached completion cannot touch new UI.
    slider.focus();page.keyboard.press('ArrowLeft');host.get_by_role('button', name='儲存門檻').click()
    page.evaluate('()=>{card.remove();finishSave()}')
    page.wait_for_timeout(20)
    assert page.evaluate('()=>card.snapshot') is None
    assert page.evaluate('()=>card.thresholdDraft') is None
    page.evaluate('()=>{document.body.append(card);card.hass=fakeHass}')
    page.wait_for_function('card.snapshot && !card.loading')
    page.evaluate('async()=>{snap.policy={temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120};snap.policy_revision++;await card.load()}')
    # Admin and loaded-scope protections: no writes from read-only cards.
    page.evaluate('()=>{fakeHass.user.is_admin=false;card.hass={...fakeHass}}')
    assert slider.is_disabled()
    before = page.evaluate('()=>calls.length')
    page.evaluate('async()=>{card.editThreshold("temperature_on",34);await card.saveThresholds()}')
    assert page.evaluate('()=>calls.length') == before
    page.evaluate('()=>{fakeHass.user.is_admin=true;card.hass={...fakeHass}}')
    # Invalid legacy policy is visibly rejected; effective values are not replaced.
    page.evaluate('async()=>{snap.policy.temperature_on=100;snap.policy_revision++;await card.load()}')
    assert slider.is_disabled()
    assert '超出有效範圍' in host.locator('.validation').inner_text()
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 100
    page.evaluate('async()=>{snap.policy.temperature_on=29;snap.policy_revision++;await card.load()}')
    # Scope replacement during a dispatched Save must ignore its old completion.
    slider.focus();page.keyboard.press('ArrowRight');host.get_by_role('button', name='儲存門檻').click()
    page.evaluate('()=>{card.setConfig({...card.config,entry_id:"missing"});finishSave()}')
    page.wait_for_function('!card.loading')
    assert page.evaluate('()=>card.snapshot') is None
    assert page.evaluate('()=>card.thresholdDraft') is None
    assert host.locator('[data-save]').is_disabled()
    page.evaluate('()=>{card.setConfig({...card.config,entry_id:"demo-group"});card.hass=fakeHass}')
    page.wait_for_function('card.snapshot && !card.loading')
    page.evaluate('async()=>{snap.policy={temperature_on:29,temperature_off:25,humidity_on:93.4,humidity_off:81,duration_seconds:120};snap.policy_revision++;for(const r of Object.values(snap.runtime))r.reason="threshold_not_met";await card.load()}')
    demo = browser.new_page(viewport={'width':1530,'height':1200})
    demo.goto((ROOT/'tests/fixtures/approved-threshold-a.html').as_uri())
    demo.wait_for_function('demo.card.snapshot && !demo.card.loading')
    geometry = []
    measure = '''()=>{const c=window.card||window.demo.card,s=c.shadowRoot,r=s.querySelector('.threshold-grid').getBoundingClientRect();return [...s.querySelectorAll('.threshold-group,.slider-row,.slider-row input,.slider-row output')].map(e=>{const b=e.getBoundingClientRect();return {class:e.className,tag:e.tagName,x:b.x-r.x,y:b.y-r.y,w:b.width,h:b.height}})}'''
    composition = '''()=>{const c=window.card||window.demo.card,s=c.shadowRoot,r=c.getBoundingClientRect();return [...s.querySelectorAll('.header,.global,.global-body,.fans,.fan-item,.card-note')].map(e=>{const b=e.getBoundingClientRect();return {class:e.className,x:b.x-r.x,y:b.y-r.y,w:b.width,h:b.height}})}'''
    for theme in ('light','dark'):
        for layout in ('auto','2'):
            for width in (390,500,720,1080):
                page.evaluate('args=>{const [width,theme,layout]=args;card.style.width=width+"px";card.setConfig({...card.config,theme,layout});card.hass=fakeHass}', [width,theme,layout])
                page.wait_for_function('card.snapshot && !card.loading')
                page.evaluate('()=>{card.expanded=true;card.render()}')
                demo.evaluate('args=>{const [width,theme,layout]=args;demo.card.style.width=width+"px";demo.card.setConfig({...demo.card.config,theme,layout});demo.card.hass=demo.hass}', [width,theme,layout])
                demo.wait_for_function('demo.card.snapshot && !demo.card.loading')
                ac,bc=page.evaluate(composition),demo.evaluate(composition)
                assert len(ac)==len(bc)==7
                for a,b in zip(ac,bc):
                    for key in ('x','y','w','h'): assert abs(a[key]-b[key])<=1,(theme,layout,width,a,b)
                actual, approved = page.evaluate(measure), demo.evaluate(measure)
                assert len(actual) == len(approved) == 14
                for a,b in zip(actual,approved):
                    for key in ('x','y','w','h'): assert abs(a[key]-b[key]) <= 1, (theme,layout,width,a,b)
                overflow = page.evaluate('()=>[...card.shadowRoot.querySelectorAll(".card,.global,.global-body,.threshold-grid,.threshold-group,.slider-row,.fans")].map(e=>e.scrollWidth-e.clientWidth)')
                assert max(overflow) <= 1, (width, overflow)
                assert host.locator('[data-save]').bounding_box()['height'] >= 44
                groups = [x for x in actual if x['class']=='threshold-group']
                assert (groups[0]['y']==groups[1]['y']) == (width-34 > 520)
                geometry.append({'theme':theme,'layout':layout,'width':width,'max_geometry_delta':max(abs(a[k]-b[k]) for a,b in zip(actual,approved) for k in ('x','y','w','h')),'overflow':overflow})
                if layout=='2' and width in (390,720):
                    host.screenshot(path=str(OUT/f'threshold-production-{theme}-{width}.png'))
                    demo.locator('uninus-greenhouse-fan-card').screenshot(path=str(OUT/f'threshold-approved-a-{theme}-{width}.png'))
    assert not errors, errors
    result={'geometry':geometry,'interaction':'pointer drag, keyboard, Save/Cancel, validation, pending, failure, stale/conflict, detach passed','errors':errors}
    (OUT/'threshold-layout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print(json.dumps(result,ensure_ascii=False))
