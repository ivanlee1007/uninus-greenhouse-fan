"""Real Chromium user flows; offline HA/picker protocol fixture, no live writes."""
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
    page = browser.new_page(viewport={'width':1200,'height':1100})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content('<body style="margin:0"><button id="save">Save</button><button id="cancel">Cancel</button><div id="edit"></div><div id="display"></div></body>')
    # This fixture models the native picker event contract, not its implementation.
    # Fixture innerHTML is static; entity/search strings enter DOM via textContent.
    page.evaluate('''()=>{
      customElements.define('ha-entity-picker',class extends HTMLElement{
        constructor(){super();this.attachShadow({mode:'open'});this._value=''}
        connectedCallback(){this.shadowRoot.innerHTML='<input aria-label="Search entities"><div class="choices"></div><button class="clear">Clear entity</button>';this.shadowRoot.querySelector('input').addEventListener('input',()=>this.options());this.shadowRoot.querySelector('.clear').onclick=()=>this.choose('');this.options()}
        set hass(v){this._hass=v;if(this.isConnected)this.options()} get hass(){return this._hass}
        set value(v){this._value=v} get value(){return this._value}
        options(){const list=this.shadowRoot.querySelector('.choices');if(!list)return;list.replaceChildren();const q=this.shadowRoot.querySelector('input').value;for(const id of Object.keys(this.hass?.states||{}).filter(id=>id.includes(q))){const b=document.createElement('button');b.textContent=id;b.onclick=()=>{this.dispatchEvent(new Event('change',{bubbles:true,composed:true}));this.choose(id)};list.append(b)}}
        choose(id){this.value=id;this.dispatchEvent(new CustomEvent('value-changed',{bubbles:true,composed:true,detail:{value:id}}))}
      });
    }''')
    page.add_script_tag(path=str(ROOT / 'www/uninus-greenhouse-fan-card.js'))
    page.evaluate('''()=>{
      window.calls=[];window.events=[];window.saved={entry_id:'g',name:'House',items:[{device_id:'d',fan_entity:'switch.fan',name:'Front'}],layout:'2',theme:'dark'};
      window.view={entry_id:'g',control_mode:'auto',devices:[{device_id:'d',fan_entity:'switch.fan',name:'Fan'}],policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60},bindings:{},runtime:{'switch.fan':{mode:'on'}}};
      window.h={states:{'switch.fan':{state:'on',attributes:{}},'sensor.subtitle':{state:'0',attributes:{unit_of_measurement:'°C'}},'switch.subtitle':{state:'off',attributes:{}},'input_text.subtitle':{state:'Welcome',attributes:{}},'weather.subtitle':{state:'rainy',attributes:{temperature:0,flag:false,data:[0,false],unit_of_measurement:'°C'}}},callWS:async msg=>{calls.push(msg);return msg.type.endsWith('/groups')?[{entry_id:'g',loaded:true,name:'Group'}]:structuredClone(view)}};
      window.card=document.createElement('uninus-greenhouse-fan-card');display.append(card);card.style.width='390px';card.setConfig(saved);card.hass=h;
      window.openEditor=()=>{edit.replaceChildren();window.editor=document.createElement('uninus-greenhouse-fan-card-editor');edit.append(editor);editor.style.width='390px';editor.setConfig(saved);editor.hass=h;editor.addEventListener('config-changed',e=>{window.draft=e.detail.config;events.push(draft);card.setConfig(draft)})};
      save.onclick=()=>{saved=structuredClone(draft||saved);openEditor()};cancel.onclick=()=>{draft=saved;openEditor();card.setConfig(saved)};openEditor();
    }''')
    page.wait_for_function('editor.snapshot && !editor.loading && card.snapshot && !card.loading')
    e = page.locator('uninus-greenhouse-fan-card-editor')
    c = page.locator('uninus-greenhouse-fan-card')
    text = e.get_by_role('textbox', name='副標題文字', exact=True)
    text.fill('<img src=x onerror=alert(1)> & visible')
    assert c.locator('.sub').inner_text() == '<img src=x onerror=alert(1)> & visible'
    assert c.locator('img').count() == 0
    page.locator('#save').click()
    page.wait_for_function('editor.snapshot && !editor.loading')
    page.evaluate("()=>view.devices.push({device_id:'second',fan_entity:'switch.second',name:'New configured'})")
    e.get_by_role('button', name='重新讀取裝置').click()
    page.wait_for_function('!editor.loading')
    assert 'New configured' in e.locator('select[data-field="device_id"]').inner_text(), 'focused refresh button prevented new inventory render'
    assert text.input_value() == '<img src=x onerror=alert(1)> & visible'
    e.locator('select[data-config="theme"]').select_option('light')
    assert text.input_value() == '<img src=x onerror=alert(1)> & visible'
    e.locator('select[data-config="subtitle_mode"]').select_option('entity')
    picker = e.locator('ha-entity-picker')
    assert page.evaluate('()=>editor.shadowRoot.querySelector("ha-entity-picker").hass===h')
    assert page.evaluate('()=>editor.shadowRoot.querySelector("ha-entity-picker").includeDomains===undefined')
    for domain in ('sensor','switch','input_text','weather'):
        search = picker.get_by_role('textbox', name='Search entities')
        search.fill(domain+'.subtitle')
        picker.get_by_role('button', name=domain+'.subtitle', exact=True).click()
        assert page.evaluate('()=>draft.subtitle_entity') == domain+'.subtitle'
        assert page.evaluate('()=>editor.shadowRoot.querySelector("ha-entity-picker").value') == domain+'.subtitle'
    search.fill('weather.sub')
    page.evaluate('()=>{window.searchPicker=editor.shadowRoot.querySelector("ha-entity-picker");h.states["weather.subtitle"].state="sunny";editor.hass=h;editor.load()}')
    page.wait_for_function('!editor.loading')
    assert page.evaluate('()=>searchPicker===editor.shadowRoot.querySelector("ha-entity-picker")'), 'refresh disconnected active picker'
    assert search.input_value() == 'weather.sub'
    assert e.locator('[data-subtitle-preview]').inner_text() == 'sunny °C'
    attr = e.get_by_role('textbox', name='副標題屬性', exact=True)
    for key, expected in [('temperature','0'),('flag','false'),('data','[0,false]'),('missing','—'),('','sunny °C')]:
        attr.fill(key)
        assert c.locator('.sub').inner_text() == expected
        assert e.locator('[data-subtitle-preview]').inner_text() == expected
    page.locator('#save').click()
    page.wait_for_function('editor.snapshot && !editor.loading')
    assert page.evaluate('()=>editor.shadowRoot.querySelector("ha-entity-picker").value') == 'weather.subtitle'
    assert page.evaluate('()=>saved.name==="House" && saved.items[0].device_id==="d"')
    picker.get_by_role('button', name='Clear entity').click()
    assert page.evaluate('()=>events.at(-1).subtitle_entity') == ''
    assert c.locator('.sub').count() == 0
    page.locator('#cancel').click()
    page.wait_for_function('editor.snapshot && !editor.loading')
    assert c.locator('.sub').inner_text() == 'sunny °C'
    picker.get_by_role('button', name='Clear entity').click()
    page.locator('#save').click()
    page.wait_for_function('editor.snapshot && !editor.loading')
    assert page.evaluate('()=>editor.config.subtitle_entity') == ''
    assert c.locator('.sub').count() == 0
    measurements = []
    for theme in ('dark','light'):
        for width in (390,500,720,1080):
            for layout in ('auto','2'):
                for global_mode,hold in [('manual','on'),('auto','on'),('auto','auto')]:
                    page.evaluate('''args=>{const [theme,width,layout,mode,hold]=args;view.control_mode=mode;view.runtime['switch.fan'].mode=hold;card.style.width=width+'px';card.setConfig({...saved,theme,layout,subtitle_mode:'entity',subtitle_entity:'weather.subtitle',subtitle_attribute:'data'});card.hass=h;card.load()}''',[theme,width,layout,global_mode,hold])
                    page.wait_for_function('card.snapshot && !card.loading')
                    geometry = page.evaluate('''()=>{const s=card.shadowRoot,summary=s.querySelector('.global summary'),toggle=s.querySelector('.mode-switch'),limits=s.querySelector('.limits'),r=toggle.getBoundingClientRect(),q=summary.getBoundingClientRect(),style=getComputedStyle(toggle);return {gap:q.right-r.right,top:r.top,bottom:r.bottom,summaryTop:q.top,summaryBottom:q.bottom,limitsRight:limits.getBoundingClientRect().right,toggleLeft:r.left,width:r.width,height:r.height,border:style.borderTopWidth,background:style.backgroundColor,shadow:style.boxShadow,label:toggle.innerText,overflow:[s.querySelector('.card'),summary,limits,...s.querySelectorAll('.limit-pair,.fan-item,.sub')].map(x=>x.scrollWidth-x.clientWidth)}}''')
                    assert geometry['gap'] == 10, geometry
                    assert geometry['limitsRight'] <= geometry['toggleLeft'], geometry
                    assert geometry['width'] >= 44 and geometry['height'] >= 44, geometry
                    assert geometry['summaryTop'] <= geometry['top'] and geometry['bottom'] <= geometry['summaryBottom'], geometry
                    assert geometry['border'] == '0px' and geometry['background'] == 'rgba(0, 0, 0, 0)' and geometry['shadow'] == 'none', geometry
                    assert geometry['label'] == '自動', geometry
                    assert max(geometry['overflow']) <= 1, geometry
                    assert c.locator('button.resume').count() == int(global_mode=='auto' and hold=='on')
                    measurements.append({'theme':theme,'width':width,'layout':layout,'mode':global_mode,'hold':hold,**{('toggle_width' if key=='width' else key):value for key,value in geometry.items()}})
    source_cases = []
    for theme in ('dark','light'):
        for width in (390,500):
            for entity, attribute, unit, expected in [
                ('sensor.subtitle','',True,'0 °C'), ('sensor.subtitle','',False,'0'),
                ('switch.subtitle','',True,'off'), ('input_text.subtitle','',True,'Welcome'),
                ('weather.subtitle','temperature',True,'0'), ('weather.subtitle','flag',True,'false'),
                ('weather.subtitle','data',True,'[0,false]'), ('weather.subtitle','absent',True,'—'),
                ('sensor.missing','',True,'—')]:
                page.evaluate('''args=>{const [theme,width,entity,attribute,unit]=args;card.style.width=width+'px';card.setConfig({...saved,theme,subtitle_mode:'entity',subtitle_entity:entity,subtitle_attribute:attribute,subtitle_unit:unit});card.hass=h}''',[theme,width,entity,attribute,unit])
                assert c.locator('.sub').inner_text() == expected
                assert c.locator('.sub').evaluate('(x)=>x.scrollWidth-x.clientWidth') <= 1
                source_cases.append([theme,width,entity,attribute,unit,expected])
            page.evaluate('''args=>{const [theme,width]=args;h.states['input_text.subtitle'].state='<b>'+('x'.repeat(1000))+'</b>';card.setConfig({...saved,theme,subtitle_mode:'entity',subtitle_entity:'input_text.subtitle',subtitle_attribute:''});card.hass=h}''',[theme,width])
            assert len(c.locator('.sub').inner_text()) == 256
            assert c.locator('.sub b').count() == 0
            assert c.locator('.sub').evaluate('(x)=>x.scrollWidth-x.clientWidth') <= 1
            page.evaluate("()=>h.states['input_text.subtitle'].state='Welcome'")
    assert page.evaluate('()=>calls.every(x=>x.type.endsWith("/groups") || x.type.endsWith("/get"))'), 'editor performed backend write'
    assert not errors, errors
    (OUT / 'subtitle-layout.json').write_text(json.dumps({'picker':'offline native-event-contract fixture; not live HA frontend','user_flow':'text/entity save/reopen/clear/cancel; active search refresh','measurements':measurements,'source_cases':source_cases,'errors':errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()
print(json.dumps({'user_flow':'passed','measurements':len(measurements),'errors':errors}))
