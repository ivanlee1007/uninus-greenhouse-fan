/* UNiNUS Greenhouse Fan — Lovelace UI only. Automation and binding storage live in the integration. */
(() => {
  'use strict';
  const PREFIX = 'uninus_greenhouse_fan/';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validId = (value, domain) => typeof value === 'string' && value.startsWith(`${domain}.`) && value.length > domain.length + 1;
  const validDevice = value => validId(value,'fan') || validId(value,'switch');
  const item = value => ({...value,fan_entity:value.fan_entity || '',name:value.name || ''});
  const clean = value => ({...value,type:'custom:uninus-greenhouse-fan-card',entry_id:value.entry_id || '',name:value.name || '',layout:['1','2'].includes(String(value.layout))?String(value.layout):'auto',theme:value.theme === 'light'?'light':'dark',items:Array.isArray(value.items)?value.items.map(item):[]});
  const notify = element => element.dispatchEvent(new CustomEvent('config-changed',{bubbles:true,composed:true,detail:{config:clean(element.config)}}));
  const state = (hass,id) => hass?.states?.[id];
  const number = (entity,kind) => {
    if(!entity || !['unknown','unavailable'].every(x=>entity.state!==x) || String(entity.state).trim()==='')return '—';
    const unit=kind==='temperature'?'°C':'%',type=entity.attributes?.device_class;
    if(entity.attributes?.unit_of_measurement!==unit || (type && type!==kind))return '—';
    return Number.isFinite(Number(entity.state))?Number(entity.state).toFixed(1):'—';
  };
  const errorText = error => String(error?.message || error || 'Request failed');
  const styles = `<style>
    :host{display:block;min-width:0;--bg:#10171b;--surface:#1c282e;--inner:#142027;--text:#eef3f2;--muted:#b8c8c5;--border:#35444b;--accent:#f4cf5a;--good:#8cdbb3;--danger:#ffada5;color:var(--text);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    :host([data-theme="light"]){--bg:#edf2ef;--surface:#fff;--inner:#e6eee9;--text:#21312e;--muted:#4f605b;--border:#c6d3cb;--accent:#155f55;--good:#16633d;--danger:#a83220}
    *{box-sizing:border-box}button,input,select{font:inherit;color:var(--text);background:var(--inner);border:1px solid var(--border);border-radius:8px}button{min-height:44px;padding:7px 11px;cursor:pointer;font-weight:650}button:disabled{opacity:.45;cursor:not-allowed}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,ha-entity-picker:focus-visible{outline:2px solid var(--accent);outline-offset:2px}input,select{width:100%;min-height:44px;padding:8px 10px}h2,h3,p{margin:0}small{color:var(--muted)}
    .card{container-type:inline-size;min-width:0;background:radial-gradient(circle at 8% -8%,#617d8120,transparent 38%),var(--bg);border:1px solid var(--border);border-radius:22px;padding:20px;box-shadow:0 14px 35px #0003}.header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:18px}.brand{font-size:10px;letter-spacing:.18em;color:var(--accent);font-weight:800;margin-bottom:5px}.header h2{font-size:23px}.sub{font-size:12px;color:var(--muted);margin-top:4px}.summary{color:var(--accent);font-size:12px;white-space:nowrap;border:1px solid var(--border);border-radius:20px;padding:7px 10px}
    .workspace{display:flex;flex-direction:column;gap:12px;min-width:0}.global{width:100%;min-width:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.global summary{display:flex;align-items:center;flex-wrap:wrap;gap:12px;min-height:52px;padding:10px 14px;cursor:pointer}.limit-pair{display:flex;align-items:baseline;gap:9px;flex:1 1 160px;min-width:0}.limit-pair span{color:var(--muted)}.limit-pair b{font-size:15px;white-space:nowrap}.global-body{border-top:1px solid var(--border);padding:12px 14px;display:grid;grid-template-columns:1fr 2fr;gap:8px 16px}.global-body p{font-size:11px}.global-body strong{color:var(--accent)}
    .fans{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,310px),1fr));gap:12px;width:100%;min-width:0}.layout-1 .fans{grid-template-columns:1fr}.layout-2 .fans{grid-template-columns:repeat(2,minmax(0,1fr))}
    .fan-item{display:flex;flex-direction:column;min-width:0;border:1px solid var(--border);border-radius:13px;padding:14px;background:var(--surface)}.device-title{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:26px;margin-bottom:11px}.device-title h3{font-size:15px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.badge{font-size:11px;color:var(--good);white-space:nowrap}.off .badge{color:var(--muted)}.error .badge,.unavailable{color:var(--danger)}.device-hero{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:114px}.scene{width:108px;height:108px;flex:0 0 auto;display:grid;place-items:center}.fan-machine{position:relative;width:98px;height:98px;border:7px solid #4d686d;border-radius:15px;background:radial-gradient(circle,#334851 0%,#182a31 68%);box-shadow:inset 0 0 0 3px #809496,0 5px 12px #0006}.fan-wheel{position:absolute;inset:9px;border:3px solid #806668;border-radius:50%;overflow:hidden}.rotor{position:absolute;inset:4px;animation:spin 1.2s linear infinite}.rotor svg{width:100%;height:100%;fill:#dc5b56}.hub{position:absolute;left:50%;top:50%;width:19px;height:19px;transform:translate(-50%,-50%);border:2px solid #f19b8b;border-radius:50%;background:radial-gradient(circle at 30% 25%,#ffc2ae,#aa393d 80%)}.off .rotor,.error .rotor{animation-play-state:paused}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.rotor{animation:none}}
    .live-status{margin-left:auto;text-align:right;min-width:0;display:grid;justify-items:end;gap:9px}.live-line{width:100%;text-align:right}.live-line span,.live-line strong{display:block}.live-line span{color:var(--muted);font-size:11px}.live-line strong{font-size:21px}.device-details{min-height:60px;margin:10px 0 8px}.mode-row{font-size:11px}.reason{color:var(--muted);font-size:11px;margin-top:7px;min-height:2em}.controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:auto}.controls button.resume{grid-column:1/-1}.controls button.selected{border-color:var(--accent);color:var(--accent)}.card-note{margin-top:14px;font-size:11px;color:var(--muted)}.status{color:var(--danger);margin:8px 0}
    .editor{background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:16px}.editor h2{font-size:17px;margin-bottom:12px}.editor p{color:var(--muted);margin:8px 0}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.field{min-width:0}.field.wide{grid-column:1/-1}.field label{display:block;color:var(--muted);font-size:12px;margin-bottom:4px}.field ha-entity-picker{display:block;min-width:0}.slot{padding:12px;border:1px solid var(--border);border-radius:10px;background:var(--surface);margin:12px 0}.slot-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}.slot-actions{display:flex;gap:5px}.slot-actions button{min-width:40px}.apply{margin-top:10px}.feedback{color:var(--good)!important}.feedback.failure{color:var(--danger)!important}.notice{border:1px solid var(--border);border-radius:8px;padding:9px;margin:12px 0}.editor-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}
    @container(max-width:630px){.layout-2 .fans{grid-template-columns:1fr}}@container(max-width:370px){.card{padding:13px}.header h2{font-size:17px}.global summary{gap:6px}.limit-pair{flex-basis:100%;justify-content:space-between}.limit-pair b{font-size:13px}.device-hero{gap:6px}.scene{width:90px;height:90px}.fan-machine{transform:scale(.82)}.live-line strong{font-size:17px}}@media(max-width:450px){.fields{grid-template-columns:1fr}.global-body{grid-template-columns:1fr}}
  </style>`;
  const machine = `<div class="scene" aria-hidden="true"><div class="fan-machine"><div class="fan-wheel"><div class="rotor"><svg viewBox="0 0 100 100"><g><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(90 50 50)"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(180 50 50)"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(270 50 50)"/></g></svg></div><div class="hub"></div></div></div></div>`;

  class GroupClient extends HTMLElement {
    constructor() {
      super();this.groups=null;this.resolvedId='';this.epoch=0;this.request=0;this.loading=false;this.detached=false;this.error='';
    }
    invalidate() {this.epoch++;this.request++;this.loading=false;this.busy='';this.operation=null;this.snapshot=null;this.resolvedId='';this.error=''}
    connectedCallback(){this.detached=false;if(this.config && this.hass)this.load()}
    disconnectedCallback(){this.detached=true;this.invalidate()}
    async load() {
      if(!this.hass?.callWS || !this.config || this.detached || this.operation)return;
      const config=this.config,epoch=this.epoch,sequence=++this.request;
      const current=()=>!this.detached && epoch===this.epoch && sequence===this.request && config===this.config;
      this.loading=true;
      try {
        const rows=await this.hass.callWS({type:PREFIX+'groups'});
        if(!current())return;
        if(!Array.isArray(rows))throw Error('Invalid group discovery response');
        this.groups=rows;this.error='';
        const loaded=rows.filter(row=>row.loaded===true);
        const id=config.entry_id || (loaded.length===1?loaded[0].entry_id:'');
        const selected=rows.find(row=>row.entry_id===id);
        const previousId=this.resolvedId;this.resolvedId='';
        if(config.entry_id && !selected){this.snapshot=null;this.error='已儲存的控制群組不存在；請選擇群組或檢查整合設定';return}
        if(selected && !selected.loaded){this.snapshot=null;this.error='控制群組尚未載入；請在整合設定檢查或重新載入';return}
        if(!id){this.snapshot=null;return}
        if(previousId!==id)this.snapshot=null;
        this.resolvedId=id;this.render();
        const result=await this.hass.callWS({type:PREFIX+'get',entry_id:id});
        if(!current())return;
        this.snapshot=result;
        if(!config.entry_id && this instanceof FanEditor){config.entry_id=id;notify(this)}
      } catch(error) {
        if(current()){this.snapshot=null;this.resolvedId='';this.error='讀取控制群組失敗：'+errorText(error)}
      } finally {if(current()){this.loading=false;this.render()}}
    }
    selectGroup(id) {
      if(!this.groups?.some(row=>row.entry_id===id && row.loaded))return;
      this.invalidate();this.config={...this.config,entry_id:id};this.load();this.render();
    }
    groupMarkup() {
      if(this.error)return `<p class="status" role="alert">${escape(this.error)}</p>${this.groupSelect()}<a href="/config/integrations">設定 → 裝置與服務</a>`;
      if(this.groups===null)return '<p role="status">正在讀取控制群組…</p>';
      if(!this.groups.length)return '<p class="status">尚無控制群組。<a href="/config/integrations">設定 → 裝置與服務：新增 UNiNUS Greenhouse Fan 整合</a></p>';
      return this.groupSelect();
    }
    groupSelect() {
      if(!this.groups?.length)return '';
      const selected=this.config.entry_id || this.resolvedId;
      return `<div class="field wide"><label>控制群組</label><select data-group="true" aria-label="控制群組"><option value="" ${!selected?'selected':''}>請選擇控制群組</option>${selected && !this.groups.some(row=>row.entry_id===selected)?'<option value="'+escape(selected)+'" selected disabled>已儲存群組不存在</option>':''}${this.groups.map(row=>`<option value="${escape(row.entry_id)}" ${row.entry_id===selected?'selected':''} ${!row.loaded?'disabled':''}>${escape(row.name)}${!row.loaded?'（尚未載入）':''}</option>`).join('')}</select></div>`;
    }
  }

  class FanCard extends GroupClient {
    constructor() {
      super();this.attachShadow({mode:'open'});this.snapshot=null;this.expanded=false;this.busy='';this.error='';this.request=0;
      this.shadowRoot.addEventListener('toggle',e=>{if(e.target.matches?.('details.global'))this.expanded=e.target.open},true);
      this.shadowRoot.addEventListener('change',e=>{if(e.target.dataset?.group)this.selectGroup(e.target.value)});
      this.shadowRoot.addEventListener('click',e=>{const button=e.target.closest?.('button[data-mode]');if(button)this.manual(button.dataset.fan,button.dataset.mode)});
    }
    static getConfigElement() {return document.createElement('uninus-greenhouse-fan-card-editor')}
    static getStubConfig() {return {type:'custom:uninus-greenhouse-fan-card',entry_id:'',name:'Greenhouse fans',items:[],layout:'auto',theme:'dark'}}
    setConfig(config) {const next=clean(config);if(this.config && JSON.stringify(this.config)===JSON.stringify(next))return;this.invalidate();this.config=next;this.load();this.render()}
    connectedCallback(){this.detached=false;if(!this._poll){this._poll=setInterval(()=>this.load(),5000)}if(this.config && this.hass)this.load()}
    disconnectedCallback(){clearInterval(this._poll);this._poll=null;super.disconnectedCallback()}
    set hass(value) {this._hass=value;if(this.config && !this.snapshot && !this.loading)this.load();this.render()}
    get hass() {return this._hass}
    async manual(fan,mode) {
      if(this.operation || !this.resolvedId || !this.snapshot || this.error || !this.snapshot.bindings?.[fan] || !['on','off','auto'].includes(mode) || !validDevice(fan) || !this.config?.items.some(x=>x.fan_entity===fan) || !['on','off'].includes(state(this.hass,fan)?.state))return;
      const operation={epoch:this.epoch,id:this.resolvedId};this.operation=operation;this.request++;this.loading=false;
      const current=()=>!this.detached && this.operation===operation && this.epoch===operation.epoch && this.resolvedId===operation.id;
      this.busy=fan;this.error='';this.render();
      try {
        const result=await this.hass.callWS({type:PREFIX+'manual',entry_id:operation.id,fan_entity:fan,mode});
        if(current())this.snapshot=result;
      } catch(error){if(current())this.error=errorText(error)}
      finally {if(current()){this.operation=null;this.busy='';this.render()}}
    }
    renderFan(slot) {
      const id=slot.fan_entity,fan=state(this.hass,id),binding=this.snapshot?.bindings?.[id],runtime=this.snapshot?.runtime?.[id];
      const unavailable=!fan || ['unknown','unavailable'].includes(fan.state),bound=validId(binding?.temperature_entity,'sensor')&&validId(binding?.humidity_entity,'sensor');
      const temp=bound?number(state(this.hass,binding.temperature_entity),'temperature'):'—',hum=bound?number(state(this.hass,binding.humidity_entity),'humidity'):'—';
      const bad=unavailable||!bound||temp==='—'||hum==='—';const on=!unavailable && fan.state==='on';
      const label=slot.name||fan?.attributes?.friendly_name||id;
      const mode=runtime?.mode || '—',modeLabel={auto:'自動',on:'手動開啟',off:'手動關閉'}[mode]||'—';
      const reason=unavailable?'裝置不可用':!bound?'未綁定感測來源':bad?'感測讀值不可用':({unbound:'未綁定感測來源',sensor_unavailable:'感測讀值不可用',fan_unavailable:'裝置不可用',manual:'手動保持',resumed:'已恢復自動',waiting_duration:'條件計時中',threshold_not_met:'維持目前狀態',action_requested:'已下達自動控制',action_failed:'控制指令失敗'}[runtime?.reason]||runtime?.reason||'—');
      const disabled=unavailable||!bound||!!this.busy||!this.snapshot||!this.resolvedId||!!this.error?'disabled':'';
      return `<article class="fan-item ${on?'running':'off'} ${bad?'error':''}"><header class="device-title"><h3 title="${escape(label)}">${escape(label)}</h3><span class="badge">● ${unavailable?'未知':on?'已開啟':'已關閉'}</span></header><div class="device-hero">${machine}<div class="live-status"><div class="live-line ${temp==='—'?'unavailable':''}" title="${escape(binding?.temperature_entity||'')}"><span>目前溫度</span><strong>${temp}<small> °C</small></strong></div><div class="live-line ${hum==='—'?'unavailable':''}" title="${escape(binding?.humidity_entity||'')}"><span>目前濕度</span><strong>${hum}<small> %</small></strong></div></div></div><div class="device-details"><div class="mode-row">控制模式 <b>${escape(modeLabel)}</b> · ${escape(runtime?.pending ? '條件計時中' : '開關回報')}</div><p class="reason" title="${escape(reason)}">${escape(reason)}</p></div><div class="controls"><button data-fan="${escape(id)}" data-mode="on" ${disabled} class="${mode==='on'?'selected':''}">手動開啟</button><button data-fan="${escape(id)}" data-mode="off" ${disabled} class="${mode==='off'?'selected':''}">手動關閉</button>${mode==='on'||mode==='off'?`<button class="resume" data-fan="${escape(id)}" data-mode="auto" ${disabled}>恢復自動</button>`:''}</div></article>`;
    }
    render() {
      if(!this.config)return;
      this.setAttribute?.('data-theme',this.config.theme);
      const p=this.snapshot?.policy || {}, items=this.config.items;
      const tOn=p.temperature_on ?? '—',tOff=p.temperature_off ?? '—',hOn=p.humidity_on ?? '—',hOff=p.humidity_off ?? '—';
      const count=items.filter(x=>state(this.hass,x.fan_entity)?.state==='on').length;
      this.shadowRoot.innerHTML=`${styles}<section class="card layout-${this.config.layout}"><header class="header"><div><div class="brand">UNiNUS / GREENHOUSE</div><h2>${escape(this.config.name||'Greenhouse fans')}</h2><p class="sub">各區獨立感測 · 同群組共用門檻</p></div><span class="summary">● ${count} / ${items.length} 台開啟</span></header>${this.groupMarkup()}<div class="workspace"><details class="global" ${this.expanded?'open':''}><summary aria-label="全域溫濕度上下限，展開或收折"><span class="limit-pair"><span>溫度 ↑／↓</span><b>${escape(tOn)} / ${escape(tOff)} °C</b></span><span class="limit-pair"><span>濕度 ↑／↓</span><b>${escape(hOn)} / ${escape(hOff)} %</b></span></summary><div class="global-body"><p>條件持續 ${escape(p.duration_seconds ?? '—')} 秒 · 計時中 ${Object.values(this.snapshot?.runtime||{}).filter(r=>r.pending).length} 台</p><p><strong>開：</strong>溫度 &gt; ${escape(tOn)} °C 或濕度 &gt; ${escape(hOn)} %<br><strong>關：</strong>溫度 ≤ ${escape(tOff)} °C 且濕度 ≤ ${escape(hOff)} %</p></div></details><div class="fans">${items.map(x=>this.renderFan(x)).join('')}</div></div><p class="card-note">動畫依開關回報 · 手動保持至恢復自動</p></section>`;
    }
    getCardSize(){return Math.max(3,(this.config?.items?.length||0)*3)}
  }

  class FanEditor extends GroupClient {
    constructor() {
      super();this.attachShadow({mode:'open'});this.snapshot=null;this.drafts=[];this.status={};this.request=0;this.scopeDrafts=new Map();
      this.shadowRoot.addEventListener('input',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('change',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('value-changed',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('click',e=>this.handleClick(e));
    }
    saveDrafts() {
      const id=this.config?.entry_id || this.resolvedId;
      if(!id)return;
      const saved=new Map();
      this.config.items.forEach((slot,i)=>{if(!saved.has(slot.fan_entity))saved.set(slot.fan_entity,[]);saved.get(slot.fan_entity).push(this.drafts[i])});
      this.scopeDrafts.set(id,saved);
    }
    restoreDrafts() {
      const saved=this.scopeDrafts.get(this.config.entry_id || this.resolvedId);
      const occurrences=new Map();
      this.drafts=this.config.items.map(slot=>{const index=occurrences.get(slot.fan_entity)||0;occurrences.set(slot.fan_entity,index+1);return saved?.get(slot.fan_entity)?.[index]||{}});this.status={};
    }
    setConfig(value) {
      const next=clean(value);if(this.config && JSON.stringify(this.config)===JSON.stringify(next))return;
      this.saveDrafts();this.invalidate();this.config=next;this.restoreDrafts();this.load();this.render();
    }
    selectGroup(id) {
      if(!this.groups?.some(row=>row.entry_id===id && row.loaded) || this.config.entry_id===id)return;
      this.saveDrafts();super.selectGroup(id);this.restoreDrafts();notify(this);this.render();
    }
    cancelOperation(){this.epoch++;this.request++;this.operation=null;this.loading=false}
    set hass(value){this._hass=value;if(this.config && !this.snapshot && !this.loading)this.load();if(!this.shadowRoot.activeElement || this.shadowRoot.activeElement.tagName==='BODY')this.render()}
    get hass(){return this._hass}
    emit(){notify(this);this.render()}
    setItemField(index,field,value) {
      if(!this.config.items[index])return;
      if(field==='fan_entity') {this.cancelOperation();this.config.items[index].fan_entity=value;this.drafts[index]={};this.emit();return}
      if(field==='name'){this.config.items[index].name=value;notify(this);return}
      if(['temperature_entity','humidity_entity'].includes(field)){if(this.drafts[index].revision===undefined)this.drafts[index]={...this.snapshot?.bindings?.[this.config.items[index].fan_entity],revision:this.snapshot?.revision};this.drafts[index]={...this.drafts[index],[field]:value};this.status[index]='';this.render()}
    }
    removeItem(index){if(index<0||index>=this.config.items.length)return;this.cancelOperation();this.config.items.splice(index,1);this.drafts.splice(index,1);this.status={};this.emit()}
    moveItem(index,offset){const next=index+offset;if(next<0||next>=this.config.items.length)return;this.cancelOperation();[this.config.items[index],this.config.items[next]]=[this.config.items[next],this.config.items[index]];[this.drafts[index],this.drafts[next]]=[this.drafts[next],this.drafts[index]];this.emit()}
    discardDraft(index){if(!this.config.items[index]||this.operation)return;this.drafts[index]={};this.status[index]='草稿已捨棄；請核對目前 Integration 來源';this.render()}
    async applyBinding(index){
      const slot=this.config.items[index],draft=this.drafts[index];if(!slot||!draft||this.operation||!this.resolvedId||this.error)return;
      const base=this.snapshot?.bindings?.[slot.fan_entity]||{};
      const temperature_entity=draft.temperature_entity ?? base.temperature_entity;
      const humidity_entity=draft.humidity_entity ?? base.humidity_entity;
      if(!this.snapshot){this.status[index]='請先讀取 Integration 綁定及 revision';this.render();return}
      if(!validDevice(slot.fan_entity)||!validId(temperature_entity,'sensor')||!validId(humidity_entity,'sensor')||!state(this.hass,slot.fan_entity)||!state(this.hass,temperature_entity)||!state(this.hass,humidity_entity)) {this.status[index]='請選擇現有風扇、溫度與濕度實體';this.render();return}
      const operation={epoch:this.epoch,id:this.resolvedId};this.operation=operation;this.request++;this.loading=false;
      const current=()=>!this.detached && this.operation===operation && operation.epoch===this.epoch && operation.id===this.resolvedId && this.config.items[index]===slot && this.drafts[index]===draft;
      this.status[index]='套用中…';this.render();
      try {
        const result=await this.hass.callWS({type:PREFIX+'bind',entry_id:operation.id,expected_revision:draft.revision ?? this.snapshot.revision,fan_entity:slot.fan_entity,temperature_entity,humidity_entity});
        if(current()){this.snapshot=result;this.drafts[index]={};this.status[index]='已套用至 Integration；Lovelace Save 僅儲存顯示設定'}
      } catch(error){if(current())this.status[index]=`套用失敗：${errorText(error)}。草稿已保留；如 revision 衝突，請重新整理後核對。`}
      finally {if(this.operation===operation){this.operation=null;if(!this.detached)this.render()}}
    }
    handleChange(e){
      const target=e.target;if(!target?.dataset)return;
      if(target.dataset.group){this.selectGroup(target.value);return}
      if(target.tagName==='HA-ENTITY-PICKER' && e.type!=='value-changed')return;
      const value=e.detail?.value ?? target.value;
      if(target.dataset.config){const field=target.dataset.config;if(!['name','theme','layout'].includes(field))return;this.config[field]=value;if(e.type==='input' && field==='name')notify(this);else this.emit();return}
      if(target.dataset.field)this.setItemField(Number(target.dataset.index),target.dataset.field,value);
    }
    handleClick(e){const button=e.target.closest?.('button[data-action]');if(!button)return;const index=Number(button.dataset.index);switch(button.dataset.action){case 'add':this.config.items.push({fan_entity:'',name:''});this.drafts.push({});this.emit();break;case 'remove':this.removeItem(index);break;case 'up':this.moveItem(index,-1);break;case 'down':this.moveItem(index,1);break;case 'apply':this.applyBinding(index);break;case 'discard':this.discardDraft(index);break;case 'refresh':this.load();break}}
    selector(domain,value,index,field){
      const domains=domain==='fan'?['fan','switch']:[domain];
      const ids=Object.keys(this.hass?.states||{}).filter(id=>domains.some(d=>id.startsWith(d+'.'))).sort();
      // HA's picker supplies native search and validation. Plain select is a fallback for older HA.
      const picker=!!customElements.get('ha-entity-picker');
      if(picker)return `<ha-entity-picker data-index="${index}" data-field="${field}" data-domain="${domain}" value="${escape(value||'')}" allow-custom-entity="false"></ha-entity-picker>`;
      return `<select data-index="${index}" data-field="${field}"><option value="">選擇 ${domain} Entity</option>${[...new Set(value && !ids.includes(value)?[value,...ids]:ids)].map(id=>`<option value="${escape(id)}" ${id===value?'selected':''}>${escape(this.hass?.states?.[id]?.attributes?.friendly_name||id)} · ${escape(id)}</option>`).join('')}</select>`;
    }
    renderItem(slot,index){
      const binding=this.snapshot?.bindings?.[slot.fan_entity]||{},draft=this.drafts[index]||{};
      const temperature=draft.temperature_entity ?? binding.temperature_entity ?? '',humidity=draft.humidity_entity ?? binding.humidity_entity ?? '';
      const feedback=this.status[index]||'';
      return `<section class="slot"><div class="slot-head"><strong>顯示項目 ${index+1}</strong><div class="slot-actions"><button data-action="up" data-index="${index}" ${index===0?'disabled':''} aria-label="上移">↑</button><button data-action="down" data-index="${index}" ${index===this.config.items.length-1?'disabled':''} aria-label="下移">↓</button><button data-action="remove" data-index="${index}" aria-label="移除顯示項目">×</button></div></div><div class="fields"><div class="field"><label>風扇 Entity</label>${this.selector('fan',slot.fan_entity,index,'fan_entity')}</div><div class="field"><label>顯示名稱</label><input data-index="${index}" data-field="name" value="${escape(slot.name)}"></div><div class="field"><label>溫度 Entity</label>${this.selector('sensor',temperature,index,'temperature_entity')}</div><div class="field"><label>濕度 Entity</label>${this.selector('sensor',humidity,index,'humidity_entity')}</div></div><button class="apply" data-action="apply" data-index="${index}" ${!this.snapshot||!this.resolvedId||this.error||this.operation?'disabled':''}>套用感測來源</button>${Object.keys(draft).length?` <button data-action="discard" data-index="${index}" ${this.operation?'disabled':''}>捨棄草稿並核對來源</button>`:''}<p class="feedback ${feedback.includes('失敗')||feedback.includes('請')?'failure':''}" role="status">${escape(feedback||(!binding.temperature_entity?'未綁定 · 請選擇感測來源並套用':'來源由 Integration 管理'))}</p></section>`;
    }
    render(){
      if(!this.config)return;
      this.setAttribute?.('data-theme',this.config.theme);
      this.shadowRoot.innerHTML=`${styles}<section class="editor"><h2>風扇卡片設定</h2><p class="notice">感測來源由 Integration 管理。「套用感測來源」立即寫入後端；Lovelace Save 只儲存群組、風扇顯示項目、名稱與外觀。</p><div class="fields">${this.groupMarkup()}<div class="field wide"><label>卡片標題</label><input data-config="name" value="${escape(this.config.name)}"></div><div class="field"><label>主題</label><select data-config="theme"><option value="dark" ${this.config.theme==='dark'?'selected':''}>深夜石墨</option><option value="light" ${this.config.theme==='light'?'selected':''}>雲霧白</option></select></div><div class="field"><label>每列設備數</label><select data-config="layout"><option value="auto" ${this.config.layout==='auto'?'selected':''}>自動排列</option><option value="1" ${this.config.layout==='1'?'selected':''}>1 欄</option><option value="2" ${this.config.layout==='2'?'selected':''}>2 欄</option></select></div></div><p>Integration revision：${escape(this.snapshot?.revision ?? '—')} <button data-action="refresh">重新讀取綁定</button></p>${this.status.global?`<p class="feedback failure" role="alert">${escape(this.status.global)}</p>`:''}${this.config.items.map((slot,i)=>this.renderItem(slot,i)).join('')}<div class="editor-actions"><button data-action="add">＋ 新增顯示項目</button></div><p>移除顯示項目不會刪除 Integration 綁定，也不會控制風扇。</p></section>`;
      // Property assignment is required by HA's native picker; its value is not only an HTML attribute.
      this.shadowRoot.querySelectorAll?.('ha-entity-picker').forEach(picker=>{picker.hass=this.hass;picker.value=picker.getAttribute('value');picker.includeDomains=picker.dataset.domain==='fan'?['fan','switch']:[picker.dataset.domain]});
    }
  }
  if(!customElements.get('uninus-greenhouse-fan-card'))customElements.define('uninus-greenhouse-fan-card',FanCard);
  if(!customElements.get('uninus-greenhouse-fan-card-editor'))customElements.define('uninus-greenhouse-fan-card-editor',FanEditor);
  if(window.customCards && !window.customCards.some(card=>card.type==='uninus-greenhouse-fan-card'))window.customCards.push({type:'uninus-greenhouse-fan-card',name:'UNiNUS Greenhouse Fan',description:'Group policy and independent fans'});
})();
