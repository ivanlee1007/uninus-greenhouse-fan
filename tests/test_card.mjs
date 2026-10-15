import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../www/uninus-greenhouse-fan-card.js', import.meta.url), 'utf8');
function setup() {
  const registry = new Map();
  class Element {
    constructor() { this.shadowRoot = {innerHTML:'', addEventListener() {}, querySelector() { return null; }}; }
    attachShadow() { return this.shadowRoot; }
    dispatchEvent(e) { (this.events ||= []).push(e); return true; }
  }
  const ctx = {HTMLElement:Element, customElements:{get:n=>registry.get(n), define:(n,c)=>registry.set(n,c)},
    window:{customCards:[]}, CustomEvent:class {constructor(type,opts) {this.type=type; Object.assign(this,opts);}},
    console, setTimeout, clearTimeout, setInterval, clearInterval};
  vm.runInNewContext(source, ctx);
  return {Card:registry.get('uninus-greenhouse-fan-card'), Editor:registry.get('uninus-greenhouse-fan-card-editor')};
}
test('global device details option is a typed display-only boolean with legacy default', async () => {
  const {Card,Editor}=setup();
  assert.equal(Card.getStubConfig().show_device_details,true);
  await new Promise(resolve=>setTimeout(resolve,0));
  for(const value of [undefined,null,0,'false',{},true,false]) {
    const el=new Card();el.setConfig({...config,show_device_details:value});el.hass=groupHass();await flush();
    assert.equal(el.config.show_device_details,value!==false);
    const html=el.renderFan(el.config.items[0]);
    assert.equal(html.includes('class="device-details"'),value!==false);
    assert.match(html,/class="controls"/);assert.match(html,/class="badge"/);assert.match(html,/目前溫度/);
  }
  const editor=new Editor();editor.setConfig(config);editor.hass=groupHass();await flush();
  for(const checked of [false,true]) {
    editor.handleChange({type:'change',target:{dataset:{config:'show_device_details'},checked,value:'on'}});
    const saved=editor.events.at(-1).detail.config;assert.equal(saved.show_device_details,checked);
    const reopened=new Editor();reopened.setConfig(saved);assert.equal(reopened.config.show_device_details,checked);
  }
});
const states = {
  'fan.a':{state:'on',attributes:{friendly_name:'Fan A'}},
  'fan.b':{state:'off',attributes:{}},
  'switch.relay':{state:'off',attributes:{friendly_name:'Fan relay'}},
  'sensor.t':{state:'32.5',attributes:{unit_of_measurement:'°C',device_class:'temperature'}},
  'sensor.h':{state:'73',attributes:{unit_of_measurement:'%',device_class:'humidity'}},
};
const snapshot = (revision=2) => ({entry_id:'group-1',revision,devices:['fan.a','fan.b','switch.relay'].map(fan=>({device_id:fan,name:fan,fan_entity:fan})),policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},bindings:{'fan.a':{temperature_entity:'sensor.t',humidity_entity:'sensor.h'}},runtime:{'fan.a':{mode:'auto',pending:null,reason:'Ready'}}});
const config = {type:'custom:uninus-greenhouse-fan-card',entry_id:'group-1',name:'House',items:[{fan_entity:'fan.a',name:'Front'}],layout:'auto',theme:'dark'};
test('threshold save error contains one clear message and committed UI fault clears draft', async () => {
  for(const committed of [false,true]){
    const {Card}=setup(),el=new Card();el.setConfig(config);const view={...snapshot(),policy_revision:0};
    el.hass={...groupHass(groups,msg=>{
      if(!msg.type.endsWith('/save_thresholds'))return view;
      if(!committed)throw {code:'save_failed',message:'門檻儲存失敗；草稿保留，請檢查日誌。'};
      return {...view,policy_revision:1,policy:{...view.policy,temperature_on:35},save_status:'committed_publication_failed',save_warning:'門檻已儲存；顯示更新失敗，控制已停用。請重新載入整合。'};
    }),user:{is_admin:true}};await flush();el.editThreshold('temperature_on',35);await el.saveThresholds();
    if(committed){assert.equal(el.thresholdDraft,null);assert.match(el.policyNotice,/顯示更新失敗/)}
    else{assert.equal((el.policyError.match(/門檻儲存失敗/g)||[]).length,1);assert.ok(el.thresholdDraft)}
  }
});
test('threshold response rejects changed duration and stale revision without clearing draft', async () => {
  for(const override of [{policy_revision:0},{policy:{...snapshot().policy,temperature_on:35,duration_seconds:1}}]){
    const {Card}=setup(),el=new Card();el.setConfig(config);
    const view={...snapshot(),policy_revision:0};
    el.hass={...groupHass(groups,msg=>msg.type.endsWith('/save_thresholds')?{...view,policy_revision:1,policy:{...view.policy,temperature_on:35},...override}:view),user:{is_admin:true}};await flush();
    el.editThreshold('temperature_on',35);await el.saveThresholds();
    assert.ok(el.thresholdDraft);assert.equal(el.snapshot.policy.temperature_on,30);assert.match(el.policyError,/核對/);
  }
});
test('threshold draft survives unrelated revision but never rebases policy on poll', async () => {
  const {Card}=setup(),el=new Card();el.setConfig(config);let view={...snapshot(),policy_revision:0};let writes=0;
  el.hass={...groupHass(groups,msg=>{if(msg.type.endsWith('/save_thresholds'))writes++;return view}),user:{is_admin:true}};await flush();
  el.editThreshold('temperature_on',35);view={...view,revision:99};await el.load();
  assert.equal(el.thresholdDraft.revision,0);assert.equal(el.thresholdStale(),false);
  view={...view,policy_revision:1,policy:{...view.policy,temperature_on:36}};await el.load();
  assert.equal(el.thresholdDraft.revision,0);assert.equal(el.thresholdDraft.values.temperature_on,35);assert.equal(el.thresholdStale(),true);
  await el.saveThresholds();assert.equal(writes,0);
});
test('threshold draft only, explicit atomic save, cancel, pending serialization', async () => {
  const {Card}=setup(), el=new Card();el.setConfig(config);let finish;
  let view={...snapshot(),policy_revision:0};const calls=[];
  el.hass={...groupHass(groups,msg=>{calls.push(msg);return msg.type.endsWith('/save_thresholds')?new Promise(r=>finish=r):view}),user:{is_admin:true}};await flush();
  assert.equal(typeof el.editThreshold,'function');
  el.editThreshold('temperature_on',35);
  assert.equal(el.snapshot.policy.temperature_on,30);
  assert.equal(calls.filter(x=>x.type.endsWith('/save_thresholds')).length,0);
  el.cancelThresholds();assert.equal(el.thresholdDraft,null);await flush();
  el.editThreshold('temperature_on',35);
  const pending=el.saveThresholds();await el.saveThresholds();await el.manual('fan.a','off');await el.setControlMode('manual');
  const writes=calls.filter(x=>x.type.endsWith('/save_thresholds'));
  assert.equal(writes.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0])),{type:'uninus_greenhouse_fan/save_thresholds',entry_id:'group-1',expected_policy_revision:0,thresholds:{temperature_on:35,temperature_off:25,humidity_on:80,humidity_off:60}});
  assert.equal(el.snapshot.policy.temperature_on,30);
  finish({...view,policy_revision:1,policy:{...view.policy,temperature_on:35}});await pending;
  assert.equal(el.thresholdDraft,null);assert.equal(el.snapshot.policy.temperature_on,35);
});
test('global mutation errors and late completions are scoped and cannot bypass pending gate', async () => {
  const {Card}=setup(),el=new Card();el.setConfig(config);let reject;
  const calls=[];el.hass=groupHass(groups,msg=>{calls.push(msg);return msg.type.endsWith('/set_control_mode')?new Promise((resolve,r)=>reject=r):snapshot()});await flush();
  const pending=el.setControlMode('manual');
  await el.manual('fan.a','on');await el.setControlMode('auto');
  assert.equal(calls.filter(x=>x.type.endsWith('/set_control_mode')).length,1);
  el.disconnectedCallback();reject(Error('old fault'));await pending;
  assert.equal(el.snapshot,null);assert.equal(el.error,'');
  el.detached=false;el.setConfig({...config,name:'Retry'});await flush();
  const failed=el.setControlMode('manual');reject(Error('disk offline'));await failed;
  assert.equal(el.snapshot.control_mode,undefined);assert.match(el.error,/disk offline/);
  assert.match(el.shadowRoot.innerHTML,/role="alert"/);
});

test('auto threshold colors use separate finite native readings and strict boundaries', async () => {
  const {Card}=setup(),el=new Card();el.setConfig(config);let view=snapshot();
  el.hass=groupHass(groups,()=>view);await flush();
  for(const [t,h,mode,global,expected] of [[30,80,'auto','auto',0],[30.001,80,'auto','auto',1],[30,80.001,'auto','auto',1],[31,81,'auto','auto',2],[31,81,'on','auto',0],[31,81,'auto','manual',0],[null,'unknown','auto','auto',0],[true,'Infinity','auto','auto',0]]) {
    view={...snapshot(),control_mode:global,runtime:{'fan.a':{mode}}};
    el.hass={...el.hass,states:{...states,'sensor.t':{...states['sensor.t'],state:t},'sensor.h':{...states['sensor.h'],state:h}}};await el.load();
    assert.equal((el.renderFan(el.config.items[0]).match(/threshold-high/g)||[]).length,expected,JSON.stringify([t,h,mode,global]));
  }
  view={...snapshot(),bindings:{}};await el.load();assert.doesNotMatch(el.renderFan(el.config.items[0]),/threshold-high/);
});

test('global mode waits for authoritative response and blocks resume under global manual', async () => {
  const {Card}=setup(), el=new Card();el.setConfig(config);let finish;
  el.hass=groupHass(groups,msg=>msg.type.endsWith('/set_control_mode')?new Promise(r=>finish=r):snapshot());await flush();
  assert.equal(typeof el.setControlMode,'function');
  const initial=new Card();initial.setConfig(config);assert.match(initial.shadowRoot.innerHTML,/role="switch"[^>]*aria-checked="false"[^>]*disabled/);
  const pending=el.setControlMode('manual');
  assert.match(el.shadowRoot.innerHTML,/role="switch"[^>]*aria-checked="true"[^>]*disabled/);
  finish({...snapshot(),control_mode:'manual'});await pending;
  assert.equal(el.canManual('fan.a','auto'),false);
  assert.equal(el.canManual('fan.a','on'),true);
  assert.match(el.renderFan(el.config.items[0]),/全域手動/);
  assert.doesNotMatch(el.renderFan(el.config.items[0]),/threshold-high/);
  assert.match(el.shadowRoot.innerHTML,/role="switch"[^>]*aria-checked="false"/);
});

test('global manual hides Resume while pending mode changes retain authoritative holds', async () => {
  const {Card}=setup(),el=new Card();el.setConfig(config);let finish;
  const held={...snapshot(),control_mode:'auto',runtime:{'fan.a':{mode:'on'}}};
  el.hass=groupHass(groups,msg=>msg.type.endsWith('/set_control_mode')?new Promise(r=>finish=r):held);await flush();
  const html=el.shadowRoot.innerHTML;
  assert.match(html,/<span>自動<\/span><span class="switch-track"/);
  assert.ok(html.indexOf('class="limit-pair"')<html.indexOf('class="mode-switch"'));
  const pending=el.setControlMode('manual');assert.match(el.renderFan(el.config.items[0]),/class="resume"/);
  finish({...held,control_mode:'manual'});await pending;assert.doesNotMatch(el.renderFan(el.config.items[0]),/class="resume"/);
  const auto=el.setControlMode('auto');assert.doesNotMatch(el.renderFan(el.config.items[0]),/class="resume"/);
  finish(held);await auto;assert.match(el.renderFan(el.config.items[0]),/class="resume"/);
});

test('editor choices are owned configured devices, stable identity and no binding UI', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);
  const inventory={...snapshot(),devices:[{device_id:'opaque-a',name:'Configured A',fan_entity:'fan.a'},{device_id:'offline',name:'Offline configured',fan_entity:'switch.offline'}]};
  const calls=[];el.hass=groupHass(groups,msg=>{calls.push(msg);return inventory});await flush();
  assert.doesNotMatch(el.shadowRoot.innerHTML,/temperature_entity|humidity_entity|data-action="apply"|data-action="discard"|revision/);
  assert.match(el.shadowRoot.innerHTML,/Offline configured/);
  assert.doesNotMatch(el.shadowRoot.innerHTML,/switch\.relay/);
  el.setItemField(0,'device_id','opaque-a');
  assert.equal(el.config.items[0].device_id,'opaque-a');
  assert.equal(calls.filter(msg=>msg.type.endsWith('/bind')).length,0);
});

test('stable device selection follows output edits but never follows deleted identity', async () => {
  const {Card}=setup();const el=new Card();el.setConfig({...config,items:[{device_id:'stable',fan_entity:'fan.a'}]});
  let current={...snapshot(),devices:[{device_id:'stable',name:'One',fan_entity:'switch.relay'}]};const writes=[];
  el.hass=groupHass(groups,msg=>{if(msg.type.endsWith('/manual'))writes.push(msg);return current});await flush();
  assert.equal(el.output(el.config.items[0]),'switch.relay');await el.manual('fan.a','on');assert.equal(writes.length,0);
  await el.manual('switch.relay','off');assert.equal(writes[0].fan_entity,'switch.relay');
  current={...current,devices:[]};await el.load();await el.manual('fan.a','on');await el.manual('switch.relay','on');
  assert.equal(writes.length,1);assert.equal(el.output(el.config.items[0]),'');
});

test('unregistered literal YAML output displays safely but cannot dispatch', async () => {
  const {Card}=setup();const el=new Card();el.setConfig(config);let writes=0;
  el.hass=groupHass(groups,msg=>{if(msg.type.endsWith('/manual'))writes++;return {...snapshot(),devices:[]}});await flush();
  assert.match(el.shadowRoot.innerHTML,/禁止控制/);await el.manual('fan.a','on');assert.equal(writes,0);
});

test('loaded custom elements expose readable 0.5.2 build marker', () => {
  const {Card,Editor}=setup();assert.equal(Card.buildVersion,'0.5.2');assert.equal(Editor.buildVersion,'0.5.2');
});
test('subtitle text round trips editor config immediately and explicit empty hides legacy tagline', async () => {
  const {Card,Editor}=setup(),el=new Editor();el.setConfig(config);el.hass=groupHass();await flush();
  el.handleChange({type:'input',target:{dataset:{config:'subtitle_text'},value:'<img src=x onerror=alert(1)> & House'}});
  const saved=el.events.at(-1).detail.config;
  assert.equal(saved.subtitle_text,'<img src=x onerror=alert(1)> & House');
  const reopened=new Editor();reopened.setConfig(saved);assert.equal(reopened.config.subtitle_text,saved.subtitle_text);
  const card=new Card();card.setConfig(saved);assert.match(card.shadowRoot.innerHTML,/<p class="sub">&lt;img/);assert.doesNotMatch(card.shadowRoot.innerHTML,/<img/);
  card.setConfig(config);assert.match(card.shadowRoot.innerHTML,/<p class="sub">各區獨立感測/);
  card.setConfig({...saved,subtitle_text:''});assert.doesNotMatch(card.shadowRoot.innerHTML,/<p class="sub">/);
  assert.equal(saved.items[0].name,'Front');assert.equal(saved.name,'House');
});

test('entity subtitle resolves any domain scalar, units, attributes and bounded structured fallback', () => {
  const {Card}=setup(),card=new Card();
  const circular={};circular.self=circular;
  const broken={toJSON(){throw Error('bad')}};
  for(const [domain,value,attrs,attribute,unit,expected] of [
    ['sensor',0,{unit_of_measurement:'°C'},'',true,'0 °C'],['switch',false,{},'',true,'false'],['input_text','<b>unsafe</b>',{},'',true,'&lt;b&gt;unsafe&lt;/b&gt;'],['weather','rainy',{},'',false,'rainy'],
    ['sensor','unknown',{},'',true,'—'],['switch','unavailable',{},'',true,'—'],['sensor',Infinity,{},'',true,'—'],['sensor',null,{},'',true,'—'],
    ['weather','sunny',{temperature:0,unit_of_measurement:'°C'},'temperature',true,'0'],['weather','sunny',{enabled:false},'enabled',true,'false'],['weather','sunny',{},'missing',true,'—'],
    ['weather','sunny',{data:[0,false]},'data',true,'[0,false]'],['weather','sunny',{data:{a:1}},'data',true,'{&quot;a&quot;:1}'],['weather','sunny',{data:null},'data',true,'—'],['weather','sunny',{data:circular},'data',true,'—'],['weather','sunny',{data:broken},'data',true,'—'],
    ['sensor','4',{unit_of_measurement:'kW'},'',false,'4']
  ]) {
    const id=domain+'.subtitle';card.setConfig({...config,subtitle_mode:'entity',subtitle_entity:id,subtitle_attribute:attribute,subtitle_unit:unit});card.hass={states:{[id]:{state:value,attributes:attrs}}};
    assert.equal(card.shadowRoot.innerHTML.match(/<p class="sub">(.*?)<\/p>/s)?.[1],expected,JSON.stringify([domain,attribute,unit]));
  }
  card.setConfig({...config,subtitle_mode:'entity',subtitle_entity:'sensor.missing'});assert.match(card.shadowRoot.innerHTML,/<p class="sub">—<\/p>/);
  card.setConfig({...config,subtitle_mode:'entity',subtitle_entity:''});assert.doesNotMatch(card.shadowRoot.innerHTML,/<p class="sub">/);
  card.setConfig({...config,subtitle_mode:'entity',subtitle_entity:'weather.long',subtitle_attribute:'data'});card.hass={states:{'weather.long':{state:'sunny',attributes:{data:{long:'x'.repeat(1000)}}}}};
  assert.ok(card.shadowRoot.innerHTML.match(/<p class="sub">(.*?)<\/p>/s)[1].replaceAll('&quot;','"').length<=256);
});

test('subtitle picker ignores bubbled changes and stale events, persists clears without rerender', async () => {
  const {Editor}=setup(),el=new Editor();el.setConfig({...config,subtitle_mode:'entity',subtitle_entity:'sensor.t'});el.hass=groupHass();await flush();
  const picker={tagName:'HA-ENTITY-PICKER',dataset:{config:'subtitle_entity'},value:'sensor.t'};
  el.shadowRoot.querySelector=selector=>selector==='ha-entity-picker[data-config="subtitle_entity"]'?picker:null;
  const html=el.shadowRoot.innerHTML;
  el.handleChange({type:'change',target:picker,detail:{value:'switch.relay'}});assert.equal(el.config.subtitle_entity,'sensor.t');
  el.handleChange({type:'value-changed',target:picker,detail:{value:'switch.relay'}});assert.equal(el.events.at(-1).detail.config.subtitle_entity,'switch.relay');assert.equal(el.shadowRoot.innerHTML,html);
  el.handleChange({type:'value-changed',target:{...picker},detail:{value:'sensor.stale'}});assert.equal(el.config.subtitle_entity,'switch.relay');
  el.handleChange({type:'value-changed',target:picker,detail:{value:''}});assert.equal(el.events.at(-1).detail.config.subtitle_entity,'');
  assert.equal(el.config.name,'House');assert.equal(el.config.items[0].fan_entity,'fan.a');
});

const targetSwitch='switch.uss_p130_f5_relay0';
test('exact user YAML unknown feedback accepts explicit manual without optimistic blades', async () => {
  const {Card}=setup(), el=new Card(), writes=[];
  const entry_id='01M4TJESXTB1DRBYG80VTF3SNG',device_id='ee34fec4b5b45cc882181801bbd4e71a';
  el.setConfig({type:'custom:uninus-greenhouse-fan-card',entry_id,layout:'2',theme:'dark',items:[{device_id,fan_entity:targetSwitch}]});
  const view={...snapshot(),entry_id,devices:[{device_id,name:'P130',fan_entity:targetSwitch}],bindings:{[targetSwitch]:{temperature_entity:'sensor.sensor_8d_s0_batt',humidity_entity:'sensor.sensor_8d_s1_air4_vms_t_214'}},runtime:{}};
  el.hass={states:{[targetSwitch]:{state:'unknown'},'sensor.sensor_8d_s0_batt':{state:'27.7',attributes:{device_class:'temperature',unit_of_measurement:'°C'}},'sensor.sensor_8d_s1_air4_vms_t_214':{state:'58.2',attributes:{device_class:'humidity',unit_of_measurement:'%'}}},callWS:async msg=>{if(msg.type.endsWith('/groups'))return [{entry_id,loaded:true}];if(msg.type.endsWith('/manual')){writes.push(msg);view.runtime[targetSwitch]={mode:msg.mode};}return view;}};await flush();
  for(const mode of ['on','off','auto']){assert.equal(el.canManual(targetSwitch,mode),true);await el.manual(targetSwitch,mode);const html=el.renderFan(el.config.items[0]);assert.match(html,/狀態未知.*明確手動.*自動.*回報/);assert.doesNotMatch(html,/已開啟|已關閉|fan-item running/);assert.match(html,/27\.7/);assert.match(html,/58\.2/);}
  assert.deepEqual(writes.map(x=>[x.entry_id,x.fan_entity,x.mode]),['on','off','auto'].map(mode=>[entry_id,targetSwitch,mode]));
});
test('exact configured P130 output manual gating is independent of sensor health', async () => {
  const {Card}=setup();
  for(const output of ['on','off','unknown'])for(const sensors of ['absent','healthy','unavailable']) {
    const el=new Card(),writes=[];
    el.setConfig({...config,items:[{device_id:'p130',fan_entity:'fan.stale'}]});
    const view={...snapshot(),devices:[{device_id:'p130',name:'P130',fan_entity:targetSwitch}],bindings:sensors==='absent'?{}:{[targetSwitch]:{temperature_entity:'sensor.t',humidity_entity:'sensor.h'}},runtime:{}};
    el.hass={states:{...states,[targetSwitch]:{state:output},...(sensors==='unavailable'?{'sensor.t':{state:'unavailable'},'sensor.h':{state:'unavailable'}}:{})},callWS:async msg=>{if(msg.type.endsWith('/groups'))return groups;if(msg.type.endsWith('/manual'))writes.push(msg);return view}};await flush();
    for(const mode of ['on','off','auto']) {assert.equal(el.canManual(targetSwitch,mode),true);await el.manual(targetSwitch,mode)}
    assert.deepEqual(writes.map(x=>[x.entry_id,x.fan_entity,x.mode]),['on','off','auto'].map(mode=>['group-1',targetSwitch,mode]));
    assert.doesNotMatch(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  }
});
test('disabled configured output diagnostics distinguish absent and reported unavailable/invalid', async () => {
  const {Card}=setup();
  for(const value of [null,'unavailable','invalid']) {
    const el=new Card();el.setConfig({...config,items:[{device_id:'p130',fan_entity:'fan.stale'}]});
    el.hass={...groupHass(groups,()=>({...snapshot(),devices:[{device_id:'p130',fan_entity:targetSwitch}]})),states:value?{[targetSwitch]:{state:value}}:{}};await flush();
    const html=el.renderFan(el.config.items[0]);
    assert.match(html,/switch\.uss_p130_f5_relay0/);assert.doesNotMatch(html,/fan\.stale/);
    assert.match(html,value?new RegExp('回報狀態：'+value):/實體不存在/);
    assert.match(html,/href="\/config\/integrations"/);assert.match(html,/data-mode="on" disabled/);
  }
});
test('deleted stable identity diagnostics never reuse stale YAML output or its on state', async () => {
  const {Card}=setup();const el=new Card();el.setConfig({...config,items:[{device_id:'deleted-stable',fan_entity:'fan.a'}]});
  el.hass=groupHass(groups,()=>({...snapshot(),devices:[]}));await flush();
  const html=el.renderFan(el.config.items[0]);assert.match(html,/已儲存裝置已刪除|已儲存裝置不存在/);assert.match(html,/deleted-stable/);assert.match(html,/編輯卡片/);assert.match(html,/href="\/config\/integrations"/);assert.doesNotMatch(html,/已開啟|data-fan="fan.a"/);
});
const flush = () => new Promise(resolve => setTimeout(resolve,0));

test('card registers, requests authoritative snapshot and renders global above fan grid', async () => {
  const {Card} = setup();
  assert.equal(typeof Card.getConfigElement,'function');
  assert.equal(Card.getStubConfig().layout,'auto');
  const calls=[]; const card=new Card(); card.setConfig(config);
  card.hass={states,callWS:async msg=>{calls.push(msg);return msg.type.endsWith('/groups')?groups:snapshot();}};
  await flush();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1])),{type:'uninus_greenhouse_fan/get',entry_id:'group-1'});
  const html=card.shadowRoot.innerHTML;
  assert.ok(html.indexOf('class="global"')<html.indexOf('class="fans"'));
  assert.match(html,/32\.5/); assert.match(html,/73/);
  assert.match(html,/repeat\(auto-fit,minmax\(min\(100%,310px\),1fr\)\)/);
  assert.doesNotMatch(html,/demo-fixture|width control/i);
});

test('unbound and unavailable sensors remain safe and never infer another source', async () => {
  const {Card}=setup(); const card=new Card();card.setConfig({...config,items:[...config.items,{fan_entity:'fan.b',name:'Rear'}]});
  card.hass={states:{...states,'sensor.t':{state:'unavailable',attributes:{}}},callWS:async msg=>msg.type.endsWith('/groups')?groups:snapshot()};
  await flush();
  assert.match(card.shadowRoot.innerHTML,/未綁定/);assert.match(card.shadowRoot.innerHTML,/—/);
  assert.doesNotMatch(card.shadowRoot.innerHTML,/sensor\.fan_b/);
});

test('manual command sends exact mode and awaits backend snapshot without optimistic toggle', async () => {
  const {Card}=setup();let resolveManual; const calls=[];const card=new Card();card.setConfig(config);
  card.hass={states,callWS:msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return Promise.resolve(groups);return msg.type.endsWith('/manual')?new Promise(r=>resolveManual=r):Promise.resolve(snapshot());}};
  await flush(); const pending=card.manual('fan.a','off');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2])),{type:'uninus_greenhouse_fan/manual',entry_id:'group-1',fan_entity:'fan.a',mode:'off'});
  assert.match(card.shadowRoot.innerHTML,/已開啟/);
  resolveManual(snapshot());await pending;
});

test('unbound manual fan and relay controls dispatch and display durable hold/resume', async () => {
  const {Card}=setup();
  for(const fan of ['fan.b','switch.relay']) {
    const el=new Card();const writes=[];
    el.setConfig({...config,items:[{fan_entity:fan}]});
    el.hass=groupHass(groups,msg=>{
      const result={...snapshot(),bindings:{},runtime:{}};
      if(msg.type.endsWith('/manual')){writes.push(msg);result.runtime[fan]={mode:msg.mode,reason:msg.mode==='auto'?'unbound':'manual'}};
      return result;
    });await flush();
    assert.doesNotMatch(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
    assert.match(el.shadowRoot.innerHTML,/僅手動控制/);
    await el.manual(fan,'on');assert.equal(writes.length,1);
    assert.equal(writes[0].fan_entity,fan);assert.equal(writes[0].mode,'on');
    assert.match(el.shadowRoot.innerHTML,/class="resume"/);
    await el.manual(fan,'auto');assert.equal(writes.length,2);
    assert.match(el.shadowRoot.innerHTML,/自動未啟用/);
    assert.doesNotMatch(el.shadowRoot.innerHTML,/class="resume"/);
  }
});

test('manual gate and rendered controls share domain availability and fresh scope checks', async () => {
  const {Card}=setup();const el=new Card();let writes=0;
  el.setConfig({...config,items:[{fan_entity:'fan.b'},{fan_entity:'sensor.t'}]});
  el.hass=groupHass(groups,msg=>{if(msg.type.endsWith('/manual'))writes++;return {...snapshot(),bindings:{}}});await flush();
  await el.manual('fan.a','on');await el.manual('sensor.t','on');await el.manual('fan.b','bad');assert.equal(writes,0);
  assert.match(el.renderFan(el.config.items[1]),/data-mode="on" disabled/);
  for(const value of ['unavailable','invalid']) {
    el.hass={...el.hass,states:{...states,'fan.b':{state:value}}};
    await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  }
  el.hass={...el.hass,states};el.snapshot.entry_id='wrong-group';
  await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  el.snapshot.entry_id='group-1';el.loading=true;
  await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  assert.equal(writes,0);
});

test('editor selects stable devices and display names without sensor copies', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const calls=[];
  el.hass=groupHass(groups,msg=>{calls.push(msg);return snapshot()});await flush();
  el.setItemField(0,'device_id','switch.relay');el.setItemField(0,'name','Updated');
  assert.equal(el.events.at(-1).detail.config.items[0].device_id,'switch.relay');
  assert.equal(el.events.at(-1).detail.config.items[0].name,'Updated');
  assert.equal(el.config.items[0].temperature_entity,undefined);
  assert.equal(calls.filter(x=>x.type.endsWith('/bind')).length,0);
});

test('switch relay appears in fallback editor picker', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);el.hass=groupHass();await flush();
  assert.match(el.shadowRoot.innerHTML,/switch\.relay/);el.setItemField(0,'device_id','switch.relay');
  assert.equal(el.events.at(-1).detail.config.items[0].fan_entity,'switch.relay');
});

test('invalid selection is rejected and display removal makes no backend writes', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const writes=[];
  el.hass=groupHass(groups,msg=>{if(!msg.type.endsWith('/get'))writes.push(msg);return snapshot()});await flush();
  el.setItemField(0,'device_id','unowned');assert.equal(el.config.items[0].fan_entity,'fan.a');
  el.removeItem(0);assert.equal(el.config.items.length,0);assert.equal(writes.length,0);
});

const groups = [{entry_id:'group-1',name:'North greenhouse',loaded:true}];
const groupHass = (rows=groups, extra=()=>snapshot()) => ({states,callWS:async msg=>msg.type.endsWith('/groups')?rows:extra(msg)});
test('YAML and editor resolve a unique loaded group without typing its ID', async () => {
  const {Card,Editor}=setup();
  for (const Class of [Card,Editor]) {
    const el=new Class();el.setConfig({...config,entry_id:''});el.hass=groupHass();await flush();
    assert.equal(el.snapshot?.revision,2);
    assert.equal(el.resolvedId,'group-1');
    assert.doesNotMatch(el.shadowRoot.innerHTML,/Integration entry_id|input data-config="entry_id"/);
    if(Class===Card)assert.doesNotMatch(el.shadowRoot.innerHTML,/select data-group/);
    else assert.match(el.shadowRoot.innerHTML,/select data-group/);
    if(Class===Editor)assert.equal(el.events.at(-1).detail.config.entry_id,'group-1');
  }
});

const multi=[...groups,{entry_id:'group-2',name:'South greenhouse',loaded:true}];
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
test('selection restores group-scoped display names and ignores old snapshot completion', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const pending=deferred();let paused=false;
  el.hass=groupHass(multi,msg=>paused && msg.entry_id==='group-1'?pending.promise:{...snapshot(),entry_id:msg.entry_id});await flush();
  paused=true;const read=el.load();await flush();el.selectGroup('group-2');await flush();
  pending.resolve(snapshot(99));await read;assert.equal(el.snapshot.entry_id,'group-2');assert.equal(el.snapshot.revision,2);
});
test('manual completion after scope change cannot refresh or clear the new operation', async () => {
  const {Card}=setup();const el=new Card();el.setConfig(config);const pending=deferred();const calls=[];
  el.hass=groupHass(multi,msg=>{calls.push(msg);return msg.type.endsWith('/manual')?pending.promise:snapshot()});await flush();
  const action=el.manual('fan.a','off');el.setConfig({...config,entry_id:'group-2'});await flush();const before=calls.length;
  pending.reject(Error('old action failed'));await action;
  assert.equal(el.error,'');assert.equal(calls.length,before);assert.equal(el.resolvedId,'group-2');
});
test('explicit missing or unloaded saved groups cannot dispatch manual writes', async () => {
  const {Card}=setup();
  for(const rows of [groups,[{...groups[0],entry_id:'gone',loaded:false},...groups]]) {
    const calls=[];const el=new Card();el.setConfig({...config,entry_id:'gone'});
    el.hass=groupHass(rows,msg=>{calls.push(msg);return snapshot()});await flush();
    await el.manual('fan.a','on');assert.equal(calls.length,0);assert.equal(el.resolvedId,'');
    assert.equal(el.config.entry_id,'gone');assert.match(el.shadowRoot.innerHTML,/不存在|尚未載入/);
  }
});

test('typing a new draft during pending snapshot must retain new input', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const pending=deferred();el.hass=groupHass();await flush();
  el.hass=groupHass(groups,()=>pending.promise);const read=el.load();await flush();
  el.setItemField(0,'name','New input');pending.resolve(snapshot(7));await read;
  assert.equal(el.config.items[0].name,'New input');assert.equal(el.snapshot.revision,7);
});
test('discovery distinguishes multi, zero, unloaded and query failure for card and editor', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor])for(const rows of [multi,[],[{...groups[0],loaded:false}]]) {
    const calls=[];const el=new Class();el.setConfig({...config,entry_id:''});el.hass=groupHass(rows,msg=>{calls.push(msg);return snapshot()});await flush();
    assert.equal(el.snapshot,null);assert.equal(calls.length,0);
    if(Class===Editor)assert.match(el.shadowRoot.innerHTML,rows.length?/select data-group/:/href="\/config\/integrations"/);
    else {assert.doesNotMatch(el.shadowRoot.innerHTML,/select data-group/);assert.match(el.shadowRoot.innerHTML,/編輯卡片|設定/);if(rows===multi)assert.match(el.shadowRoot.innerHTML,/多個控制群組/);if(rows.length===1)assert.match(el.shadowRoot.innerHTML,/尚未載入/)}
    if(rows===multi){if(Class===Editor)el.selectGroup('group-2');else el.setConfig({...config,entry_id:'group-2'});await flush();assert.equal(el.resolvedId,'group-2')}
  }
  for(const Class of [Card,Editor]) {
    const el=new Class();el.setConfig({...config,entry_id:''});el.hass={states,callWS:async()=>{throw Error('network failure')}};await flush();
    assert.match(el.shadowRoot.innerHTML,/network failure/);assert.doesNotMatch(el.shadowRoot.innerHTML,/尚無控制群組/);
  }
});
test('latest snapshot request wins and disconnect invalidates discovery, snapshot and mutation', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor]) {
    const el=new Class();el.setConfig(config);const old=deferred();let reads=0;
    el.hass=groupHass(groups,()=>++reads===1?old.promise:snapshot(7));await flush();
    await el.load();old.resolve(snapshot(99));await flush();assert.equal(el.snapshot.revision,7);
    const discovery=deferred();el.hass={states,callWS:()=>discovery.promise};const loading=el.load();el.disconnectedCallback();
    discovery.resolve(groups);await loading;assert.equal(el.snapshot,null);assert.equal(el.loading,false);
    const html=el.shadowRoot.innerHTML;await el.load();assert.equal(el.shadowRoot.innerHTML,html);
  }
});

test('dashboard config replacement cancels display draft without backend writes', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);let writes=0;
  el.hass=groupHass(groups,msg=>{if(!msg.type.endsWith('/get'))writes++;return snapshot()});await flush();
  el.setItemField(0,'name','Dashboard draft');await el.load();assert.equal(el.config.items[0].name,'Dashboard draft');
  el.setConfig(config);assert.equal(el.config.items[0].name,'Front');assert.equal(writes,0);
  assert.doesNotMatch(el.shadowRoot.innerHTML,/data-action="discard"/);
});

test('unique loaded choice ignores unloaded alternatives without replacing explicit choices', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor]) {
    const el=new Class();el.setConfig({...config,entry_id:''});el.hass=groupHass([groups[0],{...multi[1],loaded:false}]);await flush();
    assert.equal(el.resolvedId,'group-1');assert.equal(el.snapshot.revision,2);
  }
});
test('disconnect invalidates late snapshot and manual completion without rendering or dispatching', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor])for(const reject of [false,true]) {
    const el=new Class();el.setConfig(config);const late=deferred();const calls=[];el.hass=groupHass();await flush();
    el.hass=groupHass(groups,msg=>{calls.push(msg);return late.promise});
    const action=Class===Card?el.manual('fan.a','off'):el.load();await flush();const html=el.shadowRoot.innerHTML;
    el.disconnectedCallback();const count=calls.length;reject?late.reject(Error('stale failure')):late.resolve(snapshot(99));await action;
    assert.equal(el.snapshot,null);assert.equal(el.error,'');assert.equal(el.shadowRoot.innerHTML,html);assert.equal(calls.length,count);
  }
});

test('automatic re-resolution never sends a command using the previous group snapshot', async () => {
  const {Card}=setup();const el=new Card();el.setConfig({...config,entry_id:''});el.hass=groupHass();await flush();
  const next=deferred(),writes=[];
  el.hass=groupHass([multi[1]],msg=>{if(msg.type.endsWith('/manual')){writes.push(msg);return snapshot()}return next.promise});
  const read=el.load();await flush();assert.equal(el.resolvedId,'group-2');
  await el.manual('fan.a','on');assert.equal(writes.length,0);assert.equal(el.snapshot,null);
  next.resolve({...snapshot(),entry_id:'group-2'});await read;
});

test('switching groups preserves distinct display names for duplicate displayed fans', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig({...config,items:[config.items[0],{...config.items[0],name:'Second view'}]});
  el.hass=groupHass(multi,msg=>({...snapshot(),entry_id:msg.entry_id}));await flush();
  el.setItemField(0,'name','First');el.setItemField(1,'name','Second');el.selectGroup('group-2');await flush();el.selectGroup('group-1');await flush();
  assert.equal(el.config.items[0].name,'First');assert.equal(el.config.items[1].name,'Second');
});
