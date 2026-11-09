"""Real browser computed colors and live transitions; no physical outputs."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=os.environ.get('HERMES_TEST_BROWSER') or (str(edge) if edge.exists() else None), headless=True)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_content('<!doctype html><body></body>')
    page.add_script_tag(path=str(ROOT / 'www/uninus-greenhouse-fan-card.js'))
    page.evaluate('''() => {
      window.calls=[];
      window.snap={entry_id:'g',revision:1,policy_revision:0,control_mode:'auto',policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},devices:[{device_id:'d',fan_entity:'fan.a',name:'Fan'}],bindings:{'fan.a':{temperature_entity:'sensor.t',humidity_entity:'sensor.h'}},runtime:{'fan.a':{mode:'auto'}}};
      window.h={states:{'fan.a':{state:'on',attributes:{}},'sensor.t':{state:'24',attributes:{unit_of_measurement:'°C',device_class:'temperature'}},'sensor.h':{state:'59',attributes:{unit_of_measurement:'%',device_class:'humidity'}}},callWS:async m=>{calls.push(m);return m.type.endsWith('/groups')?[{entry_id:'g',name:'Group',loaded:true}]:structuredClone(snap)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');document.body.append(card);
      card.setConfig({entry_id:'g',items:[{device_id:'d'}]});card.hass=h;
      window.colors=()=>[...card.shadowRoot.querySelectorAll('.live-line')].map(n=>({kind:n.classList.contains('threshold-low')?'low':n.classList.contains('threshold-high')?'high':'normal',color:getComputedStyle(n.querySelector('strong')).color,unit:getComputedStyle(n.querySelector('small')).color,underline:getComputedStyle(n.querySelector('strong')).textDecorationLine}));
    }''')
    page.wait_for_function('card.snapshot && !card.loading')
    cases = 0
    for theme, good, danger in [('dark', 'rgb(131, 237, 176)', 'rgb(255, 173, 165)'), ('light', 'rgb(0, 128, 68)', 'rgb(177, 44, 36)')]:
        for layout in (None, 'compact', 'columns', 'split'):
            page.evaluate('''a=>{card.setConfig({...card.config,theme:a[0],lock_readings_right:a[1]!==null,readings_layout:a[1]})}''', [theme, layout])
            page.wait_for_function('card.snapshot && !card.loading')
            for temp, hum, expected in [('24','59',['low','low']), ('25','60',['normal','normal']), ('24','81',['low','high']), ('31','59',['high','low']), ('unavailable','unknown',['normal','normal']), ('26','65',['normal','normal'])]:
                page.evaluate('''a=>{h.states['sensor.t'].state=a[0];h.states['sensor.h'].state=a[1];card.hass={...h}}''', [temp, hum])
                results = page.evaluate('colors()')
                assert [r['kind'] for r in results] == expected, results
                for result in results:
                    if result['kind'] != 'normal':
                        color = good if result['kind'] == 'low' else danger
                        assert result['color'] == result['unit'] == color, result
                        if result['kind'] == 'high':
                            assert result['underline'] == 'none', result
                cases += 1
    assert page.evaluate("calls.every(m=>m.type.endsWith('/get') || m.type.endsWith('/groups'))")
    assert not errors, errors
    browser.close()
print(f'PASS: {cases} browser cases, both themes, all reading layouts; no backend writes or page errors')
