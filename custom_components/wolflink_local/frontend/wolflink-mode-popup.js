function wolfValidOptionalMeasurement(state){
 const value=state?.state;
 return value!==undefined&&value!==null&&String(value).trim()!==''&&Number.isFinite(Number(value));
}
/* Local WOLF dashboard UI. Opening/closing never sends an appliance command. */
const WOLF_WRITE_LABELS = {
  sending: "Wird gesendet …", awaiting_confirmation: "Übertragen · Bestätigung ausstehend",
  awaiting_period_confirmation: "Zeitraum übertragen · Bestätigung ausstehend",
  confirmed: "Bestätigt", failed: "Nicht bestätigt", reported: "Anlagenwert",
};
const WOLF_COMPACT_LABELS = { ...WOLF_WRITE_LABELS, sending: "Sendet …",
  awaiting_confirmation: "Wartet", awaiting_period_confirmation: "Zeitraum wartet",
  reported: "", failed: "Nicht bestätigt" };
const WOLF_STAGE_CSS = `
  ha-card{--status-color:#78909c;position:relative;
    background:var(--card-background-color);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color))}
  ha-card::after{content:"";position:absolute;right:12px;top:12px;
    width:7px;height:7px;border-radius:50%;background:var(--status-color);pointer-events:none}
  ha-card[data-stage="awaiting_confirmation"],ha-card[data-stage="awaiting_period_confirmation"]{--status-color:#f9a825}
  ha-card[data-stage="confirmed"],ha-card[data-stage="reported"]{--status-color:#43a047}
  ha-card[data-stage="sending"]{--status-color:#2196f3}
  ha-card[data-stage="failed"]{--status-color:#e53935}
`;
function wolfWriteStage(state) {
  const stage = state?.attributes.write_status || "reported";
  if (stage === "failed") return stage;
  if (!state || state.state === "unavailable" ||
      (state.state === "unknown" && !state.entity_id.startsWith("button."))) return "unavailable";
  return stage in WOLF_WRITE_LABELS ? stage : "unavailable";
}
class WolfLinkModePopup extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (typeof config.entity !== "string" || !Array.isArray(config.cards)) {
      throw new Error("WolfLink popup requires a status entity and cards");
    }
    this.config = config;
    this.shadowRoot.innerHTML = `<style>${WOLF_STAGE_CSS}
      :host{display:block} ha-card{height:100%;overflow:hidden}
      button{font:inherit;border:0;background:none;color:var(--primary-text-color);
        cursor:pointer;display:flex;align-items:center;gap:12px;width:100%;
        min-height:56px;padding:10px 14px;text-align:left}
      button:focus-visible{outline:2px solid var(--primary-color);outline-offset:-3px}
      ha-icon{color:var(--state-icon-color);flex-shrink:0}
      .name{font-weight:500;font-size:14px}.state{font-size:12px;color:var(--secondary-text-color)}
      button>div{min-width:0}.name,.state{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      ha-icon{color:var(--state-icon-color)}
@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){button{min-height:44px;box-sizing:border-box;padding:4px 20px 4px 8px;gap:7px;line-height:16px}.name{font-size:12px}.value,.state{font-size:11px}ha-icon{--mdc-icon-size:20px}}    button{min-height:48px;box-sizing:border-box;padding:6px 22px 6px 10px;gap:8px}.name{font-size:var(--wolf-control-font,14px)}.state{font-size:var(--wolf-control-value-font,13px)}</style><ha-card><button type="button" aria-haspopup="dialog"><ha-icon></ha-icon>
    <div><div class="name"></div><div class="state"></div></div></button></ha-card>`;
    this.shadowRoot.querySelector(".name").textContent = config.name || "WOLF";
    this.shadowRoot.querySelector("ha-icon").icon = config.icon || "mdi:radiator";
    this.shadowRoot.querySelector("button").addEventListener("click", () => this.openPopup());
    this.updateState();
  }

  set hass(hass) {
    this._hass = hass;
    this.updateState();
    if (this._dialog) this._dialog.hass = hass;
  }

  updateState() {
    const el = this.shadowRoot.querySelector(".state");
    if (!el || !this.config) return;
    const state = this._hass?.states[this.config.entity];
    const stage = wolfWriteStage(state);
    this.shadowRoot.querySelector("ha-card").dataset.stage = stage;
    this.shadowRoot.querySelector("ha-card").title = WOLF_WRITE_LABELS[stage] || "Nicht verf�gbar";
    const value = state ? this._hass.formatEntityState(state) : "Nicht verfügbar";
    el.textContent = value + (WOLF_COMPACT_LABELS[stage] ? " · " + WOLF_COMPACT_LABELS[stage] : "");
    this.shadowRoot.querySelector("button").title = WOLF_WRITE_LABELS[stage] || "Nicht verfügbar";
  }

  openPopup() {
    if (!this._hass || this._dialog?.isConnected) return;
    const event = new CustomEvent("show-dialog", {
      bubbles: true, composed: true,
      detail: {
        dialogTag: "wolflink-mode-dialog",
        dialogImport: () => Promise.resolve(),
        dialogParams: { title: this.config.name, cards: this.config.cards,
          hass: this._hass, owner: this },
      },
    });
    this.dispatchEvent(event);
  }

  getCardSize() { return 1; }
  getGridOptions() { return { columns: 6, rows: 1, min_rows: 1 }; }
}

class WolfLinkModeDialog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) this._card.hass = hass;
  }

  async showDialog(params) {
    this._closing = false;
    this.params = params;
    this.hass = params.hass;
    params.owner._dialog = this;
    const helpers = await window.loadCardHelpers();
    const schedule = params.cards.find(card => card.type === "custom:wolflink-schedule");
    const cards = schedule ? params.cards.filter(card => card.type !== "markdown") :
      params.cards.map(card => card.type === "markdown" && card.content?.includes("Erst **Speichern**")
        ? { type: "custom:wolflink-mode-info", party: params.cards.some(item => item.type === "entities" && item.entities?.some(row => (row.wolf_role||row.entity)?.includes("partymodus_dauer"))) }
        : card);
    const infoConfig = cards.find(card => card.type === "custom:wolflink-mode-info");
    this._card = helpers.createCardElement({ type: "vertical-stack", cards: cards.filter(card => card !== infoConfig) });
    this._card.hass = this._hass;
    this.shadowRoot.innerHTML = `<style>
      ha-dialog{--mdc-dialog-min-width: min(540px, calc(100vw - 24px));
        --mdc-dialog-max-width:540px;--dialog-content-padding:12px}
      .header{position:relative;display:flex;align-items:center;gap:10px;margin-bottom:10px}
      h2{font-size:20px;margin:0;flex:1;font-weight:500}
      button{border:0;background:none;color:var(--primary-text-color);font:inherit;
        font-size:24px;cursor:pointer;width:40px;height:40px;border-radius:20px}
      button:focus-visible{outline:2px solid var(--primary-color)}
      .content{width:100%;max-width:508px;min-width:0;margin-inline:auto;box-sizing:border-box}
    </style>`;
    this._panel = document.createElement("ha-dialog");
    this._panel.open = true;
    this._panel.hideActions = true;
    const content = document.createElement("div");
    content.className = "content";
    const header = document.createElement("div");
    header.className = "header";
    const title = document.createElement("h2");
    title.textContent = schedule ? (schedule.area === "heating" ? "Heizung – Zeitprogramme" : "Warmwasser – Zeitprogramme") : params.title;
    title.id = "mode-title";
    this._panel.setAttribute("aria-label", params.title);
    header.append(title);
    if (infoConfig) {
      const info = helpers.createCardElement({ ...infoConfig, header: true });
      info.hass = this._hass;
      header.append(info);
    }
    content.append(header, this._card);
    this._panel.append(content);
    this._panel.addEventListener("closed", () => this.closeDialog());
    this.shadowRoot.append(this._panel);
  }

  closeDialog() {
    if (this._closing) return true;
    this._closing = true;
    if (this._panel) this._panel.open = false;
    if (this.params?.owner) this.params.owner._dialog = null;
    this.dispatchEvent(new CustomEvent("dialog-closed", {
      bubbles: true, composed: true, detail: { dialog: this.localName },
    }));
    return true;
  }

  disconnectedCallback() {
    if (this.params?.owner) this.params.owner._dialog = null;
  }
}

if (!customElements.get("wolflink-mode-dialog")) customElements.define("wolflink-mode-dialog", WolfLinkModeDialog);
if (!customElements.get("wolflink-mode-popup")) customElements.define("wolflink-mode-popup", WolfLinkModePopup);
window.customCards = window.customCards || [];
window.customCards.push({ type: "wolflink-mode-popup", name: "WolfLink Mode Popup",
  description: "Compact party/holiday button with a local dialog" });

/* Shows the transport/readback stages reported by the integration, not a timer. */
function wolfOpenChoice(owner, entity, title) {
  owner.dispatchEvent(new CustomEvent('show-dialog', { bubbles:true, composed:true,
    detail:{dialogTag:'wolflink-choice-dialog',dialogImport:()=>Promise.resolve(),
      dialogParams:{owner,entity,title:title==="Programmwahl"?(owner._hass?.states[entity]?.attributes.friendly_name||title):title,hass:owner._hass}} }));
}
class WolfLinkChoiceDialog extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});}
  set hass(value){const previous=this._hass?.states[this.params?.entity];this._hass=value;if(previous!==value?.states[this.params?.entity])this.render();}
  showDialog(params){this._closing=false;this._error="";this._busy=false;this.params=params;params.owner._dialog=this;this._hass=params.hass;this.render();}
  render(){
    if(!this.params||this._closing)return;
    const state=this._hass?.states[this.params.entity];
    this.shadowRoot.innerHTML=`<style>ha-dialog{--mdc-dialog-min-width:min(320px,calc(100vw - 32px));--mdc-dialog-max-width:380px;--dialog-content-padding:16px}h2{font-size:18px;margin:0 0 12px}button{display:flex;align-items:center;gap:12px;width:100%;min-height:46px;padding:10px 12px;margin:4px 0;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit;text-align:left;cursor:pointer}button[aria-checked=true]{border-color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 10%,var(--card-background-color))}button:disabled{opacity:.55;cursor:default}.mark{color:var(--primary-color)}.message{font-size:12px;color:var(--secondary-text-color)}button:focus-visible{outline:2px solid var(--primary-color)}</style><ha-dialog open hideActions><h2></h2><div role="radiogroup"></div><div class="message" role="status"></div></ha-dialog>`;
    const panel=this.shadowRoot.querySelector('ha-dialog');panel.hideActions=true;
    panel.setAttribute('aria-label',this.params.title);
    this.shadowRoot.querySelector('h2').textContent=this.params.title;
    const group=this.shadowRoot.querySelector('[role=radiogroup]');group.setAttribute('aria-label',this.params.title);
    for(const option of state?.attributes.options||[]){
      const button=document.createElement('button');button.type='button';button.setAttribute('role','radio');button.setAttribute('aria-checked',String(state.state===option));
      button.disabled=this._busy||state.attributes.read_only===true||['unknown','unavailable'].includes(state.state);
      const mark=document.createElement('span');mark.className='mark';mark.textContent=state.state===option?'◉':'○';mark.setAttribute('aria-hidden','true');
      button.append(mark,document.createTextNode(this._hass.formatEntityState({...state,state:option})));button.onclick=()=>this.choose(option);group.append(button);
    }
    this.shadowRoot.querySelector('.message').textContent=this._error||(this._busy?'Wird gesendet …':state?.attributes.read_only?'Nur Lesen':(!group.children.length?'Keine Optionen verfügbar':''));
    panel.addEventListener('closed',()=>this.closeDialog());
  }
  async choose(option){
    const state=this._hass?.states[this.params.entity];
    if(this._busy||!state||state.attributes.read_only||['unknown','unavailable'].includes(state.state)||!state.attributes.options?.includes(option))return;
    if(state.state===option){this.closeDialog();return;}
    this._busy=true;this._error='';this.render();
    try{await this._hass.callService('select','select_option',{entity_id:this.params.entity,option});this.closeDialog();}
    catch(error){this._error=error.message||'Übertragung fehlgeschlagen';}
    finally{this._busy=false;if(this.params.owner._dialog===this)this.render();}
  }
  closeDialog(){if(this._closing)return true;this._closing=true;const panel=this.shadowRoot.querySelector('ha-dialog');if(panel)panel.open=false;if(this.params?.owner)this.params.owner._dialog=null;this.dispatchEvent(new CustomEvent('dialog-closed',{bubbles:true,composed:true,detail:{dialog:this.localName}}));return true;}
}
if(!customElements.get('wolflink-choice-dialog'))customElements.define('wolflink-choice-dialog',WolfLinkChoiceDialog);
class WolfLinkWriteStatus extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (typeof config.entity !== "string") throw new Error("A control entity is required");
    this.config = config;
    this._inner = null;
    this._renderToken = {};
    if (config.inner_card) {
      const token = this._renderToken;
      this.shadowRoot.innerHTML = `<style>${WOLF_STAGE_CSS}
        :host{display:block} ha-card{overflow:hidden;height:100%}
        .badge{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
      </style><ha-card><div class="inner"></div><div class="badge" aria-live="polite"></div></ha-card>`;
      window.loadCardHelpers().then(helpers => {
        if (token !== this._renderToken) return;
        // Native tile retains Home Assistant's confirmation and action handling.
        const native = { ...config.inner_card };
        if (native.type === "button") {
          native.type = "tile";
          native.hide_state = true;
          native.vertical = false;
          delete native.show_state;
          delete native.icon_height;
        }
        this._inner = helpers.createCardElement(native);
        if (this._hass) this._inner.hass = this._hass;
        this.shadowRoot.querySelector(".inner").append(this._inner);
      });
      this.updateState();
      return;
    }
    this.shadowRoot.innerHTML = `<style>${WOLF_STAGE_CSS}
      :host{display:block} ha-card{height:100%;overflow:hidden}
      button{border:0;background:none;color:var(--primary-text-color);font:inherit;cursor:pointer;
        display:flex;align-items:center;gap:12px;width:100%;min-height:56px;padding:8px 26px 8px 12px;text-align:left}
      button:focus-visible{outline:2px solid var(--primary-color);outline-offset:-3px}
      ha-icon{color:var(--state-icon-color);flex-shrink:0}.text{flex:1;min-width:0}
      .name{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row{display:flex;gap:5px;align-items:center;flex-wrap:wrap}
      .value{font-size:13px}.badge{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){button{min-height:44px;box-sizing:border-box;padding:4px 20px 4px 8px;gap:7px;line-height:16px}.name{font-size:12px}.value,.state{font-size:11px}ha-icon{--mdc-icon-size:20px}}    button{min-height:48px;box-sizing:border-box;padding:6px 22px 6px 10px;gap:8px}.name{font-size:var(--wolf-control-font,14px)}.value{font-size:var(--wolf-control-value-font,13px)}</style><ha-card><button type="button"><ha-icon icon="mdi:format-list-bulleted"></ha-icon>
      <div class="text"><div class="name"></div><div class="row"><span class="value"></span>
      <span class="badge" aria-live="polite"></span></div></div></button></ha-card>`;
    this.shadowRoot.querySelector(".name").textContent = config.name || "Programmwahl";
    if (config.icon) this.shadowRoot.querySelector("ha-icon").icon = config.icon;
    this.shadowRoot.querySelector("button").addEventListener("click", () => {
      if(this.config.entity.startsWith('select.')){wolfOpenChoice(this,this.config.entity,this.config.name||'Programmwahl');return;}
      this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true,
        detail: { entityId: this.config.entity } }));
    });
    this.updateState();
  }

  set hass(hass) { this._hass = hass; if (this._inner) this._inner.hass = hass; if(this._dialog)this._dialog.hass=hass; this.updateState(); }

  updateState() {
    if (!this.config || !this.shadowRoot.querySelector("ha-card")) return;
    const state = this._hass?.states[this.config.entity];
    const labels = this.config.compact ? WOLF_COMPACT_LABELS : WOLF_WRITE_LABELS;
    const stage = wolfWriteStage(state);
    this.shadowRoot.querySelector("ha-card").dataset.stage = stage;
    this.shadowRoot.querySelector("ha-card").title = WOLF_WRITE_LABELS[stage] || "Nicht verf�gbar";
    const value = this.shadowRoot.querySelector(".value");
    if (value) value.textContent = state ? this._hass.formatEntityState(state) : "Nicht verfügbar";
    this.shadowRoot.querySelector(".badge").textContent =
      state?.entity_id.startsWith("button.") && stage === "reported" ? "Bereit" :
      (labels[stage] ?? "Nicht verfügbar");
    const button = this.shadowRoot.querySelector("button");
    if (button) button.title = WOLF_WRITE_LABELS[stage] || "Nicht verfügbar";
  }

  getCardSize() { return 1; }
  getGridOptions() { return { columns: this.config?.compact ? 6 : 12, rows: 1, min_rows: 1 }; }
}
if (!customElements.get("wolflink-write-status")) customElements.define("wolflink-write-status", WolfLinkWriteStatus);
window.customCards.push({ type: "wolflink-write-status", name: "WolfLink Write Status",
  description: "Mode choice with transport and readback colours" });
/* SmartSet-inspired number dial; writes only on an explicit +/- click. */
class WolfLinkSmartsetDial extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(config){
    if(!config.entity?.startsWith("number.")) throw new Error("Eine Number-Entität ist erforderlich");
    this.config=config;
    this.shadowRoot.innerHTML=`<style>${WOLF_STAGE_CSS}
      :host{display:block}ha-card{padding:20px 12px 12px;border-radius:8px;box-sizing:border-box}
      .dial{position:relative;max-width:370px;margin:auto;aspect-ratio:1;container-type:inline-size}
      svg{width:100%;height:100%;overflow:visible}.track{fill:none;stroke:var(--divider-color,#eee);stroke-width:8}
      .arc{fill:none;stroke-width:8;stroke-linecap:round}.middle{position:absolute;inset:24% 14% 20%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
      .label,.secondary{color:var(--secondary-text-color);font-size:16px;line-height:1.4}.value{font-size:58px;font-weight:300;line-height:1.3;font-variant-numeric:tabular-nums;white-space:nowrap}
      .actual{font-size:22px;color:var(--secondary-text-color);margin-top:4px}.secondary{margin-top:12px}
      button{font:inherit;background:none;border:0;color:var(--primary-text-color);cursor:pointer}button:disabled{opacity:.35;cursor:default}button:focus-visible{outline:2px solid var(--primary-color);border-radius:8px}
      .adjust{position:absolute;bottom:3%;font-size:38px;border:2px solid var(--secondary-text-color);border-radius:50%;width:48px;height:48px;display:grid;place-items:center;line-height:1;padding:0}.minus{right:5%}.plus{left:5%}
      .open{padding:0}.hint{text-align:center;font-size:11px;color:var(--secondary-text-color);min-height:14px}.error{color:var(--error-color);font-size:12px;text-align:center}
      .value{font-size:clamp(34px,16cqw,58px)}.label,.secondary{font-size:clamp(12px,4.3cqw,16px)}.actual{font-size:clamp(16px,6cqw,22px)}.secondary{margin-top:clamp(4px,3cqw,12px)}.adjust{width:clamp(36px,13cqw,48px);height:clamp(36px,13cqw,48px);font-size:clamp(28px,10cqw,38px)}
      @media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){ha-card{padding:8px 6px 5px}.dial{width:min(100%,clamp(140px,calc(100dvh - 550px),230px))}svg{display:block}.middle{inset:20% 12% 19%}.label,.secondary{font-size:11px;line-height:1.25}.value{font-size:32px;line-height:1.1}.actual{font-size:15px;margin-top:2px}.secondary{margin-top:4px}.adjust{width:44px;height:44px;font-size:30px;bottom:0}.plus{left:0}.minus{right:0}.hint{font-size:10px;min-height:12px}.error:empty{display:none}}
    ha-card{padding:10px 8px 6px}.dial{width:min(100%,var(--wolf-dial-size,330px))}.middle{inset:20% 12% 19%}.label,.secondary{font-size:clamp(12px,4.3cqw,16px);line-height:1.25}.value{font-size:clamp(34px,16cqw,54px);line-height:1.1}.actual{font-size:clamp(16px,6cqw,22px);margin-top:3px}.secondary{margin-top:5px}.adjust{width:44px;height:44px;font-size:30px;bottom:0}.plus{left:0}.minus{right:0}.error:empty{display:none}</style><ha-card><div class="dial"><svg viewBox="0 0 300 300" aria-hidden="true"><defs><linearGradient id="wolf-gradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#db1824"/><stop offset=".45" stop-color="#b12c4a"/><stop offset="1" stop-color="#008aca"/></linearGradient></defs><path class="track" d="M 150 22 A 128 128 0 1 0 278 150"/><path class="arc" stroke="url(#wolf-gradient)" d="M 150 22 A 128 128 0 1 0 278 150"/><circle class="knob" r="13" fill="var(--card-background-color,white)" stroke="var(--primary-text-color)" stroke-width="1.2"/></svg><div class="middle"><div class="label"></div><button class="open" title="Temperatur einstellen"><span class="value"></span></button><div class="secondary"></div><div class="actual"></div></div><button class="adjust plus" aria-label="Wert erhöhen">+</button><button class="adjust minus" aria-label="Wert verringern">−</button></div><div class="hint">Zum Einstellen auf den Wert tippen</div><div class="error" role="alert"></div></ha-card>`;
    this.shadowRoot.querySelector('.label').textContent=config.name||"Temperatur";
    this.shadowRoot.querySelector('.secondary').textContent=config.secondary_name||"";
    this.shadowRoot.querySelector('.open').onclick=()=>{this.cancelDraft();this.dispatchEvent(new CustomEvent('hass-more-info',{bubbles:true,composed:true,detail:{entityId:this.config.entity}}));};
    this.shadowRoot.querySelector('.plus').onclick=()=>this.adjust(1);
    this.shadowRoot.querySelector('.minus').onclick=()=>this.adjust(-1);
    this.updateState();
  }
  set hass(hass){this._hass=hass;this.updateState();}
  updateState(){
    if(!this.config||!this._hass)return;
    const state=this._hass.states[this.config.entity], card=this.shadowRoot.querySelector('ha-card');
    let stage=wolfWriteStage(state);
    if(state?.attributes.read_only===true||['unknown','unavailable'].includes(state?.state))this.cancelDraft(false);
    if(this._submitted!=null&&!this._busy&&(stage==='failed'||stage==='confirmed'||(Number(state?.state)===this._submitted&&!['sending','awaiting_confirmation'].includes(stage))))this._submitted=null;
    if(this._draft!=null)stage='awaiting_confirmation';else if(this._submitted!=null&&stage!=='failed')stage=this._busy?'sending':'awaiting_confirmation';
    card.dataset.stage=stage;card.title=this._draft!=null?"Auswahl · noch nicht übertragen":WOLF_WRITE_LABELS[stage]||"Nicht verfügbar";
    const actualValue=Number(state?.state), value=this._draft??this._submitted??actualValue, a=state?.attributes||{}, min=Number(a.min),max=Number(a.max);
    const valid=state&&Number.isFinite(value)&&state.state!=="unavailable"&&state.state!=="unknown";
    this.shadowRoot.querySelector('.value').textContent=valid?this._hass.formatEntityState({...state,state:String(value)}):"–";
    const actualLabel=valid?this._hass.formatEntityState(state):"–";
    this.shadowRoot.querySelector('.hint').textContent=this._draft!=null?"Auswahl · wird nach der Klickpause gesendet. Anlagenwert: "+actualLabel:this._submitted!=null?"Übertragung wird bestätigt · Anlagenwert: "+actualLabel:"Zum Einstellen auf den Wert tippen";
    const actual=this._hass.states[this.config.secondary_entity];
    this.shadowRoot.querySelector('.actual').textContent=actual?this._hass.formatEntityState(actual):"–";
    const angle=(Math.max(0,Math.min(1,(value-min)/(max-min)))*270)*Math.PI/180;
    const knob=this.shadowRoot.querySelector('.knob');knob.setAttribute('cx',150+128*Math.cos(angle));knob.setAttribute('cy',150+128*Math.sin(angle));knob.style.display=valid?'':'none';
    const locked=!valid||a.read_only===true||this._busy||this._submitted!=null||['sending','awaiting_confirmation'].includes(wolfWriteStage(state));
    this.shadowRoot.querySelector('.plus').disabled=locked||value>=max;
    this.shadowRoot.querySelector('.minus').disabled=locked||value<=min;
  }
  cancelDraft(render=true){clearTimeout(this._draftTimer);this._draftTimer=null;this._draft=null;if(render)this.updateState();}
  disconnectedCallback(){this.cancelDraft(false);}
  async adjust(direction){
    const state=this._hass?.states[this.config.entity];if(!state||this._busy||this._submitted!=null||state.attributes.read_only===true||['sending','awaiting_confirmation'].includes(wolfWriteStage(state)))return;
    const a=state.attributes,v=this._draft??Number(state.state),step=Number(a.step),min=Number(a.min),max=Number(a.max);
    if(['unknown','unavailable'].includes(state.state)||![v,step,min,max].every(Number.isFinite)||step<=0)return;
    const target=Number((v+direction*step).toFixed(6));if(target<min||target>max)return;
    clearTimeout(this._draftTimer);this._draft=target;this.shadowRoot.querySelector('.error').textContent='';
    this._draftTimer=setTimeout(()=>this.flushDraft(),900);this.updateState();
  }
  async flushDraft(){
    clearTimeout(this._draftTimer);this._draftTimer=null;
    const target=this._draft,state=this._hass?.states[this.config.entity];
    if(target==null)return;
    this._draft=null;
    const a=state?.attributes||{},stage=wolfWriteStage(state),step=Number(a.step),min=Number(a.min),max=Number(a.max);
    if(!this.isConnected||!state||a.read_only===true||['sending','awaiting_confirmation','unavailable'].includes(stage)||![target,step,min,max].every(Number.isFinite)||step<=0||target<min||target>max){this.updateState();return;}
    if(target===Number(state.state)){this.updateState();return;}
    this._submitted=target;this._busy=true;this.updateState();
    try{await this._hass.callService('number','set_value',{entity_id:this.config.entity,value:target});}
    catch(error){this._submitted=null;this.shadowRoot.querySelector('.error').textContent=error.message||"Änderung konnte nicht bestätigt werden";}
    finally{this._busy=false;this.updateState();}
  }
  getCardSize(){return 6;}
  getGridOptions(){return{columns:12,rows:6,min_rows:5};}
}
if(!customElements.get('wolflink-smartset-dial'))customElements.define('wolflink-smartset-dial',WolfLinkSmartsetDial);
window.customCards.push({type:'wolflink-smartset-dial',name:'WolfLink SmartSet Temperatur',description:'Temperaturregler mit Anlagenrückmeldung'});

function wolfScheduleStage(day) {
  if (day?.write_status === 'failed') return 'failed';
  if (['sending','awaiting_confirmation','awaiting_period_confirmation'].includes(day?.write_status)) return day.write_status;
  return day?.status === 'ok' ? (day.write_status === 'confirmed' ? 'confirmed' : 'reported') : 'unavailable';
}
class WolfLinkSchedule extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._program=3;}
 setConfig(config){this.config=config;this._program=Number(config.program)||3;this.render();}
 set hass(hass){this._hass=hass;this.render();if(this.isConnected&&!this._loaded&&!this._loading)this.load();}
 connectedCallback(){if(this._hass&&!this._loaded&&!this._loading)this.load();}
 async load(){
  if(!this._hass||this._loading)return;
  this._loading=true;this._error='';this.render();
  try{const result=await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'get_time_program',service_data:{device_id:this.config.device_id,area:this.config.area,program:this._program},return_response:true});this._data=result.response;this._loaded=true;}
  catch(e){this._error=e.message||'Zeitprogramm konnte nicht gelesen werden';}
  finally{this._loading=false;this.render();
   clearTimeout(this._pollTimer);
   if(this.isConnected && Object.values(this._data?.days||{}).some(day=>day.write_status==='awaiting_confirmation'))this._pollTimer=setTimeout(()=>this.load(),15000);
  }
 }
 disconnectedCallback(){clearTimeout(this._pollTimer);}
 render(){
  if(!this.config)return;
  this.shadowRoot.innerHTML=`<style>:host{display:block}ha-card{padding:12px;border-radius:8px}header{display:flex;align-items:center;justify-content:space-between;gap:10px}select,button{font:inherit;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:18px;padding:8px 14px;cursor:pointer}button:disabled{opacity:.45;cursor:default}h3{font-size:15px;margin:12px 0 4px}.info{font-size:11px;color:var(--secondary-text-color);line-height:1.35}.copy{padding:12px 0}.copy>button{font-size:12px;margin:4px}.targets{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.targets label{font-size:12px;display:flex;align-items:center;gap:4px}.editor{grid-column:1/-1;padding:8px 0}.editrow{display:flex;gap:6px;margin-bottom:6px}.editrow input{width:85px;font:inherit;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px;padding:6px}.editor>button{margin:3px;font-size:12px}.edit{position:absolute;left:0;bottom:5px;font-size:10px;padding:2px 6px}.day{position:relative;padding:7px 0;border-bottom:1px solid var(--divider-color);display:grid;grid-template-columns:82px minmax(0,1fr);column-gap:10px}.day-status{display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:0;flex:0 0 7px;vertical-align:middle;background:#78909c}.day-status[data-stage="reported"],.day-status[data-stage="confirmed"]{background:#43a047}.day-status[data-stage="awaiting_confirmation"],.day-status[data-stage="awaiting_period_confirmation"]{background:#f9a825}.day-status[data-stage="sending"]{background:#2196f3}.day-status[data-stage="failed"]{background:#e53935}.name{display:flex;align-items:center;justify-content:space-between;gap:2px;white-space:nowrap;font-size:13px;grid-row:1/4;align-self:start;margin-top:3px}.track{margin-top:5px!important}.track{height:6px;background:var(--divider-color);position:relative;margin:0 5px}.slot{position:absolute;height:6px;background:var(--primary-text-color);border-radius:4px}.slot:before,.slot:after{content:'';position:absolute;top:-4px;width:14px;height:14px;border-radius:50%;background:var(--primary-text-color)}.slot:before{left:-7px}.slot:after{right:-7px}.axis{display:flex;justify-content:space-between;font-size:11px;color:var(--secondary-text-color);margin-top:3px}.times{font-size:11px;margin-top:3px;display:flex;gap:5px;flex-wrap:wrap}.time{background:var(--secondary-background-color);border-radius:4px;padding:2px 5px}.activate{width:100%;margin-top:10px;border-radius:4px;min-height:44px}.error{color:var(--error-color);font-size:12px}.error:empty{display:none}@media(max-height:750px){.day{padding:3px 0}.name{font-size:12px}h3{margin-top:8px}.activate{min-height:36px;margin-top:6px}ha-card{padding:8px}select,button{padding:5px 10px}}@media(max-width:400px){.day{grid-template-columns:78px minmax(0,1fr);column-gap:6px}.name{font-size:12px}}</style><ha-card><header><select aria-label="Zeitprogramm anzeigen"><option value="1">Programm 1</option><option value="2">Programm 2</option><option value="3">Programm 3</option></select><button class="refresh">Aktualisieren</button></header><h3>Betriebszeiten</h3><div class="info">Zeitfenster · 0 bis 24 Uhr. Gelb markierte Zeiten sind übertragen, noch nicht zurückgelesen. Anzeigen schaltet die Anlage nicht um.</div><div class="days"></div><div class="error" role="alert"></div><button class="activate"></button><div class="info" style="margin-top:8px">Bearbeiten öffnet einen lokalen Tagesentwurf. Erst Speichern überträgt diesen Tag. Aktivieren schaltet das ausgewählte Programm ein.</div></ha-card>`;
  const selector=this.shadowRoot.querySelector('select');selector.value=String(this._program);selector.disabled=this._loading||!!this._editing||!!this._copyDraft||this._copying;
  selector.onchange=()=>{this._program=Number(selector.value);this._data=null;this.load();};
  const refresh=this.shadowRoot.querySelector('.refresh');refresh.disabled=this._loading||!!this._editing||this._copying;refresh.textContent=this._loading?'Lädt …':'Aktualisieren';refresh.onclick=()=>this.load();
  this.shadowRoot.querySelector('.error').textContent=this._error||'';
  const names=['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag'];
  const keys=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
  const holder=this.shadowRoot.querySelector('.days');
  keys.forEach((key,i)=>{if(this._copyDraft&&this._copyDraft.source!==key)return;if(this._editing&&this._editing.weekday!==key)return;const day=this._data?.days?.[key];const div=document.createElement('div');div.className='day';const name=document.createElement('div');name.className='name';name.textContent=names[i];const dot=document.createElement('span');dot.className='day-status';const stage=wolfScheduleStage(day);dot.dataset.stage=stage;const statusLabel=WOLF_WRITE_LABELS[stage]||'Keine bestätigten Zeitdaten';dot.title=statusLabel;dot.setAttribute('role','img');dot.setAttribute('aria-label',`${names[i]}: ${statusLabel}`);name.append(dot);div.append(name);const track=document.createElement('div');track.className='track';div.append(track);const axis=document.createElement('div');axis.className='axis';axis.innerHTML='<span>0</span><span>24</span>';div.append(axis);const times=document.createElement('div');times.className='times';
   if(day?.status==='ok'){for(const window of day.windows){const minutes=t=>{const [h,m]=t.split(':').map(Number);return h*60+m;};const start=minutes(window.start),end=minutes(window.end);if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>1440||start>=end)continue;const span=document.createElement('span');span.className='slot';span.style.left=`${start/14.4}%`;span.style.width=`${(end-start)/14.4}%`;track.append(span);const text=document.createElement('span');text.className='time';text.textContent=`${window.start} – ${window.end}`;times.append(text);}if(!day.windows.length)times.textContent='Keine Betriebszeit';}
   else times.textContent=this._loading?'Wird gelesen …':'Keine bestätigten Zeitdaten';div.append(times);
   if (day?.status==='ok' && day.write_supported && !this._data?.read_only && !this._editing && !this._copyDraft && !this._copying) {
    const edit=document.createElement('button');edit.className='edit';edit.textContent='Bearbeiten';edit.disabled=this._saving||!!this._editing;edit.onclick=()=>{this._editing={weekday:key,expected:day.serialized,windows:day.windows.map(w=>({...w}))};this.render();};div.append(edit);
   }
   if(this._editing?.weekday===key){
    const form=document.createElement('div');form.className='editor';
    const draft=this._editing;
    draft.windows.forEach((window,index)=>{const row=document.createElement('div');row.className='editrow';for(const field of ['start','end']){const input=document.createElement('input');input.type='text';input.inputMode='numeric';input.value=window[field];input.placeholder='HH:mm';input.setAttribute('aria-label',`${names[i]} ${field==='start'?'Beginn':'Ende'} ${index+1}`);input.disabled=this._saving;input.oninput=()=>window[field]=input.value;row.append(input);}const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label','Zeitraum entfernen');remove.disabled=this._saving;remove.onclick=()=>{draft.windows.splice(index,1);this.render();};row.append(remove);form.append(row);});
    const add=document.createElement('button');add.textContent='+ Zeitraum';add.disabled=this._saving||draft.windows.length>=3;add.onclick=()=>{draft.windows.push({start:'06:00',end:'08:00'});this.render();};form.append(add);
    const save=document.createElement('button');save.textContent=this._saving?'Wird geprüft …':'Tag speichern';save.disabled=this._saving;save.onclick=()=>this.saveDay();form.append(save);
    const cancel=document.createElement('button');cancel.textContent='Verwerfen';cancel.disabled=this._saving;cancel.onclick=()=>{this._editing=null;this.render();};form.append(cancel);
    const hint=document.createElement('div');hint.className='info';hint.textContent='Maximal 3 Zeiträume · 15-Minuten-Schritte · Ende bis 24:00. Speichern ändert nur diesen Tag; das aktive Programm bleibt erhalten.';form.append(hint);div.append(form);
   }
   if(day?.write_status && !['reported','confirmed'].includes(day.write_status)){const status=document.createElement('div');status.className='info';status.style.gridColumn='1 / -1';status.textContent=WOLF_WRITE_LABELS[day.write_status]||day.write_status;div.append(status);}
   holder.append(div);
  });
  if(!this._editing && this._data && !this._data.read_only) {
   const container=document.createElement('div');container.className='copy';
   if(!this._copyDraft){const open=document.createElement('button');open.textContent='Tag kopieren';open.disabled=this._loading;open.onclick=()=>{this._copyDraft={source:'monday',targets:new Set()};this._message='';this.render();};container.append(open);}
   else {
    const draft=this._copyDraft;const label=document.createElement('label');label.textContent='Zeiten kopieren von ';const source=document.createElement('select');source.setAttribute('aria-label','Quelltag');source.disabled=this._copying;
    keys.forEach((key,i)=>{const option=document.createElement('option');option.value=key;option.textContent=names[i];option.disabled=this._data.days[key]?.status!=='ok';source.append(option);});source.value=draft.source;source.onchange=()=>{draft.source=source.value;draft.targets.delete(source.value);this.render();};label.append(source);container.append(label);
    const all=document.createElement('button');all.textContent='Ganze Woche';all.disabled=this._copying;all.onclick=()=>{draft.targets=new Set(keys.filter(key=>key!==draft.source&&this._data.days[key]?.status==='ok'&&this._data.days[key]?.write_supported));this.render();};container.append(all);
    const targets=document.createElement('div');targets.className='targets';keys.forEach((key,i)=>{const item=document.createElement('label');const check=document.createElement('input');check.type='checkbox';check.checked=draft.targets.has(key);check.disabled=this._copying||key===draft.source||this._data.days[key]?.status!=='ok'||!this._data.days[key]?.write_supported;check.onchange=()=>{if(check.checked)draft.targets.add(key);else draft.targets.delete(key);this.render();};item.append(check,document.createTextNode(names[i]));targets.append(item);});container.append(targets);
    const save=document.createElement('button');save.textContent=this._copying?'Kopieren wird geprüft …':'Auf gewählte Tage übertragen';save.disabled=this._copying||!draft.targets.size;save.onclick=()=>this.copyDays();container.append(save);const cancel=document.createElement('button');cancel.textContent='Abbrechen';cancel.disabled=this._copying;cancel.onclick=()=>{this._copyDraft=null;this.render();};container.append(cancel);
    const warning=document.createElement('div');warning.className='info';warning.textContent='Ersetzt die Zeiten der gewählten Tage in diesem Profil. Quelle und aktives Profil bleiben unverändert. Bei fehlender Bestätigung wird angehalten; bereits bestätigte Tage bleiben gespeichert.';container.append(warning);
   }
   holder.append(container);
  }
  if(this._message){const message=document.createElement('div');message.className='info';message.setAttribute('role','status');message.textContent=this._message;holder.append(message);}
  const state=this._hass?.states[this.config.entity];const active=Number(state?.state);const button=this.shadowRoot.querySelector('.activate');button.textContent=active===this._program?`Programm ${this._program} · aktiv`:`Programm ${this._program} aktivieren`;
  button.disabled=this._loading||this._activating||!!this._editing||!!this._copyDraft||this._copying||!state||['unknown','unavailable'].includes(state.state)||state.attributes.read_only===true||active===this._program;
  button.onclick=async()=>{this._activating=true;this.render();try{await this._hass.callService('select','select_option',{entity_id:this.config.entity,option:String(this._program)});}catch(e){this._error=e.message||'Aktivierung konnte nicht bestätigt werden';}finally{this._activating=false;this.render();}};
 }
 async copyDays(){
  if(!this._copyDraft||this._copying)return;
  const keys=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
  const names=['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag'];
  const draft=this._copyDraft,source=this._data?.days[draft.source];
  const targets=keys.filter(key=>draft.targets.has(key)&&key!==draft.source);
  if(!source||source.status!=='ok'||!targets.length)return;
  if(source.write_status==='awaiting_confirmation'){this._error='Quelltag ist noch nicht von der Anlage bestätigt.';this.render();return;}
  const original=Object.fromEntries(targets.map(key=>[key,this._data.days[key]?.serialized]));
  this._copying=true;this._error='';this._message='';this.render();const completed=[];
  let failure='';
  try{
   await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'preview_time_program_day',service_data:{area:this.config.area,program:this._program,weekday:draft.source,windows:source.windows},return_response:true});
   if(!window.confirm(`Zeiten von ${names[keys.indexOf(draft.source)]} auf ${targets.map(key=>names[keys.indexOf(key)]).join(', ')} in Programm ${this._program} kopieren? Die bisherigen Zielzeiten werden ersetzt.`))return;
   const fresh=await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'get_time_program',service_data:{device_id:this.config.device_id,area:this.config.area,program:this._program},return_response:true});
   if(fresh.response?.read_only||fresh.response?.days[draft.source]?.serialized!==source.serialized||targets.some(key=>fresh.response?.days[key]?.serialized!==original[key]))throw new Error('Zeiten wurden zwischenzeitlich geändert. Bitte neu laden und Kopierauswahl erneut prüfen.');
   for(const weekday of targets){
    const result=await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'write_time_program_day',service_data:{device_id:this.config.device_id,area:this.config.area,program:this._program,weekday,windows:source.windows,expected:original[weekday]},return_response:true});
    if(result.response?.write_status!=='confirmed')throw new Error(`${names[keys.indexOf(weekday)]}: Bestätigung steht aus. Keine weiteren Tage übertragen.`);
    completed.push(names[keys.indexOf(weekday)]);
   }
   this._copyDraft=null;
  }catch(e){failure=e.message||'Kopieren konnte nicht bestätigt werden';}
  finally{
   if(completed.length||failure){await this.load();this._message=completed.length?'Bestätigt gespeichert: '+completed.join(', '):'';this._error=failure;}
   this._copying=false;this.render();
  }
 }
 async saveDay(){
  if(!this._editing||this._saving)return;
  const draft=this._editing;this._saving=true;this._error='';this.render();
  try{
   await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'preview_time_program_day',service_data:{area:this.config.area,program:this._program,weekday:draft.weekday,windows:draft.windows},return_response:true});
   if(!window.confirm('Diesen Wochentag mit den eingegebenen Zeiten an WOLF übertragen?'))return;
   await this._hass.callWS({type:'call_service',domain:'wolflink_local',service:'write_time_program_day',service_data:{device_id:this.config.device_id,area:this.config.area,program:this._program,weekday:draft.weekday,windows:draft.windows,expected:draft.expected},return_response:true});
   this._editing=null;await this.load();
  }catch(e){this._error=e.message||'Zeiten konnten nicht bestätigt werden';}
  finally{this._saving=false;this.render();}
 }
 getCardSize(){return 12;}
}
if(!customElements.get('wolflink-schedule'))customElements.define('wolflink-schedule',WolfLinkSchedule);
window.customCards.push({type:'wolflink-schedule',name:'WolfLink Wochenprogramm',description:'Gespeicherte Betriebszeiten und Programmauswahl'});

/* Small accessible help control: hover, keyboard focus or explicit touch/click. */
class WolfLinkModeInfo extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});}
 setConfig(config){
  this.config=config;
  this.shadowRoot.innerHTML=`<style>:host{display:block}.line{display:flex;justify-content:flex-end;align-items:center;gap:6px;color:var(--secondary-text-color);font-size:12px;padding:0 4px}button{font:inherit;font-size:17px;color:var(--secondary-text-color);background:none;border:0;border-radius:50%;width:32px;height:32px;cursor:pointer}button:focus-visible{outline:2px solid var(--primary-color)}.help{font-size:13px;line-height:1.5;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:8px;padding:10px 12px;margin:4px 0 8px}.help[hidden]{display:none}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){:host{margin-bottom:-12px}.bar{padding:0 4px;gap:8px;min-height:44px}h1{font-size:20px;line-height:24px}.bar>button{min-height:44px;padding:4px 8px}}p{margin:0 0 8px}p:last-child{margin:0}</style><div class="line"><span>Hinweise</span><button type="button" aria-label="Informationen zum Speichern und HA-Neustart" aria-expanded="false" aria-controls="mode-help">ⓘ</button></div><div class="help" id="mode-help" role="region" aria-label="Hinweise zum Modus" hidden><p class="party" hidden>Partymodus: 15 Minuten bis 24 Stunden, in 15-Minuten-Schritten.</p><p><strong>Eingaben ändern:</strong> Dauer bzw. Von/Bis bleiben zunächst nur im Formular.</p><p><strong>Speichern:</strong> Erst danach werden die Eingaben an die Anlage übertragen und geprüft.</p><p><strong>HA-Neustart:</strong> Nicht gespeicherte Eingaben gehen verloren. Die Formularfelder zeigen danach wieder Standardvorschläge.</p><p>Ein bereits an der Anlage aktivierter Party- oder Urlaubsmodus wird dadurch <strong>nicht beendet</strong>. Die Vorschlagswerte betreffen nur die Eingabefelder.</p></div>`;
  if (config.header) {
    const style = document.createElement('style');
    style.textContent = ':host{flex-shrink:0}.help{position:absolute;top:100%;left:0;right:0;z-index:20;box-shadow:0 4px 14px #0003;border:1px solid var(--divider-color);margin-top:4px;background:var(--card-background-color)}';
    this.shadowRoot.append(style);
  }
  this.shadowRoot.querySelector('.party').hidden=!config.party;
  const button=this.shadowRoot.querySelector('button'),help=this.shadowRoot.querySelector('.help');
  const show=visible=>{help.hidden=!visible;button.setAttribute('aria-expanded',String(visible));};
  this._pinned=false;
  button.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse')show(true);});
  this.addEventListener('pointerleave',()=>{if(!this._pinned)show(false);});
  button.addEventListener('focus',()=>show(true));
  button.addEventListener('blur',()=>{if(!this._pinned)show(false);});
  button.addEventListener('click',()=>{this._pinned=!this._pinned;show(this._pinned);});
  button.addEventListener('keydown',event=>{if(event.key==='Escape'){this._pinned=false;show(false);}});
 }
 set hass(hass){this._hass=hass;}
 getCardSize(){return 1;}
}
if(!customElements.get('wolflink-mode-info'))customElements.define('wolflink-mode-info',WolfLinkModeInfo);
/* One visual container per appliance area; native child actions are preserved. */
class WolfLinkAreaCard extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._cards=[];}
 setConfig(config){
  if(!Array.isArray(config.cards))throw new Error('Karten fehlen');this.config=config;const token={};this._token=token;this._cards=[];
  this.shadowRoot.innerHTML=`<style>:host{display:block;min-width:0}ha-card{padding:16px;border-radius:18px;border:1px solid var(--divider-color);background:var(--card-background-color);box-shadow:0 2px 8px #0000000a}header{display:flex;gap:10px;align-items:center;padding:0 2px 14px;font-weight:500;font-size:18px}ha-icon{color:var(--state-icon-color);--mdc-icon-size:22px}.body{min-width:0;display:grid;gap:8px}.body>*{min-width:0}@media(max-width:450px){ha-card{padding:12px;border-radius:14px}}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){ha-card{padding:8px;border-radius:14px}header{font-size:16px;line-height:22px;height:24px;padding-bottom:6px}.body{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.body>.wide{grid-column:1/-1}.body>.subheading{display:none}}ha-card{padding:10px}header{font-size:17px;padding-bottom:8px;min-height:26px}.body{grid-template-columns:var(--wolf-area-columns,minmax(0,1fr));gap:6px}.body>.wide{grid-column:1/-1}.body>.subheading{display:none}</style><ha-card><header><ha-icon></ha-icon><span></span></header><div class="body"></div></ha-card>`;
  this.shadowRoot.querySelector('header span').textContent=config.name||'WOLF';this.shadowRoot.querySelector('ha-icon').icon=config.icon||'mdi:radiator';
  window.loadCardHelpers().then(helpers=>{if(this._token!==token)return;this._cards=config.cards.map((def,index)=>{const card=helpers.createCardElement(def.type==='tile'?{...def,type:'custom:wolflink-reading'}:def);if(index<2||def.type==='grid')card.classList.add('wide');if(def.type==='heading')card.classList.add('subheading');if(this._hass)card.hass=this._hass;this.shadowRoot.querySelector('.body').append(card);return card;});});
 }
 set hass(hass){this._hass=hass;this._cards.forEach(card=>card.hass=hass);}
 getCardSize(){return 15;}
 getGridOptions(){return{columns:12,rows:'auto'};}
}
if(!customElements.get('wolflink-area-card'))customElements.define('wolflink-area-card',WolfLinkAreaCard);
window.customCards.push({type:'wolflink-area-card',name:'WolfLink Bereich',description:'Zusammenhängende Karte für Heizung oder Warmwasser'});

class WolfLinkDashboardTitle extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});}
 setConfig(){this.shadowRoot.innerHTML=`<style>:host{display:block}.bar{display:flex;align-items:center;gap:12px;padding:8px 4px}h1{font-size:24px;font-weight:500;flex:1;margin:0}button{font:inherit;color:var(--secondary-text-color);border:0;background:none;cursor:pointer;padding:8px}.help{padding:14px;border-radius:10px;background:var(--card-background-color);font-size:13px;line-height:1.6}.help[hidden]{display:none}.help section+section{margin-top:20px;padding-top:16px;border-top:1px solid var(--divider-color)}.help h2{font-size:15px;font-weight:600;margin:0 0 10px}.help p{margin:8px 0}.help ul,.help ol{margin:0;padding-left:20px}.help li{margin:7px 0}.legend{display:grid;grid-template-columns:80px minmax(0,1fr);gap:10px 14px;margin:0}.legend dt{display:flex;align-items:center;gap:8px;font-weight:600}.legend dd{margin:0}.legend i{width:8px;height:8px;border-radius:50%;flex-shrink:0}.blue{background:#2196f3}.yellow{background:#f9a825}.green{background:#43a047}.red{background:#e53935}.grey{background:#78909c}.help .note{padding:10px 12px;border-radius:6px;background:var(--secondary-background-color)}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){:host{margin-bottom:-14px}.bar{padding:0 4px;min-height:44px;gap:8px}h1{font-size:20px;line-height:24px}.bar>button{min-height:44px;padding:4px 8px}}:host{display:none}:host([inline]){display:block;position:relative;margin:0!important}:host([inline]) h1{display:none}:host([inline]) .bar{padding:0;min-height:44px}:host([inline]) .bar>button{min-height:44px;padding:8px;white-space:nowrap}:host([inline]) .help{position:absolute;right:0;top:100%;width:min(680px,calc(100vw - 40px));max-height:70dvh;overflow:auto;box-sizing:border-box;z-index:10;border:1px solid var(--divider-color);box-shadow:0 4px 18px #0003}</style><div class="bar"><h1>Wolf Smartlink</h1><button aria-label="Bedienung und Statuspunkte" aria-expanded="false">Hinweise ⓘ</button></div><div class="help" hidden>
<section><h2>Bedienung</h2><ul><li><strong>Kachel oder Wert antippen:</strong> Öffnet die jeweilige Einstellung.</li><li><strong>Plus/Minus:</strong> Mehrfach klicken und den Endwert wählen. Nach <strong>0,9 Sekunden Klickpause</strong> wird nur dieser Wert gesendet.</li><li><strong>Vor dem Senden:</strong> Die gelbe Auswahl ist noch lokal. Der bisherige Anlagenwert steht darunter.</li></ul></section>
<section><h2>Was bedeuten die Statuspunkte?</h2><dl class="legend"><dt><i class="blue"></i>Blau</dt><dd>Der Schreibauftrag wird bearbeitet und gesendet. Die Dauer hängt von WOLF und der Verbindung ab.</dd><dt><i class="yellow"></i>Gelb</dt><dd>Übertragen, aber noch nicht durch Rücklesen bestätigt. Am Temperaturregler auch: lokale Auswahl vor dem Senden.</dd><dt><i class="green"></i>Grün</dt><dd>Bestätigter oder gelesener Anlagenwert. Bedeutet nicht automatisch „eingeschaltet“.</dd><dt><i class="red"></i>Rot</dt><dd>Fehler oder keine Bestätigung. Der Befehl könnte die Anlage trotzdem erreicht haben; Istwert prüfen.</dd><dt><i class="grey"></i>Grau</dt><dd>Kein gültiger Anlagenwert verfügbar.</dd></dl></section>
<section><h2>Rückmeldung: Ablauf und Zeiten</h2><ol><li><strong>Direkt nach dem Schreiben:</strong> HA liest den Anlagenwert sofort zurück.</li><li><strong>Erste Prüfphase:</strong> <ul><li><strong>Lokal (ISM7):</strong> Weitere Wartepausen von <strong>1, 2, 3 und 5 Sekunden</strong> – insgesamt <strong>11 Sekunden Wartezeit</strong>.</li></ul>Hinzu kommen die Laufzeiten der Abfragen; bei passender Rückmeldung endet die Prüfung früher.</li><li><strong>Bestätigung noch offen:</strong> Erneute Abfrage normalerweise etwa <strong>alle 15 Sekunden</strong>.</li><li><strong>Weiterhin unbestätigter Einzelwert:</strong> Nach der ersten Prüfphase bis zu <strong>10 weitere Minuten</strong> Nachprüfung. Beim nächsten erfolgreichen Abruf ohne passenden Zielwert wird der Punkt rot. Eindeutige Fehler können sofort rot erscheinen.</li></ol><p class="note"><strong>Grün hat keine feste Wartezeit:</strong> Es erscheint erst, wenn der tatsächliche Anlagenwert passend zurückgelesen wurde. Ohne ausstehenden Auftrag aktualisiert HA standardmäßig ungefähr <strong>alle 60 Sekunden</strong>. Für Lokal ist dieser Abstand unter den Integrationsoptionen bei Read-only auf <strong>15 bis 900 Sekunden</strong> einstellbar; er gilt spätestens ab der nächsten regulären Abfrage. Keepalive hält alle 25 Sekunden nur die lokale Verbindung offen.</p><p>HA wiederholt nur das Lesen, nicht den Schreibbefehl. Erneutes Schalten beschleunigt die Bestätigung nicht.</p></section>
<section><h2>Zeitprogramme</h2><ul><li><strong>Programm auswählen:</strong> Zeigt dessen Wochenzeiten. Das aktive Programm bleibt unverändert.</li><li><strong>Aktivieren:</strong> Schaltet auf das angezeigte Programm um.</li><li><strong>Bearbeiten / Tag speichern:</strong> Zuerst einen lokalen Tagesentwurf ändern; erst Speichern überträgt ihn mit Rücklesekontrolle.</li><li><strong>Tag kopieren:</strong> Quelltag und Zieltage wählen. Erst „Auf gewählte Tage übertragen“ ersetzt die Zielzeiten. Bei ausstehender Bestätigung hält der Vorgang an.</li></ul><p class="note"><strong>Zeitpläne lokal:</strong> Die Tageszeiten werden direkt zurückgelesen, zunächst mit denselben Wartepausen von 1, 2, 3 und 5 Sekunden. Bleibt die Bestätigung aus, wird die lokale Nachprüfung bis zu 10 weitere Minuten vorgemerkt. Ein erfolgreicher Abgleich beendet sie früher.</p></section>
<section><h2>Party, Urlaub und Schreibfreigabe</h2><ul><li><strong>Party / Urlaub:</strong> Eingaben bleiben zunächst lokal. Speichern überträgt sie nach der Sicherheitsabfrage.</li><li><strong>Read-only:</strong> Sperrt Schreibzugriffe. Die Freigabe erfolgt in den Integrationsoptionen.</li></ul></section>
</div>`;const b=this.shadowRoot.querySelector('button'),h=this.shadowRoot.querySelector('.help');let pinned=false;const show=v=>{h.hidden=!v;b.setAttribute('aria-expanded',String(v));};b.onpointerenter=e=>{if(e.pointerType==='mouse')show(true);};this.onpointerleave=()=>{if(!pinned)show(false);};b.onclick=()=>{pinned=!pinned;show(pinned);};b.onfocus=()=>show(true);b.onblur=()=>{if(!pinned)show(false);};b.onkeydown=e=>{if(e.key==='Escape'){pinned=false;show(false);}};}
 set hass(value){this._hass=value;}
 getCardSize(){return 1;}
 getGridOptions(){return{columns:24,rows:'auto'};}
}
if(!customElements.get('wolflink-dashboard-title'))customElements.define('wolflink-dashboard-title',WolfLinkDashboardTitle);
/* Local tabs retain the existing controls and add an illustrative live plant view. */
class WolfLinkPlantDashboard extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._active='Bedienung';this._panels=[];}
 setConfig(config){
  if(!Array.isArray(config.area_cards)||config.area_cards.length!==2)throw new Error('Heizung und Warmwasser fehlen');
  this._overviewQuery?.removeEventListener('change',this._overviewResize);
  this.config=config;this._panels=[];const token={};this._token=token;
  this.shadowRoot.innerHTML=`<style>:host{display:block}.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:0 0 16px;justify-content:center}.tabs button{font:inherit;padding:10px 16px;border:0;border-bottom:2px solid transparent;background:none;color:var(--secondary-text-color);cursor:pointer}.tabs button[aria-selected=true]{color:var(--primary-text-color);border-color:var(--primary-color);font-weight:500}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){:host{margin-top:-6px}.tabs{gap:0;margin-bottom:8px}.tabs button{font-size:13px;padding:6px 12px;min-height:44px}}.plant-status{min-width:0}.plant-status>summary{cursor:pointer;min-height:44px;align-items:center;font-size:13px;color:var(--secondary-text-color)}.plant-status>summary{display:none}.panel[hidden]{display:none}.scheme{padding:18px;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:18px;margin-bottom:14px}.scheme h2{margin:0;font-size:18px}.scheme p{font-size:12px;color:var(--secondary-text-color)}svg{display:block;width:100%;max-width:850px;margin:auto;color:var(--primary-text-color)}svg text{fill:currentColor;font:14px sans-serif}.value{font-weight:600}.pipe{fill:none;stroke-width:6;stroke-linejoin:round}.hot{stroke:#cf263d}.cold{stroke:#568ac5}.box{fill:var(--secondary-background-color);stroke:var(--divider-color);stroke-width:2}button:focus-visible{outline:2px solid var(--primary-color)}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){.panel[aria-label="Übersicht"]:not([hidden]){display:grid;grid-template-columns:minmax(0,1fr);gap:4px;align-items:start}.plant-status>summary{display:flex}.scheme{padding:12px;margin-bottom:0}.scheme h2{font-size:16px}.scheme p{margin:6px 0;font-size:11px}.scheme svg{max-height:calc(100dvh - 330px);width:100%}}@media(orientation:landscape) and (max-height:600px){.scheme{padding:12px}.scheme svg{max-height:none;width:100%}.scheme p{font-size:11px;margin:6px 0}}.toolbar{display:flex;align-items:flex-start;gap:8px;margin-bottom:8px}.toolbar .tabs{flex:1;min-width:0;margin-bottom:0}.toolbar> wolflink-dashboard-title{flex-shrink:0}.tabs button{min-height:44px}@media(max-width:600px){.toolbar{gap:0}.tabs button{padding:8px;font-size:12px}}</style><div class="toolbar"><nav class="tabs" role="tablist" aria-label="WOLF Anlagenansicht"></nav></div><div class="panels"></div>`;
  const help=document.createElement('wolflink-dashboard-title');help.setAttribute('inline','');help.setConfig({});this.shadowRoot.querySelector('.toolbar').append(help);
  // Local legacy dashboards expose the native energy roles; generated ones pass credit explicitly.
  if(config.credit==='Tom74HH'||Object.keys(config.sensors||{}).some(key=>key.startsWith('energie_'))){const credit=document.createElement('div');credit.textContent='Tom74HH';credit.setAttribute('aria-label','Oberfläche von Tom74HH');credit.style.cssText='text-align:right;font-size:10px;line-height:14px;color:var(--secondary-text-color);opacity:.65;padding:3px 4px 0;user-select:none';this.shadowRoot.append(credit);}
  const labels=['Bedienung','Übersicht','Heizung','Warmwasser'];if(Object.keys(config.sensors||{}).some(k=>k.startsWith('energie_')))labels.push('Energiestatistik');this._labels=labels;if(!labels.includes(this._active))this._active=labels[0];
  for(const label of labels){const b=document.createElement('button');b.textContent=label;b.setAttribute('role','tab');b.onclick=()=>this.select(label);this.shadowRoot.querySelector('.tabs').append(b);const panel=document.createElement('div');panel.className='panel';panel.setAttribute('role','tabpanel');panel.setAttribute('aria-label',label);this.shadowRoot.querySelector('.panels').append(panel);this._panels.push(panel);}
  const overview=this._panels[1];overview.innerHTML=`<div class="scheme"><h2>Anlagenübersicht</h2><p>Live-Werte · Eigenes vereinfachtes Funktionsschema von Tom74HH. Keine Darstellung der tatsächlichen Rohrführung.</p>${wolfPortalPlantSvg()}</div><div class="plant-status"><div class="status-content"></div></div>`;

  const entities=(title,items)=>({type:'entities',title,show_header_toggle:false,entities:items.map(([key,name])=>({entity:this.sensor(key),name}))});
  window.loadCardHelpers().then(h=>{if(this._token!==token)return;
   const generator=entities('Wärmeerzeuger',[['typ','Typ'],['betriebsart','Betriebsart'],['brennerstatus','Brennerstatus'],['kesselsolltemperatur','Kesselsolltemperatur'],['kesseltemperatur','Kesseltemperatur'],['brenner','Brenner'],['modulationsgrad','Modulationsgrad'],['drehzahl_heizkreispumpe','Drehzahl Heizkreispumpe'],['speicherladepumpe','Speicherladepumpe'],['3_wege_ventil','3-Wege-Ventil'],['anlagendruck','Anlagendruck'],['aussentemperatur','Außentemperatur'],['rucklauftemperatur','Rücklauftemperatur'],['anzahl_brennerstarts','Brennerstarts'],['brennerbetriebsstunden','Brennerbetriebsstunden'],['netzbetriebsstunden','Netzbetriebsstunden']]);
   const allCards=c=>[c,...(c.cards||[]).flatMap(allCards)];
   const heat=allCards(config.area_cards[0]),water=allCards(config.area_cards[1]);
   const read=(key,name)=>({entity:this.sensor(key),name});
   const room=()=>({...read('raumtemperatur','Raumtemperatur'),optional_measurement:true});
   const areaCards=config.area_cards.map((area,index)=>index===0?{...area,cards:[...area.cards,{type:'custom:wolflink-reading',...room(),icon:'mdi:home-thermometer'}]}:area);
   const control=(entity,name,source)=>({entity,name,editable:true,popup:source?.cards});
   const popup=(cards,needle,name)=>{const c=cards.find(c=>c.type==='custom:wolflink-mode-popup'&&(c.wolf_role||c.entity)?.includes(needle))||cards.find(c=>(c.wolf_role||c.entity)?.includes(needle)&&!c.entity.startsWith('button.'));return control(c?.entity,name,c);};
   const heatTable={type:'custom:wolflink-portal-table',sections:[
    {name:'Gemeinsame Einstellungen',rows:[control(heat.find(c=>c.type==='custom:wolflink-smartset-dial')?.entity,'Sollwertkorrektur'),control(heat.find(c=>c.entity?.startsWith('select.')&&c.type==='custom:wolflink-write-status')?.entity,'Programmwahl')]},
    {name:'Direkter Heizkreis',rows:[popup(heat,'partymodus','Partymodus'),popup(heat,'urlaubsmodus','Urlaubsmodus'),read('gemittelte_aussentemperatur','Gemittelte Außentemperatur'),room(),read('vorlauftemperatur','Vorlauftemperatur'),read('anforderung_heizkreis','Anforderung Heizkreis'),read('heizkreis_status','Heizkreis-Status'),popup(heat,'tagtemperatur','Tagtemperatur'),popup(heat,'heizungszeitprogramm','Zeitprogramm')]},
    {name:'Wärmeerzeuger 1',rows:generator.entities}
   ]};
   const waterTable={type:'custom:wolflink-portal-table',sections:[
    {name:'Gemeinsame Einstellungen',rows:[control(water.find(c=>c.type==='custom:wolflink-smartset-dial')?.entity,'Warmwassersolltemperatur eingestellt'),control(water.find(c=>c.entity?.startsWith('select.')&&c.type==='custom:wolflink-write-status')?.entity,'Programmwahl')]},
    {name:'Warmwasser',rows:[popup(water,'1x_warmwasser','1x Warmwasser'),read('warmwasser_status','Warmwasser-Status'),popup(water,'warmwasserzeitprogramm','Zeitprogramm'),read('warmwassersolltemperatur','Warmwassersolltemperatur'),read('warmwassertemperatur','Warmwassertemperatur'),read('auslauftemperatur_warmwasser','Auslauftemperatur Warmwasser'),read('durchfluss_warmwasser','Durchfluss Warmwasser')]}
   ]};
   const energyTable={type:'custom:wolflink-energy-periods',groups:[
    {title:'Tagesvergleich',periods:[['Gestern','gestern'],['Heute · bisher','heute']].map(([name,key])=>({name,consumption_entity:this.sensor('energie_verbrauch_'+key),heat_entity:this.sensor('energie_waerme_'+key)}))},
    {title:'Jahresvergleich',periods:[['Vorvorjahr','vorvorjahr'],['Vorjahr','vorjahr'],['Dieses Jahr · bisher','jahr']].map(([name,key])=>({name,consumption_entity:this.sensor('energie_verbrauch_'+key),heat_entity:this.sensor('energie_waerme_'+key)}))}
   ]};
   const deviceSections=[{name:'Heizgerät',rows:[read('typ','Typ'),read('geraet_firmware_heizung','Firmware'),read('geraet_netzstarts','Anzahl Netzstarts')]},{name:'Bedienmodul BM-2',rows:[read('geraet_firmware_bm2','Firmware')]}];
   const available={Bedienung:{type:'custom:wolflink-area-layout',cards:areaCards},Übersicht:{type:'custom:wolflink-portal-table',layout:'overview',sections:[{name:'Anlagenstatus',rows:[read('betriebsart','Betriebsart'),read('brennerstatus','Brennerstatus'),read('heizkreis_status','Heizkreis'),read('warmwasser_status','Warmwasser'),read('anlagendruck','Anlagendruck'),room()]},...deviceSections]},Heizung:heatTable,Warmwasser:waterTable,Energiestatistik:{type:'custom:wolflink-area-layout',cards:[{type:'custom:wolflink-energy-overview',heating_entity:this.sensor('energie_heizung'),water_entity:this.sensor('energie_warmwasser')},energyTable]}};
   const definitions=this._labels.map(label=>available[label]);
   this._cards=definitions.map((def,i)=>{const card=h.createCardElement(def);if(this._hass)card.hass=this._hass;(i===1?this._panels[i].querySelector('.status-content'):this._panels[i]).append(card);return card;});this.updateLive();
  });this.select(this._active);
 }
 sensor(key){return this.config.sensors ? (this.config.sensors[key]||'sensor.wolflink_local_missing') : 'sensor.wolflink_'+key;}
 select(label){this._active=label;const labels=this._labels;this.shadowRoot.querySelectorAll('[role=tab]').forEach((b,i)=>{b.setAttribute('aria-selected',String(labels[i]===label));b.tabIndex=labels[i]===label?0:-1;b.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const next=(i+(e.key==='ArrowRight'?1:labels.length-1))%labels.length;this.select(labels[next]);this.shadowRoot.querySelectorAll('[role=tab]')[next].focus();}};});this._panels.forEach((p,i)=>p.hidden=labels[i]!==label);}
 updateLive(){this.shadowRoot.querySelectorAll('[data-device]').forEach(el=>{const value=this._hass?.states[this.sensor(el.dataset.device)]?.state?.toLowerCase();el.dataset.active=['ein','on','1','true'].includes(value)?'true':'false';el.dataset.known=value&&!['unknown','unavailable'].includes(value)?'true':'false';});this.shadowRoot.querySelectorAll('[data-live]').forEach(el=>{const s=this._hass?.states[this.sensor(el.dataset.live)];el.textContent=!s||['unknown','unavailable'].includes(s.state)?'Nicht verfügbar':(/^[-+]?\d+(\.\d+)?$/.test(s.state)?Number(s.state).toLocaleString('de-DE',{maximumFractionDigits:2}):s.state)+(s.attributes.unit_of_measurement?' '+s.attributes.unit_of_measurement:'');});}
 set hass(value){this._hass=value;this._cards?.forEach(c=>c.hass=value);this.updateLive();}
 getGridOptions(){return{columns:24,rows:'auto'};}
 disconnectedCallback(){this._overviewQuery?.removeEventListener('change',this._overviewResize);}
 connectedCallback(){if(this._overviewResize)this._overviewQuery?.addEventListener('change',this._overviewResize);}
 getCardSize(){return 16;}
}
if(!customElements.get('wolflink-plant-dashboard'))customElements.define('wolflink-plant-dashboard',WolfLinkPlantDashboard);

// Independently drawn functional diagram; no manufacturer artwork.
const WOLF_FUNCTIONAL_SVG = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 900 500\" role=\"img\" aria-label=\"Eigenes technisches Funktionsschema: Warmwasserspeicher links, Wärmeerzeuger mittig und Heizkreis rechts\">\n<defs><linearGradient id=\"t74-case\" x2=\"0\" y2=\"1\"><stop stop-color=\"#f7f9fc\"/><stop offset=\"1\" stop-color=\"#e3e9f0\"/></linearGradient><linearGradient id=\"t74-store\" x2=\"0\" y2=\"1\"><stop stop-color=\"#edb5ba\"/><stop offset=\".5\" stop-color=\"#f4ecee\"/><stop offset=\"1\" stop-color=\"#bbdbe9\"/></linearGradient><linearGradient id=\"t74-exchanger\"><stop stop-color=\"#d45d6c\"/><stop offset=\".5\" stop-color=\"#b995ac\"/><stop offset=\"1\" stop-color=\"#659dbb\"/></linearGradient><linearGradient id=\"t74-heating-flow\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#ca5264\"/><stop offset=\".5\" stop-color=\"#ab7b99\"/><stop offset=\"1\" stop-color=\"#548eaf\"/></linearGradient></defs>\n<style>.case{fill:url(#t74-case);stroke:#8798a9;stroke-width:1.6}.hot{fill:none;stroke:#ca5264;stroke-width:5;stroke-linejoin:round;stroke-linecap:round}.cold{fill:none;stroke:#548eaf;stroke-width:5;stroke-linejoin:round;stroke-linecap:round}.thin{fill:none;stroke:#8798a9;stroke-width:1.3}.label{font:12px Arial,sans-serif;fill:#52677a}.title{font:600 15px Arial,sans-serif;fill:#294158}.value{font:600 16px Arial,sans-serif;fill:#20384e}.small{font:11px Arial,sans-serif;fill:#52677a}.pump{fill:#fff;stroke:#72889b;stroke-width:2}.pump[data-active=\"true\"]{stroke:#46a16d;stroke-width:3}.pump[data-known=\"false\"]{stroke-dasharray:3 3}.burner[data-active=\"false\"]{opacity:.3;filter:grayscale(1)}.burner[data-known=\"false\"]{opacity:.2}</style>\n<!-- Functional connections: illustrative pipe routing, not a hydraulic installation plan. -->\n<path class=\"hot\" d=\"M92 420H832M676 420V116Q676 100 692 100H704\"/>\n<path class=\"cold\" d=\"M92 450H832M796 100H806Q822 100 822 116V450\"/>\n<!-- Storage cylinder and its load circuit. -->\n<text class=\"title\" x=\"52\" y=\"63\">Warmwasserspeicher</text>\n<rect x=\"70\" y=\"150\" width=\"112\" height=\"197\" rx=\"25\" fill=\"url(#t74-store)\" stroke=\"#8798a9\" stroke-width=\"1.6\"/>\n<ellipse cx=\"126\" cy=\"166\" rx=\"45\" ry=\"10\" class=\"thin\"/>\n<path class=\"hot\" d=\"M182 203H325\"/><path class=\"cold\" d=\"M182 306H325\"/>\n<path d=\"M182 203H166V195H91v22h66v22H95v22h62v22H95v23h87\" fill=\"none\" stroke=\"#fff\" stroke-width=\"7\" stroke-linejoin=\"round\" opacity=\".9\"/>\n<circle cx=\"235\" cy=\"203\" r=\"15\" class=\"pump\" data-device=\"speicherladepumpe\"/><path d=\"M241 193l-14 10 14 10z\" fill=\"#72889b\"/>\n<text class=\"small\" x=\"235\" y=\"179\" text-anchor=\"middle\">Ladepumpe</text>\n<circle cx=\"182\" cy=\"266\" r=\"5\" fill=\"#fff\" stroke=\"#8798a9\"/><path class=\"thin\" d=\"M182 266H190\"/>\n<text class=\"small\" x=\"200\" y=\"254\">Speichertemperatur</text><text class=\"value\" x=\"200\" y=\"275\" data-live=\"warmwassertemperatur\"/>\n<g transform=\"translate(45 88)\" aria-label=\"Warmwasserhahn\"><path d=\"M0 27V15H19Q28 15 28 24V28H20V24Q20 22 17 22H8V27Z\" fill=\"#dce7ee\" stroke=\"#71899d\" stroke-width=\"1.6\" stroke-linejoin=\"round\"/><path d=\"M6 15V7M0 7H13\" fill=\"none\" stroke=\"#71899d\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><path d=\"M24 32C24 32 20 37 20 39C20 44 28 44 28 39C28 37 24 32 24 32Z\" fill=\"#ca5264\"/></g>\n<text class=\"small\" x=\"88\" y=\"101\">Warmwasser-Auslauf</text><text class=\"value\" x=\"88\" y=\"122\" data-live=\"auslauftemperatur_warmwasser\"/>\n<!-- Exhaust outlet: schematic, no measured exhaust flow. -->\n<path d=\"M474 65V31Q474 19 486 19H540\" fill=\"none\" stroke=\"#8c9aa7\" stroke-width=\"17\" stroke-linecap=\"butt\" stroke-linejoin=\"round\"/>\n<path d=\"M474 65V31Q474 19 486 19H540\" fill=\"none\" stroke=\"#e5ebf0\" stroke-width=\"11\" stroke-linecap=\"butt\" stroke-linejoin=\"round\"/>\n<path d=\"M537 10V28M468 48H480\" stroke=\"#7c8d9d\" stroke-width=\"2\"/>\n<path class=\"thin\" d=\"M512 19H545V28H550\"/><circle cx=\"512\" cy=\"19\" r=\"4\" fill=\"#fff\" stroke=\"#8798a9\"/>\n<text class=\"small\" x=\"560\" y=\"21\">Abgastemperatur</text><text class=\"value\" x=\"560\" y=\"43\" data-live=\"agf_abgasfuhler\"/>\n<!-- Boiler: independent symbols and geometry. -->\n<rect class=\"case\" x=\"325\" y=\"65\" width=\"265\" height=\"282\" rx=\"14\"/>\n<text class=\"title\" x=\"343\" y=\"92\">Wärmeerzeuger</text><text class=\"small\" x=\"343\" y=\"110\">Brennwertgerät</text>\n<!-- Draw continuous internal pipes above the casing and below component symbols. -->\n<path class=\"hot\" d=\"M430 183V420M325 203H355V238M390 251H430\"/>\n<path class=\"cold\" d=\"M527 183V450M325 306H365V303M390 289H527\"/>\n<rect x=\"414\" y=\"140\" width=\"120\" height=\"43\" rx=\"5\" fill=\"url(#t74-exchanger)\" stroke=\"#8798a9\"/>\n<path d=\"M430 145l-8 33m24-33-8 33m24-33-8 33m24-33-8 33m24-33-8 33m24-33-8 33\" stroke=\"#ffffff\" stroke-width=\"2\" opacity=\".65\"/>\n<g class=\"burner\" data-device=\"brenner\" transform=\"translate(450 185) scale(2.05)\"><path fill=\"#e98943\" d=\"M17.66 11.2C17.43 10.9 17.15 10.64 16.89 10.38C16.22 9.78 15.46 9.35 14.82 8.72C13.33 7.26 13 4.85 13.95 3C13 3.23 12.17 3.75 11.46 4.32C8.87 6.4 7.85 10.07 9.07 13.22C9.11 13.32 9.15 13.42 9.15 13.55C9.15 13.77 9 13.97 8.8 14.05C8.57 14.15 8.33 14.09 8.14 13.93C8.08 13.88 8.04 13.83 8 13.76C6.87 12.33 6.69 10.28 7.45 8.64C5.78 10 4.87 12.3 5 14.47C5.06 14.97 5.12 15.47 5.29 15.97C5.43 16.57 5.7 17.17 6 17.7C7.08 19.43 8.95 20.67 10.96 20.92C13.1 21.19 15.39 20.8 17.03 19.32C18.86 17.66 19.5 15 18.56 12.72L18.43 12.46C18.22 12 17.66 11.2 17.66 11.2M14.5 17.5C14.22 17.74 13.76 18 13.4 18.1C12.28 18.5 11.16 17.94 10.5 17.28C11.69 17 12.4 16.12 12.61 15.23C12.78 14.43 12.46 13.77 12.33 13C12.21 12.26 12.23 11.63 12.5 10.94C12.69 11.32 12.89 11.7 13.13 12C13.9 13 15.11 13.44 15.37 14.8C15.41 14.94 15.43 15.08 15.43 15.23C15.46 16.05 15.1 16.95 14.5 17.5H14.5Z\"/></g>\n<text class=\"small\" x=\"462\" y=\"251\">Brenner</text>\n<!-- Functional plate exchanger for the storage load circuit. -->\n<rect x=\"350\" y=\"238\" width=\"40\" height=\"65\" rx=\"4\" fill=\"url(#t74-exchanger)\" stroke=\"#8798a9\"/>\n<path d=\"M360 243l-5 55m15-55-5 55m15-55-5 55\" stroke=\"#fff\" stroke-width=\"2\" opacity=\".7\"/>\n\n<g transform=\"translate(430 251)\"><circle r=\"12\" fill=\"#fff\" stroke=\"#8798a9\"/><path d=\"M0 0l-8-6v12zM0 0l8-6v12zM0 0l-6 8H6z\" fill=\"#72889b\"/></g><text class=\"small\" x=\"444\" y=\"268\">Umschaltventil</text>\n<circle class=\"pump\" cx=\"527\" cy=\"306\" r=\"16\" data-device=\"zhp_heizkreispumpe\"/><path d=\"M517 312l10-18 10 18z\" fill=\"#72889b\"/>\n<text class=\"small\" x=\"548\" y=\"319\">Heizkreispumpe</text>\n<!-- Sensors: tagged to the functional measurement locations. -->\n<path class=\"thin\" d=\"M414 158H393V126H310\"/><circle cx=\"414\" cy=\"158\" r=\"4\" fill=\"#fff\" stroke=\"#8798a9\"/>\n<text class=\"small\" x=\"240\" y=\"102\">Kessel</text><text class=\"value\" x=\"240\" y=\"123\" data-live=\"kesseltemperatur\"/>\n<path class=\"thin\" d=\"M527 212H600\"/><circle cx=\"527\" cy=\"212\" r=\"4\" fill=\"#fff\" stroke=\"#8798a9\"/>\n<text class=\"small\" x=\"610\" y=\"207\">Rücklauf</text><text class=\"value\" x=\"610\" y=\"229\" data-live=\"rucklauftemperatur\"/>\n<text class=\"label\" x=\"345\" y=\"368\">Anlagendruck</text><text class=\"value\" x=\"345\" y=\"391\" data-live=\"anlagendruck\"/>\n\n<!-- External heating circuit. -->\n<text class=\"title\" x=\"670\" y=\"63\">Heizkreis</text>\n<rect x=\"704\" y=\"78\" width=\"92\" height=\"44\" rx=\"5\" fill=\"#f1f5f8\" stroke=\"#8798a9\"/><path d=\"M714 85v30m14-30v30m14-30v30m14-30v30m14-30v30m14-30v30\" stroke=\"url(#t74-heating-flow)\" stroke-width=\"4\"/>\n<path class=\"thin\" d=\"M676 158H713\"/><circle cx=\"676\" cy=\"158\" r=\"4\" fill=\"#fff\" stroke=\"#8798a9\"/>\n<text class=\"small\" x=\"720\" y=\"160\">Vorlauf</text><text class=\"value\" x=\"720\" y=\"182\" data-live=\"vorlauftemperatur\"/>\n<path d=\"M767 59C751 59 744 43 755 32C750 18 765 8 778 14C786 1 807 0 818 12C832 3 850 8 854 21C869 13 889 21 889 35C904 43 895 59 880 59Z\" fill=\"#eef5f9\" stroke=\"#a4bacb\" stroke-width=\"1.4\"/>\n<text class=\"label\" x=\"823\" y=\"29\" text-anchor=\"middle\">Außentemperatur</text><text class=\"value\" x=\"823\" y=\"49\" text-anchor=\"middle\" data-live=\"aussentemperatur\"/>\n<text class=\"small\" x=\"702\" y=\"371\">Heizkreis-Zustand</text><text class=\"small\" x=\"702\" y=\"390\" data-live=\"heizkreis_status\"/>\n\n<!-- Arrowheads show the schematic operating direction, not measured flow. -->\n<g fill=\"#ca5264\"><path d=\"M430 383l-7-12h14z\"/><path d=\"M676 315l-7 12h14z\"/><path d=\"M297 203l12-7v14z\"/><path d=\"M402 251l12-7v14z\"/><path d=\"M610 420l-12-7v14z\"/></g>\n<g fill=\"#548eaf\"><path d=\"M527 355l-7 12h14z\"/><path d=\"M822 324l-7-12h14z\"/><path d=\"M270 306l-12-7v14z\"/><path d=\"M470 289l-12-7v14z\"/><path d=\"M610 450l12-7v14z\"/></g>\n<g fill=\"#ca5264\" stroke=\"#fff\" stroke-width=\"1\"><circle cx=\"430\" cy=\"420\" r=\"4\"/><circle cx=\"676\" cy=\"420\" r=\"4\"/></g>\n<g fill=\"#548eaf\" stroke=\"#fff\" stroke-width=\"1\"><circle cx=\"527\" cy=\"450\" r=\"4\"/><circle cx=\"822\" cy=\"450\" r=\"4\"/></g>\n<text class=\"small\" x=\"100\" y=\"413\">Vorlauf</text><text class=\"small\" x=\"100\" y=\"473\">Rücklauf</text>\n<text class=\"small\" x=\"450\" y=\"496\" text-anchor=\"middle\">Funktionsschema · Pfeile: schematische Richtung, kein gemessener Durchfluss</text>\n</svg>";
function wolfPortalPlantSvg(){return WOLF_FUNCTIONAL_SVG;}

/* Compact portal-style readout; settings open existing HA/entity dialogs. */
class WolfLinkPortalTable extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._rows=[];}
 setConfig(config){this.config=config;this._rows=[];
  this.shadowRoot.innerHTML=`<style>:host{display:block;container-type:inline-size}ha-card{overflow:hidden;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color)}h3{font-size:14px;font-weight:600;margin:0;padding:9px 14px;background:#666;color:#fff}.row{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr) 95px;align-items:center;gap:12px;padding:5px 18px;min-height:32px;box-sizing:border-box;font-size:13px}.row:nth-child(even){background:color-mix(in srgb,var(--card-background-color) 96%,var(--primary-text-color) 4%)}.name{color:var(--secondary-text-color);overflow-wrap:anywhere;min-width:0}.value{display:flex;align-items:center;gap:8px;min-width:0}.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-left:auto;background:#78909c}.dot[data-stage=reported],.dot[data-stage=confirmed]{background:#43a047}.dot[data-stage=awaiting_confirmation],.dot[data-stage=awaiting_period_confirmation]{background:#f9a825}.dot[data-stage=sending]{background:#2196f3}.dot[data-stage=failed]{background:#e53935}button{font:inherit;font-size:12px;padding:4px 8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:4px;cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible{outline:2px solid var(--primary-color)}@media(max-width:500px){.row{grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 65px;padding:8px;gap:6px;font-size:12px}button{padding:4px;font-size:11px}}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){ha-card.multi{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px;padding:8px}ha-card.multi section{min-width:0}ha-card.heating section:nth-child(3){grid-column:2;grid-row:1/3}ha-card.heating section:nth-child(-n+2){grid-column:1}h3{font-size:13px;padding:6px 10px}.row{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr) 62px;gap:6px;padding:3px 8px;min-height:26px;font-size:12px;line-height:18px}.row:not(:has(button))>:last-child{visibility:hidden}.row:has(button){min-height:44px}button{min-height:44px;font-size:11px;padding:3px 6px}.value{overflow-wrap:anywhere}}@container(min-width:680px){ha-card.overview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px;padding:8px;align-items:start}ha-card.overview section{min-width:0}ha-card.overview section:nth-child(1){grid-column:1;grid-row:1/3}ha-card.overview section:nth-child(2){grid-column:2;grid-row:1}ha-card.overview section:nth-child(3){grid-column:2;grid-row:2}}</style><ha-card></ha-card>`;
  const card=this.shadowRoot.querySelector('ha-card');card.classList.toggle('multi',config.sections.length>1);card.classList.toggle('heating',config.sections.length===3&&config.layout!=='overview');card.classList.toggle('overview',config.layout==='overview');
  for(const section of config.sections){const group=document.createElement('section'),heading=document.createElement('h3');heading.textContent=section.name;group.append(heading);
   for(const row of section.rows){const el=document.createElement('div');el.className='row';const name=document.createElement('div');name.className='name';name.textContent=row.name;const value=document.createElement('div');value.className='value';const text=document.createElement('span');value.append(text);let dot,button;
    if(row.editable){dot=document.createElement('span');dot.className='dot';value.append(dot);button=document.createElement('button');button.textContent=row.popup?'Öffnen':'Ändern';button.setAttribute('aria-label',row.name+' '+button.textContent);button.onclick=()=>this.open(row);}
    el.append(name,value,button||document.createElement('span'));group.append(el);this._rows.push({row,text,dot,button,el});
   }card.append(group);
  }this.update();
 }
 open(row){if(!this._hass||!row.entity)return;
  if(!row.popup&&row.entity.startsWith('select.')){wolfOpenChoice(this,row.entity,row.name);return;}
  if(row.popup){this.dispatchEvent(new CustomEvent('show-dialog',{bubbles:true,composed:true,detail:{dialogTag:'wolflink-mode-dialog',dialogImport:()=>Promise.resolve(),dialogParams:{title:row.name,cards:row.popup,hass:this._hass,owner:this}}}));}
  else this.dispatchEvent(new CustomEvent('hass-more-info',{bubbles:true,composed:true,detail:{entityId:row.entity}}));
 }
 update(){for(const item of this._rows){const state=this._hass?.states[item.row.entity];if(item.el&&item.row.optional_measurement)item.el.style.display=wolfValidOptionalMeasurement(state)?'':'none';item.text.textContent=state?this._hass.formatEntityState(state):'Nicht verfügbar';if(item.dot){const stage=wolfWriteStage(state);item.dot.dataset.stage=stage;item.dot.title=WOLF_WRITE_LABELS[stage]||'Nicht verfügbar';item.dot.setAttribute('role','img');item.dot.setAttribute('aria-label',item.dot.title);}if(item.button)item.button.disabled=!state||(!item.row.popup&&state.attributes.read_only===true);}}
 set hass(hass){this._hass=hass;this.update();if(this._dialog)this._dialog.hass=hass;}
 getCardSize(){return 12;}
}
if(!customElements.get('wolflink-portal-table'))customElements.define('wolflink-portal-table',WolfLinkPortalTable);

/* Read-only energy split, calculated only from valid device counters. */
class WolfLinkEnergyOverview extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});}
 setConfig(config){this.config=config;this.render();}
 energy(){
  const read=id=>{const state=this._hass?.states[id];if(!state||!/^\d+(\.\d+)?$/.test(state.state)||state.attributes.unit_of_measurement!=='kWh')return null;const value=Number(state.state);return Number.isFinite(value)?value:null;};
  const heating=read(this.config.heating_entity),water=read(this.config.water_entity);
  const total=heating!==null&&water!==null?heating+water:null;
  return {heating,water,total,heatingPercent:total>0?heating/total*100:null,waterPercent:total>0?water/total*100:null};
 }
 render(){if(!this.config)return;const e=this.energy(),num=(v,d=1)=>v===null?'Nicht verfügbar':v.toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d}),valid=e.heatingPercent!==null;
  this.shadowRoot.innerHTML=`<style>:host{display:block}ha-card{padding:22px 20px;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;color:var(--primary-text-color)}h2{font-size:18px;margin:0 0 22px}.chart{width:min(240px,68vw);aspect-ratio:1;border-radius:50%;margin:0 auto 22px;background:${valid?`conic-gradient(#d95355 ${e.heatingPercent}%,#a2cbd5 0)`:'var(--divider-color)'};position:relative}.chart:after{content:'';position:absolute;inset:23%;border-radius:50%;background:var(--card-background-color)}.total{text-align:center;font-size:38px;font-weight:600;line-height:1.2}.unit{font-size:18px;font-weight:500}.caption{text-align:center;color:var(--secondary-text-color);font-size:13px;margin:6px 0 20px}.rows{max-width:440px;margin:auto}.row{display:flex;align-items:center;gap:10px;padding:12px 0;font-size:14px}.row+.row{border-top:1px solid var(--divider-color)}.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}.heat{background:#d95355}.water{background:#a2cbd5}.value{margin-left:auto;text-align:right;font-variant-numeric:tabular-nums}.percent{font-size:12px;color:var(--secondary-text-color);margin-left:6px}.empty{text-align:center;color:var(--secondary-text-color);font-size:12px;margin-bottom:16px}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){ha-card{padding:14px}h2{font-size:16px;margin-bottom:12px}.chart{width:clamp(130px,calc(100dvh - 480px),200px);margin-bottom:12px}.total{font-size:30px}.caption{margin:4px 0 10px;font-size:12px}.row{padding:8px 0;font-size:12px}.percent{font-size:11px}}</style><ha-card><h2>Energiemenge</h2><div class="chart" role="img" aria-label="${valid?`Heizung ${num(e.heatingPercent)} Prozent, Warmwasser ${num(e.waterPercent)} Prozent`:'Keine prozentuale Aufteilung verfügbar'}"></div><div class="total">${e.total===null?'—':num(e.total/1000)} <span class="unit">MWh</span></div><div class="caption">Energiemenge seit Inbetriebnahme</div>${!valid?'<div class="empty">'+(e.total===0?'Noch keine Energiemenge erfasst.':'Aufteilung derzeit nicht verfügbar.')+'</div>':''}<div class="rows"><div class="row"><span class="dot heat"></span><span>Heizung</span><span class="value">${num(e.heating,0)}${e.heating!==null?' kWh':''}<span class="percent">${valid?num(e.heatingPercent)+' %':''}</span></span></div><div class="row"><span class="dot water"></span><span>Warmwasser</span><span class="value">${num(e.water,0)}${e.water!==null?' kWh':''}<span class="percent">${valid?num(e.waterPercent)+' %':''}</span></span></div></div></ha-card>`;
 }
 set hass(value){this._hass=value;this.render();}
 getCardSize(){return 6;}
}
if(!customElements.get('wolflink-energy-overview'))customElements.define('wolflink-energy-overview',WolfLinkEnergyOverview);

/* Separate scales keep daily and annual device counters comparable within a group. */
class WolfLinkEnergyPeriods extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});}
 setConfig(config){this.config=config;this.render();}
 groups(){
  const read=id=>{const s=this._hass?.states[id];if(!s||s.attributes.unit_of_measurement!=='kWh'||!/^\d+(\.\d+)?$/.test(s.state))return null;const n=Number(s.state);return Number.isFinite(n)?n:null;};
  return (this.config.groups||[]).map(g=>{const periods=g.periods.map(p=>({...p,consumption:read(p.consumption_entity),heat:read(p.heat_entity)}));return {...g,periods,max:Math.max(0,...periods.flatMap(p=>[p.consumption??0,p.heat??0]))};});
 }
 render(){if(!this.config)return;
  const fmt=n=>n===null?'Nicht verfügbar':n.toLocaleString('de-DE',{maximumFractionDigits:2})+' kWh';
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  this.shadowRoot.innerHTML=`<style>:host{display:block}ha-card{padding:20px;border:1px solid var(--divider-color);border-radius:12px;color:var(--primary-text-color);background:var(--card-background-color)}h2{font-size:18px;margin:0 0 14px}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;margin-bottom:20px;color:var(--secondary-text-color)}.key{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}.consumption{background:#d95355}.heat{background:#579eae}.group+.group{border-top:1px solid var(--divider-color);padding-top:20px;margin-top:22px}h3{font-size:15px;margin:0 0 16px}.period{margin:0 0 18px}.name{font-size:13px;margin-bottom:7px}.barrow{display:grid;grid-template-columns:minmax(0,1fr) 116px;gap:12px;align-items:center;margin:6px 0}.track{height:12px;border-radius:4px;background:var(--secondary-background-color);overflow:hidden}.bar{height:100%;border-radius:4px}.value{font-size:12px;text-align:right;font-variant-numeric:tabular-nums}.note{font-size:12px;line-height:1.5;color:var(--secondary-text-color);margin:14px 0 0}@media(max-width:400px){ha-card{padding:14px}.barrow{grid-template-columns:minmax(0,1fr) 100px;gap:8px}}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){ha-card{padding:12px}h2{font-size:16px;line-height:20px;margin-bottom:8px}.legend{font-size:11px;line-height:14px;gap:8px;margin-bottom:8px}.group+.group{padding-top:8px;margin-top:8px}h3{font-size:13px;line-height:16px;margin-bottom:6px}.period{margin-bottom:6px}.name{font-size:12px;line-height:16px;margin-bottom:2px}.barrow{margin:2px 0;line-height:13px;grid-template-columns:minmax(0,1fr) 94px}.track{height:8px}.value{font-size:11px;line-height:13px}.note{font-size:11px}.notes{margin-top:10px;font-size:12px}.notes summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--secondary-text-color)}}</style><ha-card><h2>Energiemengen im Vergleich</h2><div class="legend"><span><i class="key consumption"></i>Berechneter Gasverbrauch</span><span><i class="key heat"></i>Berechnete Wärmemenge</span></div>${this.groups().map(g=>`<section class="group"><h3>${escape(g.title)}</h3>${g.periods.map(p=>`<div class="period"><div class="name">${escape(p.name)}</div>${[['consumption','Berechneter Gasverbrauch'],['heat','Berechnete Wärmemenge']].map(([key,label])=>`<div class="barrow" role="img" aria-label="${escape(p.name+': '+label+' '+fmt(p[key]))}"><div class="track"><div class="bar ${key}" style="width:${p[key]!==null&&g.max>0?p[key]/g.max*100:0}%"></div></div><span class="value">${fmt(p[key])}</span></div>`).join('')}</div>`).join('')}</section>`).join('')}<details class="notes"><summary>Hinweise zu den Energiewerten ⓘ</summary><p class="note">Eigene Skala je Vergleich. Heute und dieses Jahr sind noch nicht abgeschlossen. Laut WOLF werden Gasverbrauch und Wärmemenge aus Brennerlaufzeit und Gerätedaten berechnet; es sind keine Zählermessungen. Jahreszeitraum: 1. Januar bis 31. Dezember. Die Werte dieser Anlage sind noch nicht am BM-2 gegengeprüft (Anzeige → Heizgerät).</p></details></ha-card>`;
 }
 set hass(value){this._hass=value;this.render();}
 getCardSize(){return 8;}
}
if(!customElements.get('wolflink-energy-periods'))customElements.define('wolflink-energy-periods',WolfLinkEnergyPeriods);

/* Size columns by available card space rather than browser viewport width. */
function wolfViewportLayout(width,height,top){
 const sideBySide=width>=680;
 const available=Math.max(0,height-Math.max(0,top)-24);
 return {sideBySide,available,dial:Math.round(Math.max(200,Math.min(330,available-420)))};
}
class WolfLinkAreaLayout extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._cards=[];}
 setConfig(config){
  const token={};this._token=token;
  this.shadowRoot.innerHTML=`<style>:host{display:block;min-width:0}.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px;align-items:start}.areas>*{min-width:0}</style><div class="areas"></div>`;
  this._cards=[];
  this._adaptive=config.cards.every(card=>card.type==='custom:wolflink-area-card');
  window.loadCardHelpers().then(h=>{if(this._token!==token)return;this._cards=config.cards.map(def=>{const card=h.createCardElement(def);if(this._hass)card.hass=this._hass;this.shadowRoot.querySelector('.areas').append(card);return card;});});
 }
 set hass(value){this._hass=value;this._cards.forEach(card=>card.hass=value);}
 connectedCallback(){
  if(!this._resize){this._resize=()=>{if(!this._adaptive)return;const box=this.getBoundingClientRect();if(!box.width)return;const layout=wolfViewportLayout(box.width,window.visualViewport?.height||window.innerHeight,box.top);this.style.setProperty('--wolf-dial-size',layout.dial+'px');this.style.setProperty('--wolf-area-columns',layout.sideBySide?'repeat(2,minmax(0,1fr))':'minmax(0,1fr)');this.style.setProperty('--wolf-control-font','14px');this.style.setProperty('--wolf-control-value-font','13px');};}
  this._observer=new ResizeObserver(this._resize);this._observer.observe(this);window.addEventListener('resize',this._resize);window.visualViewport?.addEventListener('resize',this._resize);this._resize();
 }
 disconnectedCallback(){this._observer?.disconnect();window.removeEventListener('resize',this._resize);window.visualViewport?.removeEventListener('resize',this._resize);}
 getCardSize(){return 16;}
}
if(!customElements.get('wolflink-area-layout'))customElements.define('wolflink-area-layout',WolfLinkAreaLayout);

/* Plain read-only measurement rows preserve the entity details action. */
class WolfLinkReading extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});}
 setConfig(config){this.config=config;this.shadowRoot.innerHTML=`<style>:host{display:block;min-width:0}button{display:flex;align-items:center;width:100%;min-height:56px;box-sizing:border-box;padding:8px 12px;gap:10px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);color:var(--primary-text-color);text-align:left;font:inherit;cursor:pointer}ha-icon{color:var(--state-icon-color);--mdc-icon-size:22px;flex-shrink:0}.text{min-width:0}.name{font-size:14px}.value{font-size:12px;color:var(--secondary-text-color)}.name,.value{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}button:focus-visible{outline:2px solid var(--primary-color)}@media(min-width:900px) and (max-width:1400px) and (max-height:1100px) and (orientation:landscape){button{min-height:44px;padding:4px 8px;gap:7px;line-height:16px}.name{font-size:12px}.value{font-size:11px}ha-icon{--mdc-icon-size:20px}}button{min-height:48px;padding:6px 10px;gap:8px}.name{font-size:var(--wolf-control-font,14px)}.value{font-size:var(--wolf-control-value-font,13px)}</style><button><ha-icon></ha-icon><div class="text"><div class="name"></div><div class="value"></div></div></button>`;this.shadowRoot.querySelector('.name').textContent=config.name||'';this.shadowRoot.querySelector('button').onclick=()=>this.dispatchEvent(new CustomEvent('hass-more-info',{bubbles:true,composed:true,detail:{entityId:config.entity}}));this.update();}
 update(){if(!this.config)return;const state=this._hass?.states[this.config.entity];if(this.config.optional_measurement)this.style.display=wolfValidOptionalMeasurement(state)?'':'none';this.shadowRoot.querySelector('.value').textContent=state?this._hass.formatEntityState(state):'Nicht verfügbar';this.shadowRoot.querySelector('ha-icon').icon=this.config.icon||state?.attributes.icon||(this.config.entity.includes('temperatur')?'mdi:thermometer':'mdi:eye');this.shadowRoot.querySelector('button').title=(this.config.name||'')+': '+this.shadowRoot.querySelector('.value').textContent;}
 set hass(value){this._hass=value;this.update();}
 getCardSize(){return 1;}
}
if(!customElements.get('wolflink-reading'))customElements.define('wolflink-reading',WolfLinkReading);
