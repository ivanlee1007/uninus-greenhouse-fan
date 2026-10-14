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
const states = {
  'fan.a':{state:'on',attributes:{friendly_name:'Fan A'}},
  'fan.b':{state:'off',attributes:{}},
  'switch.relay':{state:'off',attributes:{friendly_name:'Fan relay'}},
  'sensor.t':{state:'32.5',attributes:{unit_of_measurement:'°C',device_class:'temperature'}},
  'sensor.h':{state:'73',attributes:{unit_of_measurement:'%',device_class:'humidity'}},
};
const snapshot = (revision=2) => ({entry_id:'group-1',revision,policy:{temperature_on:30,temperature_off:25,humidity_on:80,humidity_off:60,duration_seconds:120},bindings:{'fan.a':{temperature_entity:'sensor.t',humidity_entity:'sensor.h'}},runtime:{'fan.a':{mode:'auto',pending:null,reason:'Ready'}}});
const config = {type:'custom:uninus-greenhouse-fan-card',entry_id:'group-1',name:'House',items:[{fan_entity:'fan.a',name:'Front'}],layout:'auto',theme:'dark'};
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
  for(const value of ['unknown','unavailable','invalid']) {
    el.hass={...el.hass,states:{...states,'fan.b':{state:value}}};
    await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  }
  el.hass={...el.hass,states};el.snapshot.entry_id='wrong-group';
  await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  el.snapshot.entry_id='group-1';el.loading=true;
  await el.manual('fan.b','on');assert.match(el.renderFan(el.config.items[0]),/data-mode="on" disabled/);
  assert.equal(writes,0);
});

test('editor applies binding at observed revision; Lovelace config has no sensor copies', async () => {
  const {Editor}=setup(); const editor=new Editor();editor.setConfig(config);
  const calls=[];editor.hass={states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return groups;return msg.type.endsWith('/bind')?snapshot(3):snapshot(2);}};
  await flush();
  editor.setItemField(0,'temperature_entity','sensor.t');
  editor.setItemField(0,'humidity_entity','sensor.h');
  await editor.applyBinding(0);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2])),{type:'uninus_greenhouse_fan/bind',entry_id:'group-1',expected_revision:2,fan_entity:'fan.a',temperature_entity:'sensor.t',humidity_entity:'sensor.h'});
  assert.equal(editor.snapshot.revision,3);
  assert.equal(editor.config.items[0].temperature_entity,undefined);
  editor.setItemField(0,'name','Updated');
  assert.equal(editor.events.at(-1).detail.config.items[0].name,'Updated');
});

test('switch relay appears in fallback editor picker', async () => {
  const {Editor}=setup();const editor=new Editor();editor.setConfig(config);
  editor.hass={states,callWS:async msg=>msg.type.endsWith('/groups')?groups:snapshot()};await flush();
  assert.match(editor.shadowRoot.innerHTML,/switch\.relay/);
  editor.setItemField(0,'fan_entity','switch.relay');
  assert.equal(editor.events.at(-1).detail.config.items[0].fan_entity,'switch.relay');
});

test('failed bind preserves draft and revision; removing item does not unbind', async () => {
  const {Editor}=setup(); const editor=new Editor();editor.setConfig(config);
  const calls=[];editor.hass={states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/groups'))return groups;if(msg.type.endsWith('/bind'))throw Error('Revision conflict');return snapshot();}};
  await flush();editor.setItemField(0,'temperature_entity','sensor.t');editor.setItemField(0,'humidity_entity','sensor.h');
  await editor.applyBinding(0);
  assert.equal(editor.drafts[0].temperature_entity,'sensor.t');
  assert.match(editor.shadowRoot.innerHTML,/Revision conflict/);
  assert.equal(editor.snapshot.revision,2);
  editor.removeItem(0);
  assert.equal(calls.filter(x=>x.type.endsWith('/bind')).length,1);
  assert.equal(editor.config.items.length,0);
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
    if(Class===Editor)assert.equal(el.events.at(-1).detail.config.entry_id,'group-1');
  }
});

const multi=[...groups,{entry_id:'group-2',name:'South greenhouse',loaded:true}];
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
test('selection restores group-scoped drafts and ignores old bind completion', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const pending=deferred();
  el.hass=groupHass(multi,msg=>msg.type.endsWith('/bind')?pending.promise:snapshot());await flush();
  el.setItemField(0,'temperature_entity','sensor.h');
  const bind=el.applyBinding(0);el.selectGroup('group-2');await flush();
  assert.equal(el.drafts[0].temperature_entity,undefined);
  pending.resolve(snapshot(99));await bind;
  assert.equal(el.snapshot.revision,2);assert.equal(el.status[0],undefined);
  el.selectGroup('group-1');await flush();
  assert.equal(el.drafts[0].temperature_entity,'sensor.h');
});
test('manual completion after scope change cannot refresh or clear the new operation', async () => {
  const {Card}=setup();const el=new Card();el.setConfig(config);const pending=deferred();const calls=[];
  el.hass=groupHass(multi,msg=>{calls.push(msg);return msg.type.endsWith('/manual')?pending.promise:snapshot()});await flush();
  const action=el.manual('fan.a','off');el.selectGroup('group-2');await flush();const before=calls.length;
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

test('typing a new draft during pending bind must retain new input', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);const pending=deferred();
  el.hass=groupHass(groups,msg=>msg.type.endsWith('/bind')?pending.promise:snapshot());await flush();
  el.setItemField(0,'temperature_entity','sensor.t');const operation=el.applyBinding(0);
  el.setItemField(0,'temperature_entity','sensor.h');pending.resolve(snapshot(3));await operation;
  assert.equal(el.drafts[0].temperature_entity,'sensor.h');assert.equal(el.drafts[0].revision,2);
});
test('discovery distinguishes multi, zero, unloaded and query failure for card and editor', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor])for(const rows of [multi,[],[{...groups[0],loaded:false}]]) {
    const calls=[];const el=new Class();el.setConfig({...config,entry_id:''});el.hass=groupHass(rows,msg=>{calls.push(msg);return snapshot()});await flush();
    assert.equal(el.snapshot,null);assert.equal(calls.length,0);
    assert.match(el.shadowRoot.innerHTML,rows.length?/select data-group/:/href="\/config\/integrations"/);
    if(rows===multi){el.selectGroup('group-2');await flush();assert.equal(el.resolvedId,'group-2')}
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

test('explicit discard reconciles a retained dirty revision without a write', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig(config);let revision=2;let writes=0;
  el.hass=groupHass(groups,msg=>{if(msg.type.endsWith('/bind'))writes++;return snapshot(revision)});await flush();
  el.setItemField(0,'temperature_entity','sensor.h');revision=8;await el.load();
  assert.equal(el.drafts[0].revision,2);
  el.discardDraft(0);assert.equal(el.drafts[0].revision,undefined);
  el.setItemField(0,'temperature_entity','sensor.t');assert.equal(el.drafts[0].revision,8);
  assert.equal(writes,0);
});

test('unique loaded choice ignores unloaded alternatives without replacing explicit choices', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor]) {
    const el=new Class();el.setConfig({...config,entry_id:''});el.hass=groupHass([groups[0],{...multi[1],loaded:false}]);await flush();
    assert.equal(el.resolvedId,'group-1');assert.equal(el.snapshot.revision,2);
  }
});
test('disconnect invalidates late bind and manual completion without rendering or dispatching', async () => {
  const {Card,Editor}=setup();
  for(const Class of [Card,Editor])for(const reject of [false,true]) {
    const el=new Class();el.setConfig(config);const late=deferred();const calls=[];
    el.hass=groupHass(groups,msg=>{calls.push(msg);return msg.type.endsWith('/get')?snapshot():late.promise});await flush();
    if(Class===Editor)el.setItemField(0,'temperature_entity','sensor.t');
    const action=Class===Card?el.manual('fan.a','off'):el.applyBinding(0);const html=el.shadowRoot.innerHTML;
    el.disconnectedCallback();const count=calls.length;
    reject?late.reject(Error('stale failure')):late.resolve(snapshot(99));await action;
    assert.equal(el.snapshot,null);assert.equal(el.error,'');assert.equal(el.shadowRoot.innerHTML,html);assert.equal(calls.length,count);
    if(Class===Editor)assert.equal(el.drafts[0].temperature_entity,'sensor.t');
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

test('switching groups preserves distinct drafts for duplicate displayed fans', async () => {
  const {Editor}=setup();const el=new Editor();el.setConfig({...config,items:[config.items[0],{...config.items[0],name:'Second view'}]});el.hass=groupHass(multi);await flush();
  el.setItemField(0,'temperature_entity','sensor.t');el.setItemField(1,'temperature_entity','sensor.h');
  el.selectGroup('group-2');await flush();el.selectGroup('group-1');await flush();
  assert.equal(el.drafts[0].temperature_entity,'sensor.t');assert.equal(el.drafts[1].temperature_entity,'sensor.h');
});
