/* UNiNUS Greenhouse Fan 0.4.0 — Integration-owned devices; display-only editor. */
(() => {
  'use strict';
  const PREFIX = 'uninus_greenhouse_fan/';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validId = (value, domain) => typeof value === 'string' && value.startsWith(`${domain}.`) && value.length > domain.length + 1;
  const validDevice = value => typeof value === 'string' && /^(fan|switch)\.[a-z0-9_]+$/.test(value) && !value.includes('\n');
  const item = value => ({...value,fan_entity:value.fan_entity || '',name:value.name || ''});
  const clean = value => ({...value,type:'custom:uninus-greenhouse-fan-card',entry_id:value.entry_id || '',name:value.name || '',subtitle_mode:value.subtitle_mode==='entity'?'entity':'text',subtitle_entity:typeof value.subtitle_entity==='string'?value.subtitle_entity:'',subtitle_attribute:typeof value.subtitle_attribute==='string'?value.subtitle_attribute:'',subtitle_unit:value.subtitle_unit!==false,subtitle_text:typeof value.subtitle_text==='string'?value.subtitle_text:'各區獨立感測 · 同群組共用門檻',layout:['1','2'].includes(String(value.layout))?String(value.layout):'auto',theme:value.theme === 'light'?'light':'dark',items:Array.isArray(value.items)?value.items.map(item):[]});
  const notify = element => element.dispatchEvent(new CustomEvent('config-changed',{bubbles:true,composed:true,detail:{config:clean(element.config)}}));
  const state = (hass,id) => hass?.states?.[id];
  const subtitle = (config,hass) => {
    if(config.subtitle_mode!=='entity')return config.subtitle_text;
    if(!config.subtitle_entity)return '';
    const entity=state(hass,config.subtitle_entity),attribute=config.subtitle_attribute;
    if(!entity)return '—';
    try {
      const value=attribute?entity.attributes?.[attribute]:entity.state;
      if(value===null || value===undefined || value==='unknown' || value==='unavailable' || value==='' || (typeof value==='number' && !Number.isFinite(value)))return '—';
      if(!['string','number','boolean','object'].includes(typeof value))return '—';
      let content=typeof value==='object'?JSON.stringify(value):String(value);
      if(typeof content!=='string')return '—';
      const unit=entity.attributes?.unit_of_measurement;
      if(!attribute && config.subtitle_unit && ['string','number','boolean'].includes(typeof value) && typeof unit==='string' && unit)content+=' '+unit;
      return content.length>256?content.slice(0,255)+'…':content;
    }catch{return '—'}
  };
  const subtitleMarkup = (config,hass) => {const text=subtitle(config,hass);return text?`<p class="sub">${escape(text)}</p>`:''};
  const reading = (entity,kind) => {
    if(!entity || !['string','number'].includes(typeof entity.state) || !['unknown','unavailable'].every(x=>entity.state!==x) || String(entity.state).trim()==='')return NaN;
    const unit=kind==='temperature'?'°C':'%',type=entity.attributes?.device_class;
    if(entity.attributes?.unit_of_measurement!==unit || (type && type!==kind))return NaN;
    return Number.isFinite(Number(entity.state))?Number(entity.state):NaN;
  };
  const number = (entity,kind) => {const value=reading(entity,kind);return Number.isFinite(value)?value.toFixed(1):'—'};
  const errorText = error => String(error?.message || error || 'Request failed');
  const thresholdKeys=['temperature_on','temperature_off','humidity_on','humidity_off'];
  const thresholdValues=p=>Object.fromEntries(thresholdKeys.map(k=>[k,p?.[k]]));
  const thresholdValidation=p=>thresholdKeys.some(k=>typeof p?.[k]!=='number'||!Number.isFinite(p[k]))?'門檻必須是有效數字；請取消並重新讀取。':p.temperature_off>p.temperature_on||p.humidity_off>p.humidity_on?'停止下限不可高於啟動上限，請調整後再儲存。':p.temperature_off < -20 || p.temperature_on>80 || p.humidity_off<0 || p.humidity_on>100?'門檻超出有效範圍（溫度 −20～80 °C、濕度 0～100 %），請檢查。':'';
  const styles = `<style>
    :host{display:block;min-width:0;--bg:#10171b;--surface:#1c282e;--inner:#142027;--text:#eef3f2;--muted:#b8c8c5;--border:#35444b;--accent:#f4cf5a;--good:#8cdbb3;--danger:#ffada5;color:var(--text);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    :host([data-theme="light"]){--bg:#edf2ef;--surface:#fff;--inner:#e6eee9;--text:#21312e;--muted:#4f605b;--border:#c6d3cb;--accent:#155f55;--good:#16633d;--danger:#a83220}
    *{box-sizing:border-box}button,input,select{font:inherit;color:var(--text);background:var(--inner);border:1px solid var(--border);border-radius:8px}button{min-height:44px;padding:7px 11px;cursor:pointer;font-weight:650}button:disabled{opacity:.45;cursor:not-allowed}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,ha-entity-picker:focus-visible{outline:2px solid var(--accent);outline-offset:2px}input,select{width:100%;min-height:44px;padding:8px 10px}h2,h3,p{margin:0}small{color:var(--muted)}
    .card{container-type:inline-size;min-width:0;background:radial-gradient(circle at 8% -8%,#617d8120,transparent 38%),var(--bg);border:1px solid var(--border);border-radius:22px;padding:16px;box-shadow:0 14px 35px #0003}.header>div{min-width:0}.sub{overflow-wrap:anywhere}.header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:12px}.brand{font-size:10px;letter-spacing:.18em;color:var(--accent);font-weight:800;margin-bottom:5px}.header h2{font-size:23px}.sub{font-size:12px;color:var(--muted);margin-top:4px}.summary{color:var(--accent);font-size:12px;white-space:nowrap;border:1px solid var(--border);border-radius:20px;padding:7px 10px}
    .workspace{display:flex;flex-direction:column;gap:8px;min-width:0}.global{width:100%;min-width:0;border:1px solid var(--border);border-radius:12px;background:var(--surface)}.global summary{display:flex;align-items:center;flex-wrap:nowrap;gap:8px;min-height:48px;padding:4px 10px;cursor:pointer}.limit-pair{display:flex;align-items:baseline;gap:9px;flex:1 1 135px;min-width:0}.limit-pair span{color:var(--muted)}.limit-pair b{font-size:15px;white-space:nowrap}.global-body{border-top:1px solid var(--border);padding:12px 14px;display:grid;grid-template-columns:1fr 2fr;gap:8px 16px}.global-body p{font-size:11px}.global-body strong{color:var(--accent)}
    .mode-switch{display:flex;align-items:center;justify-content:flex-end;gap:6px;min-width:72px;min-height:44px;padding:4px 0 4px 6px;font-size:11px;flex:0 0 auto;margin-left:auto;border:0;border-radius:0;background:transparent;box-shadow:none}.limits{display:flex;flex-wrap:wrap;gap:4px 16px;flex:1 1 0;min-width:0}.mode-switch[aria-busy="true"] .switch-track{opacity:.6}.switch-track{width:30px;height:18px;border-radius:12px;background:var(--border);position:relative}.switch-track:after{content:"";position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:50%;background:var(--text)}.mode-switch[aria-checked="true"] .switch-track{background:var(--accent)}.mode-switch[aria-checked="true"] .switch-track:after{left:15px;background:var(--bg)}
    .fans{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,310px),1fr));gap:8px;width:100%;min-width:0}.layout-1 .fans{grid-template-columns:1fr}.layout-2 .fans{grid-template-columns:repeat(2,minmax(0,1fr))}
    .fan-item{display:flex;flex-direction:column;min-width:0;border:1px solid var(--border);border-radius:13px;padding:10px;background:var(--surface)}.device-title{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:26px;margin-bottom:7px}.device-title h3{font-size:15px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.badge{font-size:11px;color:var(--good);white-space:nowrap}.off .badge{color:var(--muted)}.error .badge,.unavailable{color:var(--danger)}.device-hero{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:100px}.scene{width:96px;height:96px;flex:0 0 auto;display:grid;place-items:center}.fan-machine{position:relative;width:90px;height:90px;border:7px solid #4d686d;border-radius:15px;background:radial-gradient(circle,#334851 0%,#182a31 68%);box-shadow:inset 0 0 0 3px #809496,0 5px 12px #0006}.fan-wheel{position:absolute;inset:9px;border:3px solid #806668;border-radius:50%;overflow:hidden}.rotor{position:absolute;inset:4px;animation:spin 1.2s linear infinite}.rotor svg{width:100%;height:100%;fill:#8a9499}.running .rotor svg{fill:#dc5b56}.hub{position:absolute;left:50%;top:50%;width:19px;height:19px;transform:translate(-50%,-50%);border:2px solid #abb5ba;border-radius:50%;background:radial-gradient(circle at 30% 25%,#cbd3d7,#667077 80%)}.running .hub{border-color:#f19b8b;background:radial-gradient(circle at 30% 25%,#ffc2ae,#aa393d 80%)}.off .rotor{animation-play-state:paused}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.rotor{animation:none}}
    .live-status{margin-left:auto;text-align:right;min-width:0;display:grid;justify-items:end;gap:9px}.live-line{width:100%;text-align:right}.live-line span,.live-line strong{display:block}.live-line span{color:var(--muted);font-size:11px}.live-line strong{font-size:21px}.live-line.threshold-high strong,.live-line.threshold-high strong small{color:var(--danger)}.live-line.threshold-high strong{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}.device-details{min-height:48px;margin:6px 0 6px}.mode-row{font-size:11px}.reason{color:var(--muted);font-size:11px;margin-top:4px;min-height:2em}.controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:auto}.controls button.resume{grid-column:1/-1}.controls button.selected{border-color:var(--accent);color:var(--accent)}.card-note{margin-top:10px;font-size:11px;color:var(--muted)}.status{color:var(--danger);margin:8px 0}
    .editor{background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:16px}.editor h2{font-size:17px;margin-bottom:12px}.editor p{color:var(--muted);margin:8px 0}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.field{min-width:0}.field.wide{grid-column:1/-1}.field label{display:block;color:var(--muted);font-size:12px;margin-bottom:4px}.field ha-entity-picker{display:block;min-width:0}.slot{padding:12px;border:1px solid var(--border);border-radius:10px;background:var(--surface);margin:12px 0}.slot-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}.slot-actions{display:flex;gap:5px}.slot-actions button{min-width:40px}.feedback{color:var(--good)!important}.feedback.failure{color:var(--danger)!important}.notice{border:1px solid var(--border);border-radius:8px;padding:9px;margin:12px 0}.editor-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}
    @container(max-width:630px){.layout-2 .fan-item{padding:8px}.layout-2 .device-title{flex-wrap:wrap;gap:3px}.layout-2 .device-title h3{width:100%;font-size:13px}.layout-2 .device-hero{flex-direction:column;gap:4px}.layout-2 .live-status{margin:0;width:100%;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;justify-items:stretch}.layout-2 .live-line{text-align:center}.layout-2 .live-line strong{font-size:16px;white-space:nowrap}.layout-2 .live-line span{font-size:10px}.layout-2 .controls{gap:4px}.layout-2 .controls button{padding:6px 2px;font-size:11px;min-width:0;min-height:44px}.layout-2 .reason{overflow-wrap:anywhere}.layout-2 .mode-row{overflow-wrap:anywhere}}@container(max-width:370px){.card{padding:13px}.header h2{font-size:17px}.global summary{gap:6px}.limit-pair{flex-basis:100%;justify-content:space-between}.limit-pair b{font-size:13px}.device-hero{gap:6px}.scene{width:80px;height:80px}.fan-machine{transform:scale(.82)}.live-line strong{font-size:17px}}@media(max-width:450px){.fields{grid-template-columns:1fr}.global-body{grid-template-columns:1fr}}
    .threshold-demo{grid-column:1/-1;min-width:0}.threshold-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.threshold-group{border:1px solid var(--border);border-radius:10px;padding:10px;background:var(--inner)}.threshold-group h3{font-size:13px;margin:0 0 8px}.slider-row{display:grid;grid-template-columns:64px minmax(0,1fr) 70px;align-items:center;gap:8px;margin:7px 0}.slider-row label{font-size:12px;color:var(--muted)}.slider-row input[type=range]{padding:0;min-height:30px;accent-color:var(--accent);width:100%;border:0;background:transparent;cursor:pointer}.slider-row output{font-size:13px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}.help{font-size:11px;color:var(--muted);margin-top:6px}.threshold-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:10px;flex-wrap:wrap}.threshold-actions .notice-text{font-size:11px;color:var(--muted);margin-right:auto}.threshold-actions button{min-height:44px;font-size:12px;padding:6px 12px}.threshold-actions button.save{background:var(--accent);color:var(--bg);border-color:var(--accent)}.validation{font-size:12px;color:var(--danger);margin:5px 0}@container(max-width:520px){.threshold-grid{grid-template-columns:1fr}.slider-row{grid-template-columns:64px minmax(0,1fr) 65px}}
  </style>`;
  const machine = `<div class="scene" aria-hidden="true"><div class="fan-machine"><div class="fan-wheel"><div class="rotor"><svg viewBox="0 0 100 100"><g><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(90 50 50)"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(180 50 50)"/><path d="M48 48 C15 50 9 23 28 13 C43 6 58 21 48 48Z" transform="rotate(270 50 50)"/></g></svg></div><div class="hub"></div></div></div></div>`;

  class GroupClient extends HTMLElement {
    static get buildVersion(){return '0.4.0'}
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
      this.shadowRoot.addEventListener('toggle',e=>{if(e.target===this.shadowRoot.querySelector('details.global'))this.expanded=e.target.open},true);
      this.thresholdDraft=null;this.policyError='';this.policyNotice='';
      this.shadowRoot.addEventListener('input',e=>{
        const key=e.target.dataset?.threshold;
        if(key && e.target===this.shadowRoot.querySelector(`[data-threshold="${key}"]`))this.editThreshold(key,Number(e.target.value));
      });

      this.shadowRoot.addEventListener('click',e=>{
        if(e.target.closest?.('[data-save]')){this.saveThresholds();return}
        if(e.target.closest?.('[data-cancel]')){this.cancelThresholds();return}
        const toggle=e.target.closest?.('button[data-control-mode]');
        if(toggle){e.preventDefault();e.stopPropagation();this.setControlMode(toggle.dataset.controlMode);return}
        const button=e.target.closest?.('button[data-mode]');if(button)this.manual(button.dataset.fan,button.dataset.mode);
      });
    }
    groupMarkup() {
      const settings='<a href="/config/integrations">設定 → 裝置與服務 → UNiNUS Greenhouse Fan</a>';
      if(this.error)return `<p class="status" role="alert">${escape(this.error)}；請編輯卡片選擇群組，或檢查 ${settings}</p>`;
      if(this.groups===null)return '<p role="status">正在讀取控制群組…</p>';
      if(!this.groups.length)return `<p class="status" role="alert">尚無控制群組；請在 ${settings} 新增整合，再編輯卡片。</p>`;
      if(!this.resolvedId)return `<p class="status" role="alert">${this.groups.some(row=>row.loaded)?'有多個控制群組；請編輯卡片選擇控制群組':'控制群組尚未載入；請檢查整合設定'}。${settings}</p>`;
      return '';
    }
    invalidate(){super.invalidate();this.thresholdDraft=null;this.policyError='';this.policyNotice=''}
    canEditThresholds(){return !this.detached && !this.operation && !!this.resolvedId && this.snapshot?.entry_id===this.resolvedId && this.hass?.user?.is_admin===true && Number.isInteger(this.snapshot?.policy_revision)}
    thresholdStale(){return !!this.thresholdDraft && (this.thresholdDraft.id!==this.resolvedId || this.thresholdDraft.revision!==this.snapshot?.policy_revision)}
    editThreshold(key,value){
      if(!thresholdKeys.includes(key)||!this.canEditThresholds())return;
      if(!this.thresholdDraft)this.thresholdDraft={id:this.resolvedId,revision:this.snapshot.policy_revision,values:thresholdValues(this.snapshot.policy)};
      this.thresholdDraft.values[key]=value;this.policyError='';this.policyNotice='';this.updateThresholdControls();
    }
    cancelThresholds(){
      if(this.operation)return;
      this.thresholdDraft=null;this.policyError='';this.policyNotice='已取消修改；重新讀取已儲存門檻。';this.render();this.load();
    }
    async saveThresholds(){
      if(!this.thresholdDraft || !this.canEditThresholds() || this.loading)return;
      const validation=thresholdValidation(this.thresholdDraft.values);
      if(validation || this.thresholdStale()){this.policyError=validation || '門檻已由其他介面修改；請取消草稿並重新讀取後調整。';this.updateThresholdControls();return}
      const draft=this.thresholdDraft,operation={epoch:this.epoch,id:this.resolvedId,kind:'policy'};
      this.operation=operation;this.request++;this.loading=false;this.policyError='';this.render();
      const current=()=>!this.detached && this.operation===operation && this.epoch===operation.epoch && this.resolvedId===operation.id && this.thresholdDraft===draft;
      try{
        const result=await this.hass.callWS({type:PREFIX+'save_thresholds',entry_id:operation.id,expected_policy_revision:draft.revision,thresholds:{...draft.values}});
        if(!current())return;
        const savedPolicy=this.snapshot.policy,changed=thresholdKeys.some(k=>savedPolicy[k]!==draft.values[k]);
        if(result?.entry_id!==operation.id || result.policy_revision!==draft.revision+(changed?1:0) || result.policy?.duration_seconds!==savedPolicy.duration_seconds || thresholdValidation(result.policy) || thresholdKeys.some(k=>result.policy[k]!==draft.values[k]))throw Error('儲存結果未能核對；請取消並重新讀取門檻。');
        this.snapshot=result;this.thresholdDraft=null;this.policyNotice='已儲存門檻；重新開始條件計時，不會立即開關風扇。';
      }catch(error){if(current())this.policyError=error?.code==='conflict'?'門檻已由其他介面修改；請取消草稿並重新讀取後調整。':'門檻儲存失敗；草稿保留。'+errorText(error)}
      finally{if(!this.detached && this.operation===operation && this.epoch===operation.epoch){this.operation=null;this.render()}}
    }
    thresholdMarkup(){
      const p=this.thresholdDraft?.values||this.snapshot?.policy||{},valid=!thresholdValidation(p);
      const metrics=[['temperature','溫度','°C',0,50],['humidity','濕度','%',0,100]];
      return `<section class="threshold-demo variant-a"><div class="threshold-grid">${metrics.map(([k,name,unit,min,max])=>{
        // Extend the demo range for valid native policies; never clamp them.
        if(k==='temperature' && valid){min=Math.min(min,p.temperature_off);max=Math.max(max,p.temperature_on)}
        return `<section class="threshold-group"><h3>${name}控制門檻</h3>${['on','off'].map(side=>{const key=k+'_'+side;return `<div class="slider-row"><label for="${key}">${side==='on'?'啟動上限':'停止下限'}</label><input id="${key}" aria-label="${name}${side==='on'?'啟動上限':'停止下限'}" type="range" min="${min}" max="${max}" step="0.1" value="${Number.isFinite(p[key])?p[key]:min}" data-threshold="${key}" ${this.canEditThresholds() && valid?'':'disabled'}><output for="${key}">${Number.isFinite(p[key])?p[key].toFixed(1):'—'} ${unit}</output></div>`}).join('')}<p class="help">${name}：超過上限可啟動；降至下限才允許停止。<span data-range-help="${k}"></span></p></section>`}).join('')}</div><p class="validation" hidden></p><div class="threshold-actions"><span class="notice-text" role="status"></span><button data-cancel disabled>取消修改</button><button class="save" data-save disabled>儲存門檻</button></div><p class="help" data-duration-help>啟動：溫度或濕度超過上限，持續 ${escape(this.snapshot?.policy?.duration_seconds ?? '—')} 秒。停止：兩者皆降至下限，持續相同秒數。</p></section>`;
    }
    updateThresholdControls(){
      const root=this.shadowRoot,p=this.thresholdDraft?.values||this.snapshot?.policy||{};
      const validation=!this.snapshot?.policy?'':this.thresholdStale()?'門檻已由其他介面修改；請取消草稿並重新讀取後調整。':this.policyError || thresholdValidation(p);
      for(const key of thresholdKeys){const input=root.querySelector(`[data-threshold="${key}"]`);if(!input)continue;
        const kind=key.startsWith('temperature')?'temperature':'humidity',nativeValid=!thresholdValidation(this.snapshot?.policy);
        input.min=kind==='temperature' && nativeValid?Math.min(0,this.snapshot.policy.temperature_off):0;
        input.max=kind==='temperature' && nativeValid?Math.max(50,this.snapshot.policy.temperature_on):100;
        if(Number.isFinite(p[key]) && Number(input.value)!==p[key])input.value=p[key];
        input.disabled=!this.canEditThresholds() || !nativeValid;
        input.nextElementSibling.textContent=Number.isFinite(p[key])?p[key].toFixed(1)+(kind==='temperature'?' °C':' %'):'—';
      }
      const range=root.querySelector('[data-range-help="temperature"]');
      if(range){const saved=this.snapshot?.policy,valid=!thresholdValidation(saved);range.textContent=valid && (saved.temperature_off<0 || saved.temperature_on>50)?` 既有門檻範圍：${String(Math.min(0,saved.temperature_off)).replace('-','−')}～${Math.max(50,saved.temperature_on)} °C。`:''}
      const message=root.querySelector('.validation');if(message){message.hidden=!validation;message.textContent=validation;if(validation)message.setAttribute('role','alert');else message.removeAttribute('role')}
      const save=root.querySelector('[data-save]');if(save)save.disabled=!this.thresholdDraft || !this.canEditThresholds() || this.loading || !!validation;
      const cancel=root.querySelector('[data-cancel]');if(cancel)cancel.disabled=!this.thresholdDraft || !!this.operation;
      const notice=root.querySelector('.notice-text');if(notice)notice.textContent=this.operation?.kind==='policy'?'正在儲存；控制仍使用原門檻。':this.thresholdDraft?'尚未儲存 · 自動控制仍使用已儲存門檻':this.policyNotice || (this.hass?.user?.is_admin===true?'調整後一次儲存；不會立即開關風扇。':'只有管理員可以儲存門檻。');
      const help=root.querySelector('[data-duration-help]');if(help)help.textContent=`啟動：溫度或濕度超過上限，持續 ${this.snapshot?.policy?.duration_seconds ?? '—'} 秒。停止：兩者皆降至下限，持續相同秒數。`;
    }
    static getConfigElement() {return document.createElement('uninus-greenhouse-fan-card-editor')}
    static getStubConfig() {return {type:'custom:uninus-greenhouse-fan-card',entry_id:'',name:'Greenhouse fans',items:[],layout:'auto',theme:'dark'}}
    setConfig(config) {const next=clean(config);if(this.config && JSON.stringify(this.config)===JSON.stringify(next))return;this.invalidate();this.config=next;this.load();this.render()}
    connectedCallback(){this.detached=false;if(!this._poll){this._poll=setInterval(()=>this.load(),5000)}if(this.config && this.hass)this.load()}
    disconnectedCallback(){clearInterval(this._poll);this._poll=null;super.disconnectedCallback()}
    set hass(value) {this._hass=value;if(this.config && !this.snapshot && !this.loading)this.load();this.render()}
    get hass() {return this._hass}
    resolveDevice(slot) {return this.snapshot?.devices?.find(row=>slot.device_id?row.device_id===slot.device_id:row.fan_entity===slot.fan_entity)}
    output(slot) {return this.resolveDevice(slot)?.fan_entity || (slot.device_id?'':slot.fan_entity)}
    canManual(fan,mode) {
      return !(mode==='auto' && this.snapshot?.control_mode==='manual') && !this.detached && !this.operation && !this.loading && !!this.resolvedId && this.snapshot?.entry_id===this.resolvedId && !this.error && ['on','off','auto'].includes(mode) && validDevice(fan) && this.snapshot?.devices?.some(x=>x.fan_entity===fan) && this.config?.items.some(x=>this.output(x)===fan) && ['on','off','unknown'].includes(state(this.hass,fan)?.state);
    }
    canSetControlMode() {
      return !this.detached && !this.operation && !this.loading && !!this.resolvedId && this.snapshot?.entry_id===this.resolvedId && !this.error && this.hass?.user?.is_admin!==false;
    }
    async setControlMode(control_mode) {
      if(!['auto','manual'].includes(control_mode) || !this.canSetControlMode())return;
      const operation={epoch:this.epoch,id:this.resolvedId};this.operation=operation;this.request++;this.loading=false;
      const current=()=>!this.detached && this.operation===operation && this.epoch===operation.epoch && this.resolvedId===operation.id;
      this.error='';this.render();
      try {
        const result=await this.hass.callWS({type:PREFIX+'set_control_mode',entry_id:operation.id,control_mode});
        if(current())this.snapshot=result;
      } catch(error){if(current())this.error=errorText(error)}
      finally {if(current()){this.operation=null;this.render()}}
    }
    async manual(fan,mode) {
      if(!this.canManual(fan,mode))return;
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
      const device=this.resolveDevice(slot),id=this.output(slot),fan=state(this.hass,id),binding=this.snapshot?.bindings?.[id],runtime=this.snapshot?.runtime?.[id];
      const unavailable=!validDevice(id) || !['on','off'].includes(fan?.state),bound=validId(binding?.temperature_entity,'sensor')&&validId(binding?.humidity_entity,'sensor');
      const temp=bound?number(state(this.hass,binding.temperature_entity),'temperature'):'—',hum=bound?number(state(this.hass,binding.humidity_entity),'humidity'):'—';
      const bad=unavailable||!bound||temp==='—'||hum==='—';const on=!unavailable && fan.state==='on';
      const label=slot.name||device?.name||fan?.attributes?.friendly_name||id||(slot.device_id?'未設定裝置':slot.fan_entity)||'未設定裝置';
      const mode=this.snapshot?.control_mode==='manual'?'manual':runtime?.mode || (this.snapshot?.entry_id===this.resolvedId?'auto':'—'),modeLabel={auto:bound?'自動':'自動未啟用',manual:'全域手動',on:'手動開啟',off:'手動關閉'}[mode]||'—';
      const diagnostic=!this.snapshot?'群組資料尚未就緒；請先處理控制群組提示（禁止控制）':!device?(slot.device_id?`已儲存裝置不存在（${slot.device_id}）；可能已刪除或不屬於此群組，請編輯卡片重新選擇已設定裝置（禁止控制）`:`此群組未設定此裝置（${id||'未選擇輸出'}）；請至整合設定新增，再編輯卡片選擇（禁止控制）`):unavailable && fan?.state!=='unknown'?(!validDevice(id)?`輸出設定無效（${id||'未設定'}）；請在整合設定修正`:!fan?`輸出實體不存在：${id}；請檢查實體是否停用、移除或已改名，並在整合設定修正`:`輸出 ${id} 回報狀態：${fan.state}；請檢查來源整合連線與實體狀態`):'';
      const reason=diagnostic||(mode==='manual'?'全域手動：維持輸出；請先切換全域自動再恢復自動':fan?.state==='unknown'?`輸出 ${id} 狀態未知，可明確手動下達開／關指令；自動暫停直到收到有效回報`:!bound?'未綁定感測來源 · 僅手動控制；恢復自動只解除保持，自動未啟用':bad?'感測讀值不可用 · 仍可手動控制':({unbound:'未綁定感測來源',sensor_unavailable:'感測讀值不可用',fan_unavailable:'裝置不可用',manual:'手動保持',resumed:'已恢復自動',waiting_duration:'條件計時中',threshold_not_met:'維持目前狀態',action_requested:'已下達自動控制',action_failed:'控制指令失敗'}[runtime?.reason]||runtime?.reason||'—'));
      const disabled=this.canManual(id,'on')?'':'disabled';
      const high=kind=>mode==='auto' && !!device && bound && Number.isFinite(this.snapshot?.policy?.[kind+'_on']) && reading(state(this.hass,binding[kind+'_entity']),kind)>this.snapshot.policy[kind+'_on'];
      return `<article class="fan-item ${on?'running':'off'} ${bad?'error':''}"><header class="device-title"><h3 title="${escape(label)}">${escape(label)}</h3><span class="badge">● ${unavailable?'未知':on?'已開啟':'已關閉'}</span></header><div class="device-hero">${machine}<div class="live-status"><div class="live-line ${temp==='—'?'unavailable':high('temperature')?'threshold-high':''}" title="${escape(binding?.temperature_entity||'')}"><span>目前溫度</span><strong>${temp}<small> °C</small></strong></div><div class="live-line ${hum==='—'?'unavailable':high('humidity')?'threshold-high':''}" title="${escape(binding?.humidity_entity||'')}"><span>目前濕度</span><strong>${hum}<small> %</small></strong></div></div></div><div class="device-details"><div class="mode-row">控制模式 <b>${escape(modeLabel)}</b> · ${escape(runtime?.pending ? '條件計時中' : '開關回報')}</div><p class="reason" title="${escape(reason)}">${escape(reason)}${diagnostic?' · <a href="/config/integrations">設定 → 裝置與服務</a>':''}</p></div><div class="controls"><button data-fan="${escape(id)}" data-mode="on" ${disabled} class="${mode==='on'?'selected':''}">手動開啟</button><button data-fan="${escape(id)}" data-mode="off" ${disabled} class="${mode==='off'?'selected':''}">手動關閉</button>${this.snapshot?.control_mode!=='manual' && ['on','off'].includes(mode)?`<button class="resume" data-fan="${escape(id)}" data-mode="auto" ${this.canManual(id,'auto')?'':'disabled'} title="${mode==='manual'?'請先切換全域自動':'解除個別手動保持'}">恢復自動</button>`:''}</div></article>`;
    }
    render() {
      if(!this.config)return;
      this.setAttribute?.('data-theme',this.config.theme);
      const retained=this.shadowRoot.querySelector('.threshold-demo');
      // Keep threshold DOM continuously mounted across snapshot renders.
      const retain=retained && retained.dataset.scope===this.resolvedId && !!this.snapshot;
      const p=this.snapshot?.policy || {}, items=this.config.items;
      const tOn=p.temperature_on ?? '—',tOff=p.temperature_off ?? '—',hOn=p.humidity_on ?? '—',hOff=p.humidity_off ?? '—';
      const count=items.filter(x=>state(this.hass,this.output(x))?.state==='on').length;
      const html=`${styles}<section class="card layout-${this.config.layout}"><header class="header"><div><div class="brand">UNiNUS / GREENHOUSE</div><h2>${escape(this.config.name||'Greenhouse fans')}</h2>${subtitleMarkup(this.config,this.hass)}</div><span class="summary">● ${count} / ${items.length} 台開啟</span></header><div class="group-status">${this.groupMarkup()}</div><div class="workspace"><details class="global" ${this.expanded?'open':''}><summary aria-label="全域溫濕度上下限，展開或收折"><span class="limits"><span class="limit-pair"><span>溫度 ↑／↓</span><b>${escape(tOn)} / ${escape(tOff)} °C</b></span><span class="limit-pair"><span>濕度 ↑／↓</span><b>${escape(hOn)} / ${escape(hOff)} %</b></span></span><button class="mode-switch" data-control-mode="${this.snapshot?.control_mode==='manual'?'auto':'manual'}" role="switch" aria-label="全域自動控制" aria-busy="${!!this.operation}" aria-checked="${!!this.snapshot && this.snapshot.control_mode!=='manual'}" ${this.canSetControlMode()?'':'disabled'} title="套用此群組所有裝置（含未顯示裝置）；切換不會立即開關輸出"><span>自動</span><span class="switch-track" aria-hidden="true"></span></button></summary><div class="global-body">${this.thresholdMarkup()}</div></details><div class="fans">${items.map(x=>this.renderFan(x)).join('')}</div></div><p class="card-note">動畫依開關回報 · 手動保持至恢復自動</p></section>`;
      if(retain){
        // Patch live regions only: focused/dragged range nodes never detach.
        const next=document.createElement('template');next.innerHTML=html;
        for(const selector of ['.header','.group-status','.global summary','.fans','.card-note']){
          this.shadowRoot.querySelector(selector).replaceWith(next.content.querySelector(selector));
        }
      }else this.shadowRoot.innerHTML=html;
      const controls=this.shadowRoot.querySelector('.threshold-demo');if(controls)controls.dataset.scope=this.resolvedId;
      this.updateThresholdControls();
    }
    getCardSize(){return Math.max(3,(this.config?.items?.length||0)*3)}
  }

  class FanEditor extends GroupClient {
    constructor() {
      super();this.attachShadow({mode:'open'});this.snapshot=null;
      this.shadowRoot.addEventListener('value-changed',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('input',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('change',e=>this.handleChange(e));
      this.shadowRoot.addEventListener('click',e=>this.handleClick(e));
    }
    setConfig(value) {
      const next=clean(value);if(this.config && JSON.stringify(this.config)===JSON.stringify(next))return;
      this.invalidate();this.config=next;this.load();this.render(true);
    }
    selectGroup(id) {
      if(!this.groups?.some(row=>row.entry_id===id && row.loaded) || this.config.entry_id===id)return;
      super.selectGroup(id);notify(this);this.render(true);
    }
    set hass(value){this._hass=value;if(this.config && !this.snapshot && !this.loading)this.load();const picker=this.shadowRoot.querySelector('ha-entity-picker[data-config="subtitle_entity"]');if(picker)picker.hass=value;this.updateSubtitlePreview();if(!this.shadowRoot.activeElement || this.shadowRoot.activeElement.tagName==='BODY')this.render()}
    get hass(){return this._hass}
    emit(){notify(this);this.render(true)}
    setItemField(index,field,value) {
      const slot=this.config.items[index];if(!slot)return;
      if(field==='name'){slot.name=value;notify(this);return}
      if(field==='device_id' || field==='fan_entity'){
        const row=this.snapshot?.devices?.find(row=>field==='device_id'?row.device_id===value:row.fan_entity===value);
        if(!row)return;
        slot.device_id=row.device_id;slot.fan_entity=row.fan_entity;this.emit();
      }
    }
    removeItem(index){if(index<0||index>=this.config.items.length)return;this.config.items.splice(index,1);this.emit()}
    moveItem(index,offset){const next=index+offset;if(next<0||next>=this.config.items.length)return;[this.config.items[index],this.config.items[next]]=[this.config.items[next],this.config.items[index]];this.emit()}
    handleChange(e){
      const target=e.target;if(!target?.dataset || this.detached)return;
      if(target.tagName==='HA-ENTITY-PICKER'){
        if(e.type!=='value-changed' || target!==this.shadowRoot.querySelector('ha-entity-picker[data-config="subtitle_entity"]') || !Object.prototype.hasOwnProperty.call(e.detail||{},'value'))return;
        this.config.subtitle_entity=typeof e.detail.value==='string'?e.detail.value:'';notify(this);this.updateSubtitlePreview();return;
      }
      if(target.dataset.group){this.selectGroup(target.value);return}
      if(target.dataset.config){const field=target.dataset.config;if(!['name','theme','layout','subtitle_mode','subtitle_text','subtitle_attribute','subtitle_unit'].includes(field))return;this.config[field]=field==='subtitle_unit'?target.checked:target.value;if(['name','subtitle_text','subtitle_attribute','subtitle_unit'].includes(field)){notify(this);this.updateSubtitlePreview()}else this.emit();return}
      if(target.dataset.field)this.setItemField(Number(target.dataset.index),target.dataset.field,target.value);
    }
    handleClick(e){const button=e.target.closest?.('button[data-action]');if(!button)return;const index=Number(button.dataset.index);switch(button.dataset.action){case 'add':this.config.items.push({fan_entity:'',name:''});this.emit();break;case 'remove':this.removeItem(index);break;case 'up':this.moveItem(index,-1);break;case 'down':this.moveItem(index,1);break;case 'refresh':this.load();break}}
    renderItem(slot,index){
      const devices=this.snapshot?.entry_id===this.resolvedId?this.snapshot.devices||[]:[];
      const selected=devices.find(row=>slot.device_id?row.device_id===slot.device_id:row.fan_entity===slot.fan_entity);
      return `<section class="slot"><div class="slot-head"><strong>顯示項目 ${index+1}</strong><div class="slot-actions"><button data-action="up" data-index="${index}" ${index===0?'disabled':''} aria-label="上移">↑</button><button data-action="down" data-index="${index}" ${index===this.config.items.length-1?'disabled':''} aria-label="下移">↓</button><button data-action="remove" data-index="${index}" aria-label="移除顯示項目">×</button></div></div><div class="fields"><div class="field"><label>已設定裝置</label><select data-index="${index}" data-field="device_id" ${!this.snapshot||this.loading?'disabled':''}><option value="" ${!selected?'selected':''}>${slot.fan_entity||slot.device_id?'原裝置未在此群組設定；請至整合新增':'選擇已設定裝置'}</option>${devices.map(row=>`<option value="${escape(row.device_id)}" ${row===selected?'selected':''}>${escape(row.name)} · ${escape(row.fan_entity)}${!state(this.hass,row.fan_entity)||['unknown','unavailable'].includes(state(this.hass,row.fan_entity).state)?'（離線）':''}</option>`).join('')}</select></div><div class="field"><label>顯示名稱</label><input data-index="${index}" data-field="name" value="${escape(slot.name)}"></div></div></section>`;
    }
    updateSubtitlePreview(){
      const preview=this.shadowRoot.querySelector('[data-subtitle-preview]');
      if(preview){const text=subtitle(this.config,this.hass);preview.textContent=text;preview.hidden=!text}
    }
    subtitleFields(){
      return `<div class="field wide"><label>副標題來源</label><select data-config="subtitle_mode" aria-label="副標題來源"><option value="text" ${this.config.subtitle_mode==='text'?'selected':''}>文字</option><option value="entity" ${this.config.subtitle_mode==='entity'?'selected':''}>實體</option></select></div>${this.config.subtitle_mode==='text'?`<div class="field wide"><label>副標題文字（留空隱藏）</label><input aria-label="副標題文字" data-config="subtitle_text" value="${escape(this.config.subtitle_text)}"></div>`:`<div class="field wide"><label>副標題實體（留空隱藏）</label><ha-entity-picker data-config="subtitle_entity"></ha-entity-picker></div><div class="field"><label>屬性（選填；留空顯示狀態）</label><input aria-label="副標題屬性" data-config="subtitle_attribute" value="${escape(this.config.subtitle_attribute)}"></div><div class="field"><label><input type="checkbox" data-config="subtitle_unit" ${this.config.subtitle_unit?'checked':''}>顯示狀態單位</label></div>`}<div class="field wide"><label>副標題預覽</label><p class="sub" data-subtitle-preview></p><small>僅顯示單一實體狀態或屬性；不支援模板。Dashboard Save 儲存，Cancel 不會修改後端。</small></div>`;
    }
    render(force=false){
      if(!this.config)return;
      if(!force && this.shadowRoot.activeElement?.matches?.('input,ha-entity-picker')){this.updateSubtitlePreview();return}
      this.setAttribute?.('data-theme',this.config.theme);
      this.shadowRoot.innerHTML=`${styles}<section class="editor"><h2>風扇卡片設定</h2><p class="notice">裝置與感測來源：<a href="/config/integrations">設定 → 裝置與服務 → UNiNUS Greenhouse Fan → 設定</a>。此處只儲存顯示項目、順序、名稱與外觀。</p><div class="fields">${this.groupMarkup()}<div class="field wide"><label>卡片標題</label><input data-config="name" value="${escape(this.config.name)}"></div>${this.subtitleFields()}<div class="field"><label>主題</label><select data-config="theme"><option value="dark" ${this.config.theme==='dark'?'selected':''}>深夜石墨</option><option value="light" ${this.config.theme==='light'?'selected':''}>雲霧白</option></select></div><div class="field"><label>每列設備數</label><select data-config="layout"><option value="auto" ${this.config.layout==='auto'?'selected':''}>自動排列</option><option value="1" ${this.config.layout==='1'?'selected':''}>1 欄</option><option value="2" ${this.config.layout==='2'?'selected':''}>2 欄</option></select></div></div><button data-action="refresh">重新讀取裝置</button>${this.config.items.map((slot,i)=>this.renderItem(slot,i)).join('')}<div class="editor-actions"><button data-action="add">＋ 新增顯示項目</button></div><p>移除顯示項目不會刪除整合裝置，也不會控制風扇。</p></section>`;
      const picker=this.shadowRoot.querySelector('ha-entity-picker[data-config="subtitle_entity"]');
      if(picker){picker.hass=this.hass;picker.value=this.config.subtitle_entity;picker.label='副標題實體';picker.allowCustomEntity=true}
      this.updateSubtitlePreview();
    }
  }
  if(!customElements.get('uninus-greenhouse-fan-card'))customElements.define('uninus-greenhouse-fan-card',FanCard);
  if(!customElements.get('uninus-greenhouse-fan-card-editor'))customElements.define('uninus-greenhouse-fan-card-editor',FanEditor);
  if(window.customCards && !window.customCards.some(card=>card.type==='uninus-greenhouse-fan-card'))window.customCards.push({type:'uninus-greenhouse-fan-card',name:'UNiNUS Greenhouse Fan',description:'Group policy and independent fans'});
})();
