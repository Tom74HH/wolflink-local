import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const timers=new Map();let timerId=0;const fakeTimeout=fn=>{timers.set(++timerId,fn);return timerId;};const fakeClear=id=>timers.delete(id);
const classes=new Map(); const testWindow={customCards:[],confirm:()=>false};
vm.runInNewContext(fs.readFileSync('custom_components/wolflink_local/frontend/wolflink-mode-popup.js','utf8'),{HTMLElement:class{},customElements:{get:k=>classes.get(k),define:(k,v)=>classes.set(k,v)},window:testWindow,Number,Math,setTimeout:fakeTimeout,clearTimeout:fakeClear,CustomEvent:class{constructor(type,options){this.type=type;Object.assign(this,options)}}});
const Dial=classes.get('wolflink-smartset-dial');
const viewportLayout=vm.runInNewContext('('+fs.readFileSync('custom_components/wolflink_local/frontend/wolflink-mode-popup.js','utf8').match(/function wolfViewportLayout\(width,height,top\)\{[\s\S]*?\n\}/)[0]+')');
assert.equal(viewportLayout(1000,850,220).sideBySide,true);
assert.equal(viewportLayout(390,850,220).sideBySide,false);
assert.ok(viewportLayout(1000,1200,220).dial>viewportLayout(1000,850,220).dial);
assert.equal(viewportLayout(1000,400,220).dial,200);
assert.ok(viewportLayout(1000,1200,600).dial<viewportLayout(1000,1200,100).dial);
console.log('Adaptive viewport: actual content width, remaining height and readable minimum passed');
const Choice=classes.get('wolflink-choice-dialog');
function choiceFixture(){const choice=Object.create(Choice.prototype),calls=[];choice.params={entity:'select.test',owner:{}};choice.params.owner._dialog=choice;choice.render=()=>{};choice.closeDialog=()=>{choice.params.owner._dialog=null;};choice._hass={states:{'select.test':{state:'Automatik',attributes:{options:['Automatik','Standby']}}},callService:async(...args)=>calls.push(args)};return {choice,calls};}
{
 const {choice,calls}=choiceFixture();await choice.choose('invalid');await choice.choose('Automatik');assert.equal(calls.length,0);
 await choice.choose('Standby');assert.equal(calls.length,1);assert.equal(calls[0][0],'select');assert.equal(calls[0][2].option,'Standby');assert.equal(choice._hass.states['select.test'].state,'Automatik');
}
for(const blocked of ['read_only','unavailable','busy']){const {choice,calls}=choiceFixture();if(blocked==='read_only')choice._hass.states['select.test'].attributes.read_only=true;else if(blocked==='busy')choice._busy=true;else choice._hass.states['select.test'].state='unavailable';await choice.choose('Standby');assert.equal(calls.length,0);}
{const {choice}=choiceFixture();choice._hass.callService=async()=>{throw new Error('Synthetic failure');};await choice.choose('Standby');assert.equal(choice._busy,false);assert.equal(choice._error,'Synthetic failure');}
console.log('Compact choices: valid options, unchanged selection, read-only, busy, unavailable and service errors passed');
{
 const choice=Object.create(Choice.prototype);let renders=0,events=0;const panel={open:true};
 choice.params={entity:'select.test',owner:{}};choice.params.owner._dialog=choice;
 choice.shadowRoot={querySelector:()=>panel,set innerHTML(value){renders++;}};choice.dispatchEvent=()=>{events++;};
 choice.closeDialog();assert.equal(panel.open,false);assert.equal(choice.params.owner._dialog,null);
 choice.hass={states:{'select.test':{state:'Standby',attributes:{options:['Standby']}}}};
 choice.hass={states:{'select.test':{state:'Automatik',attributes:{options:['Standby','Automatik']}}}};
 assert.equal(renders,0);assert.equal(panel.open,false);choice.closeDialog();assert.equal(events,1);
}
console.log('Closed choice dialog stays closed through later status updates');
function fixture(value=60,readonly=false){const calls=[];const dial=Object.create(Dial.prototype);dial.isConnected=true;dial.config={entity:'number.test'};dial.shadowRoot={querySelector:()=>({textContent:''})};dial.updateState=()=>{};dial._hass={states:{'number.test':{state:String(value),attributes:{min:25,max:65,step:1,read_only:readonly}}},callService:async(...args)=>calls.push(args)};return {dial,calls};}
let {dial,calls}=fixture();await dial.adjust(-1);await dial.adjust(-1);await dial.adjust(-1);assert.equal(calls.length,0);assert.equal(dial._draft,57);assert.equal(timers.size,1);await dial.flushDraft();assert.equal(calls.length,1);assert.equal(calls[0][2].value,57);assert.equal(dial._hass.states['number.test'].state,'60');
({dial,calls}=fixture(65));await dial.adjust(1);await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture(25));await dial.adjust(-1);await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture(60,true));await dial.adjust(1);await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture());dial._busy=true;await dial.adjust(1);assert.equal(calls.length,0);
({dial,calls}=fixture());dial._hass.callService=async()=>{throw new Error('Synthetic failure')};await dial.adjust(1);await dial.flushDraft();assert.equal(dial._busy,false);assert.equal(dial._submitted,null);
({dial,calls}=fixture());await dial.adjust(1);await dial.adjust(-1);await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture());await dial.adjust(1);dial._hass.states['number.test'].attributes.read_only=true;await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture());await dial.adjust(1);dial.disconnectedCallback();await dial.flushDraft();assert.equal(calls.length,0);
({dial,calls}=fixture(4));dial._hass.states['number.test'].attributes={min:-4,max:4,step:.5};for(let n=0;n<6;n++)await dial.adjust(-1);assert.equal(dial._draft,1);assert.equal(calls.length,0);await dial.flushDraft();assert.equal(calls[0][2].value,1);
console.log('Dial batching checks passed: final value only, half-degree steps, limits, read-only, cancellation, unchanged state, busy and errors');
const Schedule=classes.get('wolflink-schedule');const schedule=Object.create(Schedule.prototype);const requests=[];schedule.config={device_id:'synthetic-device',area:'heating'};schedule._program=2;schedule.render=()=>{};schedule._hass={callWS:async request=>{requests.push(request);return {response:{program:2,days:{monday:{status:'ok',windows:[{start:'04:30',end:'08:00'}]}}}}}};await schedule.load();assert.equal(requests[0].service,'get_time_program');assert.equal(requests[0].service_data.program,2);assert.equal(schedule._data.days.monday.windows[0].start,'04:30');assert.equal(schedule._loading,false);schedule._hass.callWS=async()=>{throw new Error('Synthetic offline')};await schedule.load();assert.equal(schedule._error,'Synthetic offline');assert.equal(schedule._loading,false);console.log('Schedule read request, returned windows and failure checks passed');


schedule._editing={weekday:'monday',expected:'baseline',windows:[{start:'06:00',end:'08:00'}]};const draft=schedule._editing;const previews=[];schedule._hass.callWS=async req=>{previews.push(req);return{response:{}}};await schedule.saveDay();assert.equal(previews.length,1);assert.equal(previews[0].service,'preview_time_program_day');assert.equal(schedule._editing,draft);assert.equal(schedule._saving,false);console.log('Cancelled save validates locally and sends no write');

// Copy targets are serialized; a pending target stops the remaining writes.
testWindow.confirm=()=>true;
function copyFixture(stage='confirmed',conflict=false){
 const x=Object.create(Schedule.prototype), calls=[]; x.config={device_id:'synthetic',area:'heating'};x._program=1;x.render=()=>{};x.load=async()=>{};
 const day={status:'ok',serialized:'baseline',windows:[{start:'04:30',end:'08:00'}]};
 x._data={days:Object.fromEntries(['monday','tuesday','wednesday'].map(k=>[k,{...day}]))};
 x._copyDraft={source:'monday',targets:new Set(['tuesday','wednesday'])};
 x._hass={callWS:async req=>{calls.push(req);if(req.service==='get_time_program')return {response:{days:conflict?{...x._data.days,tuesday:{serialized:'changed'}}:x._data.days}};return {response:{write_status:stage}}}};return {x,calls};
}
let copy=copyFixture();await copy.x.copyDays();assert.deepEqual(copy.calls.filter(r=>r.service==='write_time_program_day').map(r=>r.service_data.weekday),['tuesday','wednesday']);assert.equal(copy.x._copyDraft,null);
copy=copyFixture('awaiting_confirmation');await copy.x.copyDays();assert.equal(copy.calls.filter(r=>r.service==='write_time_program_day').length,1);assert.match(copy.x._error,/Bestätigung steht aus/);
copy=copyFixture('confirmed',true);await copy.x.copyDays();assert.equal(copy.calls.filter(r=>r.service==='write_time_program_day').length,0);
testWindow.confirm=()=>false;copy=copyFixture();await copy.x.copyDays();assert.equal(copy.calls.length,1);assert.equal(copy.x._copying,false);
console.log('Copy checks passed: sequential targets, pending stop, stale guard and cancellation');

const scheduleStage=vm.runInNewContext('('+fs.readFileSync('custom_components/wolflink_local/frontend/wolflink-mode-popup.js','utf8').match(/function wolfScheduleStage\(day\) \{[\s\S]*?\n\}/)[0]+')');
assert.equal(scheduleStage({status:'ok',write_status:'awaiting_confirmation'}),'awaiting_confirmation');
assert.equal(scheduleStage({status:'ok',write_status:'confirmed'}),'confirmed');
assert.equal(scheduleStage({status:'ok'}),'reported');
assert.equal(scheduleStage({status:'unavailable_or_unsupported_format'}),'unavailable');
assert.equal(scheduleStage({status:'ok',write_status:'failed'}),'failed');
console.log('Schedule status checks passed: pending, confirmed, reported, unavailable and failed');

const Table=classes.get('wolflink-portal-table'),table=Object.create(Table.prototype),events=[];table._hass={};table.dispatchEvent=e=>events.push(e);table.open({entity:'number.synthetic'});assert.equal(events[0].type,'hass-more-info');assert.equal(events[0].detail.entityId,'number.synthetic');const popupCards=[{type:'custom:wolflink-schedule'}];table.open({entity:'select.synthetic',name:'Zeitprogramm',popup:popupCards});assert.equal(events[1].type,'show-dialog');assert.equal(events[1].detail.dialogParams.cards,popupCards);console.log('Portal table opens existing entity/schedule dialogs without a write action');

({dial,calls}=fixture(60));const dialNodes=new Map();dial.shadowRoot={querySelector:key=>{if(!dialNodes.has(key))dialNodes.set(key,{dataset:{},style:{},setAttribute(){},textContent:''});return dialNodes.get(key)}};dial._hass.formatEntityState=x=>x.state;dial.updateState=Dial.prototype.updateState;await dial.adjust(-1);assert.equal(dialNodes.get('.minus').disabled,false);assert.equal(dialNodes.get('.value').textContent,'59');assert.match(dialNodes.get('.hint').textContent,/Anlagenwert: 60/);dial.cancelDraft();assert.equal(dialNodes.get('.value').textContent,'60');assert.equal(calls.length,0);console.log('Draft remains editable, actual value stays distinct, cancellation restores actual display');

const Energy=classes.get('wolflink-energy-overview'),energy=Object.create(Energy.prototype);energy.config={heating_entity:'sensor.heat',water_entity:'sensor.water'};
const energyState=(heat,water)=>{energy._hass={states:{'sensor.heat':{state:String(heat),attributes:{unit_of_measurement:'kWh'}},'sensor.water':{state:String(water),attributes:{unit_of_measurement:'kWh'}}}};return energy.energy();};
let split=energyState(21757,5487);assert.equal(split.total,27244);assert.equal(split.heatingPercent.toFixed(1),'79.9');assert.equal(split.waterPercent.toFixed(1),'20.1');
assert.equal(energyState(0,0).heatingPercent,null);assert.equal(energyState('unavailable',12).total,null);assert.equal(energyState(-1,12).total,null);assert.equal(energyState(0,12).waterPercent,100);assert.equal(energyState(12,0).heatingPercent,100);energy._hass.states['sensor.heat'].attributes.unit_of_measurement='MWh';assert.equal(energy.energy().total,null);
console.log('Energy split checks passed: totals, percentages, zero counters, missing values, negative counters and units');

const Periods=classes.get('wolflink-energy-periods'),periods=Object.create(Periods.prototype);
periods.config={groups:[{title:'Tage',periods:[{name:'Heute',consumption_entity:'sensor.c',heat_entity:'sensor.h'}]},{title:'Jahre',periods:[{name:'Vorjahr',consumption_entity:'sensor.y',heat_entity:'sensor.missing'}]}]};
periods._hass={states:{'sensor.c':{state:'0',attributes:{unit_of_measurement:'kWh'}},'sensor.h':{state:'19',attributes:{unit_of_measurement:'kWh'}},'sensor.y':{state:'9458',attributes:{unit_of_measurement:'kWh'}}}};
assert.equal(periods.groups()[0].max,19);assert.equal(periods.groups()[1].max,9458);assert.equal(periods.groups()[0].periods[0].consumption,0);assert.equal(periods.groups()[1].periods[0].heat,null);
periods.shadowRoot={innerHTML:''};periods.render();assert.match(periods.shadowRoot.innerHTML,/Nicht verfügbar/);assert.ok(!periods.shadowRoot.innerHTML.includes('NaN'));assert.match(periods.shadowRoot.innerHTML,/width:100%/);
periods._hass.states['sensor.h'].state='-1';assert.equal(periods.groups()[0].max,0);periods.render();assert.ok(!periods.shadowRoot.innerHTML.includes('NaN'));
periods._hass.states['sensor.y'].attributes.unit_of_measurement='MWh';assert.equal(periods.groups()[1].periods[0].consumption,null);
console.log('Energy period charts: separate scales, valid zero, missing/negative counters, units and rendering passed');

const validOptional=vm.runInNewContext('('+fs.readFileSync('custom_components/wolflink_local/frontend/wolflink-mode-popup.js','utf8').match(/function wolfValidOptionalMeasurement\(state\)\{[\s\S]*?\n\}/)[0]+')');
for(const state of [undefined,{}, {state:null},{state:''},{state:' '},{state:'unknown'},{state:'unavailable'},{state:'NaN'},{state:'Infinity'}])assert.equal(validOptional(state),false);
for(const value of ['0','21.5','-2',0])assert.equal(validOptional({state:value}),true);
console.log('Optional room temperature: missing and invalid states hidden; valid zero and numeric measurements displayed');

const Reading=classes.get('wolflink-reading');
const readingParts={'.value':{},'ha-icon':{},'button':{}};
const optionalReading={config:{entity:'sensor.room',name:'Raumtemperatur',optional_measurement:true},style:{},shadowRoot:{querySelector:key=>readingParts[key]}};
const roomRow={row:{entity:'sensor.room',optional_measurement:true},el:{style:{}},text:{}};
const roomTable={_rows:[roomRow]};
for(const [value,display] of [['unavailable','none'],['21.5',''],['0',''],['unknown','none']]){
 const hass={states:{'sensor.room':{state:value,attributes:{unit_of_measurement:'°C'}}},formatEntityState:s=>s.state+' °C'};
 optionalReading._hass=hass;Reading.prototype.update.call(optionalReading);assert.equal(optionalReading.style.display,display);
 roomTable._hass=hass;classes.get('wolflink-portal-table').prototype.update.call(roomTable);assert.equal(roomRow.el.style.display,display);
}
console.log('Room temperature cards and table rows react to sensor availability changes without reload');
