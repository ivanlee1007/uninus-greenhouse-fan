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
  card.hass={states,callWS:async msg=>{calls.push(msg);return snapshot();}};
  await flush();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])),{type:'uninus_greenhouse_fan/get',entry_id:'group-1'});
  const html=card.shadowRoot.innerHTML;
  assert.ok(html.indexOf('class="global"')<html.indexOf('class="fans"'));
  assert.match(html,/32\.5/); assert.match(html,/73/);
  assert.match(html,/repeat\(auto-fit,minmax\(min\(100%,310px\),1fr\)\)/);
  assert.doesNotMatch(html,/demo-fixture|width control/i);
});

test('unbound and unavailable sensors remain safe and never infer another source', async () => {
  const {Card}=setup(); const card=new Card();card.setConfig({...config,items:[...config.items,{fan_entity:'fan.b',name:'Rear'}]});
  card.hass={states:{...states,'sensor.t':{state:'unavailable',attributes:{}}},callWS:async()=>snapshot()};
  await flush();
  assert.match(card.shadowRoot.innerHTML,/未綁定/);assert.match(card.shadowRoot.innerHTML,/—/);
  assert.doesNotMatch(card.shadowRoot.innerHTML,/sensor\.fan_b/);
});

test('manual command sends exact mode and awaits backend snapshot without optimistic toggle', async () => {
  const {Card}=setup();let resolveManual; const calls=[];const card=new Card();card.setConfig(config);
  card.hass={states,callWS:msg=>{calls.push(msg);return msg.type.endsWith('/manual')?new Promise(r=>resolveManual=r):Promise.resolve(snapshot());}};
  await flush(); const pending=card.manual('fan.a','off');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1])),{type:'uninus_greenhouse_fan/manual',entry_id:'group-1',fan_entity:'fan.a',mode:'off'});
  assert.match(card.shadowRoot.innerHTML,/已開啟/);
  resolveManual(snapshot());await pending;
});

test('editor applies binding at observed revision; Lovelace config has no sensor copies', async () => {
  const {Editor}=setup(); const editor=new Editor();editor.setConfig(config);
  const calls=[];editor.hass={states,callWS:async msg=>{calls.push(msg);return msg.type.endsWith('/bind')?snapshot(3):snapshot(2);}};
  await flush();
  editor.setItemField(0,'temperature_entity','sensor.t');
  editor.setItemField(0,'humidity_entity','sensor.h');
  await editor.applyBinding(0);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1])),{type:'uninus_greenhouse_fan/bind',entry_id:'group-1',expected_revision:2,fan_entity:'fan.a',temperature_entity:'sensor.t',humidity_entity:'sensor.h'});
  assert.equal(editor.snapshot.revision,3);
  assert.equal(editor.config.items[0].temperature_entity,undefined);
  editor.setItemField(0,'name','Updated');
  assert.equal(editor.events.at(-1).detail.config.items[0].name,'Updated');
});

test('switch relay appears in fallback editor picker', async () => {
  const {Editor}=setup();const editor=new Editor();editor.setConfig(config);
  editor.hass={states,callWS:async()=>snapshot()};await flush();
  assert.match(editor.shadowRoot.innerHTML,/switch\.relay/);
  editor.setItemField(0,'fan_entity','switch.relay');
  assert.equal(editor.events.at(-1).detail.config.items[0].fan_entity,'switch.relay');
});

test('failed bind preserves draft and revision; removing item does not unbind', async () => {
  const {Editor}=setup(); const editor=new Editor();editor.setConfig(config);
  const calls=[];editor.hass={states,callWS:async msg=>{calls.push(msg);if(msg.type.endsWith('/bind'))throw Error('Revision conflict');return snapshot();}};
  await flush();editor.setItemField(0,'temperature_entity','sensor.t');editor.setItemField(0,'humidity_entity','sensor.h');
  await editor.applyBinding(0);
  assert.equal(editor.drafts[0].temperature_entity,'sensor.t');
  assert.match(editor.shadowRoot.innerHTML,/Revision conflict/);
  assert.equal(editor.snapshot.revision,2);
  editor.removeItem(0);
  assert.equal(calls.filter(x=>x.type.endsWith('/bind')).length,1);
  assert.equal(editor.config.items.length,0);
});
