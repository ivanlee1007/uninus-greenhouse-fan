"""Global card ranges: real integer gestures, untouched legacy precision and CAS."""
from pathlib import Path
import hashlib
import json
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('CARD_TEST_SOURCE', ROOT/'www/uninus-greenhouse-fan-card.js'))
OUT = ROOT/'tests/evidence'
KEYS = ['temperature_on', 'temperature_off', 'humidity_on', 'humidity_off']
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None), headless=True)
    page = browser.new_page(viewport={'width':1000, 'height':1200})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content('<!doctype html><body style="margin:0"></body>')
    page.add_script_tag(path=str(SOURCE))
    page.evaluate('''()=>{
      window.calls=[];
      window.snap={entry_id:'demo',revision:7,policy_revision:3,control_mode:'auto',policy:{temperature_on:37.7,temperature_off:20.3,humidity_on:90.4,humidity_off:60.2,duration_seconds:123},devices:[{device_id:'a',name:'A',fan_entity:'switch.a'}],bindings:{},runtime:{'switch.a':{mode:'auto'}}};
      window.fakeHass={user:{is_admin:true},states:{'switch.a':{state:'off',attributes:{}}},callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return[{entry_id:'demo',name:'Demo',loaded:true}];if(msg.type.endsWith('/save_thresholds'))return new Promise((resolve,reject)=>{window.finishSave=()=>{Object.assign(snap.policy,msg.thresholds);snap.policy_revision++;resolve(structuredClone(snap))};window.failSave=code=>reject({code,message:code});window.badSave=()=>resolve({...structuredClone(snap),policy_revision:msg.expected_policy_revision+1})});return structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');card.style.width='720px';card.setConfig({entry_id:'demo',items:snap.devices,layout:'2',theme:'light'});document.body.append(card);card.hass=fakeHass;
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    host = page.locator('uninus-greenhouse-fan-card')
    host.locator('.global summary').click()
    page.wait_for_function('card.expanded')

    def slider(key):
        return host.locator('#'+key)

    def outputs():
        return page.evaluate('()=>Object.fromEntries([...card.shadowRoot.querySelectorAll("[data-threshold]")].map(e=>[e.id,e.nextElementSibling.textContent]))')


    def cancel():
        host.get_by_role('button', name='取消修改').click()
        page.wait_for_function('!card.loading')

    def save_calls():
        return page.evaluate('()=>calls.filter(x=>x.type.endsWith("/save_thresholds"))')

    def assert_only_expected_writes():
        assert page.evaluate('()=>calls.every(x=>["/groups","/get","/save_thresholds"].some(s=>x.type.endsWith(s)))')

    # This must fail on the exact old bundle, before gestures or implementation.
    for key in KEYS:
        assert slider(key).get_attribute('step') == '1', (key, 'expected step=1', slider(key).get_attribute('step'))
        assert slider(key).get_attribute('min') == '0'
        assert slider(key).get_attribute('max') == ('50' if key.startswith('temperature') else '100')
    legacy = {'temperature_on':37.7, 'temperature_off':20.3, 'humidity_on':90.4, 'humidity_off':60.2}
    assert outputs() == {k:str(v)+(' °C' if k.startswith('temperature') else ' %') for k,v in legacy.items()}
    assert page.evaluate('()=>card.thresholdDraft') is None
    initial_summary = host.locator('.limit-pair').all_text_contents()

    page.evaluate('async()=>{card.hass={...fakeHass};await card.load({background:true})}')
    assert outputs()['temperature_on'] == '37.7 °C'
    assert page.evaluate('()=>card.thresholdDraft') is None
    assert len(save_calls()) == 0
    gestures = []
    for key in KEYS:
        control = slider(key)
        page.evaluate('key=>window.activeInput=card.shadowRoot.getElementById(key)', key)
        box = control.bounding_box()
        # Each complete pointer gesture straddles a real background refresh.
        target = .83 if key.endswith('_on') else .2
        page.mouse.move(box['x']+box['width']*.5, box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']*(target-.04), box['y']+box['height']/2, steps=5)
        page.evaluate('async()=>{card.hass={...fakeHass};await card.load({background:true})}')
        assert page.evaluate('()=>activeInput.isConnected && activeInput===card.shadowRoot.getElementById(activeInput.id)')
        page.mouse.move(box['x']+box['width']*target, box['y']+box['height']/2, steps=5)
        page.mouse.up()
        pointer = page.evaluate('key=>card.thresholdDraft.values[key]', key)
        assert type(pointer) is int, (key, pointer)
        assert outputs()[key] == str(pointer)+(' °C' if key.startswith('temperature') else ' %')
        control.focus()
        page.keyboard.press('ArrowRight')
        keyboard = page.evaluate('key=>card.thresholdDraft.values[key]', key)
        assert type(keyboard) is int and keyboard == pointer+1, (key, pointer, keyboard)
        page.evaluate('async()=>{card.hass={...fakeHass};await card.load({background:true})}')
        assert page.evaluate('()=>card.shadowRoot.activeElement===activeInput && activeInput.isConnected')
        assert outputs()[key] == str(keyboard)+(' °C' if key.startswith('temperature') else ' %')
        draft = page.evaluate('()=>card.thresholdDraft')
        assert draft['revision'] == 3
        for untouched in KEYS:
            if untouched != key:
                assert draft['values'][untouched] == legacy[untouched]
        assert host.locator('.limit-pair').all_text_contents() == initial_summary
        assert len(save_calls()) == 0
        gestures.append({'key':key, 'pointer':pointer, 'keyboard':keyboard})
        assert_only_expected_writes()
        cancel()
        assert page.evaluate('()=>card.snapshot.policy') == {**legacy, 'duration_seconds':123}
        assert outputs()[key] == str(legacy[key])+(' °C' if key.startswith('temperature') else ' %')
        assert len(save_calls()) == 0
        control.focus()
        page.keyboard.press('Home')
        assert page.evaluate('key=>card.thresholdDraft.values[key]', key) == 0
        page.keyboard.press('End')
        assert page.evaluate('key=>card.thresholdDraft.values[key]', key) == (50 if key.startswith('temperature') else 100)
        cancel()
        assert len(save_calls()) == 0

    # Only finite numbers are rounded: invalid typed candidates remain invalid,
    # never coerced into 0/1 and never sent to the backend.
    for index in range(7):
        page.evaluate('index=>card.editThreshold("temperature_on",[true,false,NaN,Infinity,-Infinity,"38.4",null][index])', index)
        assert host.get_by_role('button', name='儲存門檻').is_disabled(), index
        page.evaluate('()=>card.saveThresholds()')
        assert len(save_calls()) == 0
        cancel()
    page.evaluate('()=>card.editThreshold("temperature_on",38.4)')
    assert page.evaluate('()=>card.thresholdDraft.values.temperature_on') == 38
    assert outputs()['temperature_on'] == '38 °C'
    host.get_by_role('button', name='儲存門檻').click()
    payload = save_calls()[-1]
    assert payload['expected_policy_revision'] == 3
    assert payload['thresholds'] == {**legacy, 'temperature_on':38}
    assert host.locator('.limit-pair').all_text_contents() == initial_summary
    page.evaluate('()=>badSave()')
    page.wait_for_function('!card.operation')
    assert page.evaluate('()=>card.thresholdDraft.values.temperature_on') == 38
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 37.7
    assert host.get_by_role('button', name='儲存門檻').is_disabled()
    slider('temperature_on').focus()
    page.keyboard.press('ArrowRight')
    page.keyboard.press('ArrowLeft')
    host.get_by_role('button', name='儲存門檻').click()
    page.evaluate('()=>finishSave()')
    page.wait_for_function('!card.operation')
    assert page.evaluate('()=>card.thresholdDraft') is None
    assert page.evaluate('()=>card.snapshot.policy') == {**legacy, 'temperature_on':38, 'duration_seconds':123}
    assert outputs()['temperature_on'] == '38 °C'

    # Expanded bounds are whole-number tick anchors, initialized and live alike.
    page.evaluate('async()=>{snap.policy.temperature_on=70.5;snap.policy.temperature_off=-10.5;snap.policy_revision++;await card.load()}')
    assert page.evaluate('()=>card.thresholdDraft') is None
    # Parse the production markup with fixture-only numeric policy, no untrusted HTML.
    initial_attributes = page.evaluate('()=>{const t=document.createElement("template");t.innerHTML=card.thresholdMarkup();return [...t.content.querySelectorAll("input[type=range]")].map(e=>[e.id,e.getAttribute("min"),e.getAttribute("max"),e.getAttribute("step"),e.nextElementSibling.textContent])}')
    assert initial_attributes[:2] == [['temperature_on','-11','71','1','70.5 °C'], ['temperature_off','-11','71','1','-10.5 °C']]
    for force_render in (False, True):
        if force_render:
            page.evaluate('()=>card.render()')
        for key in KEYS[:2]:
            assert slider(key).get_attribute('min') == '-11'
            assert slider(key).get_attribute('max') == '71'
            assert slider(key).get_attribute('step') == '1'
        assert outputs()['temperature_on'] == '70.5 °C'
        assert outputs()['temperature_off'] == '-10.5 °C'
    for key, press, expected in [('temperature_on','ArrowLeft',70),('temperature_off','ArrowRight',-9)]:
        slider(key).focus()
        page.keyboard.press(press)
        assert page.evaluate('key=>card.thresholdDraft.values[key]', key) == expected
        assert outputs()[key] == str(expected)+' °C'
        cancel()
    assert page.evaluate('()=>card.snapshot.policy.temperature_on') == 70.5
    assert page.evaluate('()=>card.snapshot.policy.temperature_off') == -10.5
    assert len(save_calls()) == 2

    # One explicit Save of all four edited controls sends only integer fields.
    page.evaluate('async()=>{snap.policy={temperature_on:37.7,temperature_off:20.3,humidity_on:90.4,humidity_off:60.2,duration_seconds:123};snap.policy_revision++;await card.load()}')
    revision = page.evaluate('()=>card.snapshot.policy_revision')
    for key in KEYS:
        slider(key).focus()
        page.keyboard.press('ArrowRight')
    all_edited = page.evaluate('()=>card.thresholdDraft.values')
    assert all(type(v) is int for v in all_edited.values())
    host.get_by_role('button', name='儲存門檻').click()
    all_payload = save_calls()[-1]
    assert all_payload['thresholds'] == all_edited
    assert all_payload['expected_policy_revision'] == revision
    page.evaluate('()=>finishSave()')
    page.wait_for_function('!card.operation')
    assert page.evaluate('()=>card.snapshot.policy') == {**all_edited, 'duration_seconds':123}
    assert page.evaluate('()=>card.thresholdDraft') is None
    assert len(save_calls()) == 3
    assert_only_expected_writes()
    assert not errors, errors
    result = {'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'gestures':gestures, 'legacy_preserved':True, 'integer_bounds':[-11,71], 'legacy_initial_attributes':initial_attributes, 'save_payload':payload, 'all_edited_payload':all_payload, 'save_calls':len(save_calls()), 'errors':errors, 'limitations':'Native range thumb/value snaps to its nearest whole tick; output and untouched policy/draft retain the exact legacy fraction until that control is edited.'}
    OUT.mkdir(exist_ok=True)
    (OUT/'integer-sliders-browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    browser.close()
print(json.dumps(result,ensure_ascii=False))
