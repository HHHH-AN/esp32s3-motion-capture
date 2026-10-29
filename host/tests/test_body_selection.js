"use strict";
// Execute the actual controller with a DOM/socket harness. No real endpoints.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
function harness(){
  const elements=new Map(),diagnostics=[],sent=[],timers=new Map();let timerId=0,animation=null,now=0;
  function element(){return {value:"",children:[],disabled:false,textContent:"",className:"",dataset:{},
    classList:{toggle(){}},append(...items){this.children.push(...items);},
    replaceChildren(...items){this.children=items;},setAttribute(){},scrollIntoView(){},
    get options(){return this.children;}};}
  const document={activeElement:null,getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element};
  class Socket{constructor(){this.readyState=1;Socket.last=this;}send(value){sent.push(JSON.parse(value));}}
  class View{draw(){}reset(){}clearTrail(){}}
  const context={document,WebSocket:Socket,BodyView:{BodyView:View},PoseMath:require("../web/pose_math.js"),location:{protocol:"http:",host:"offline"},
    requestAnimationFrame(fn){animation=fn;},performance:{now:()=>now},setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId;},clearTimeout(id){timers.delete(id);},localStorage:{setItem(){}},console,
    fetch:async()=>({ok:true,json:async()=>({items:[]})})};
  context.window=context;
  context.renderBodyDiagnostic=(device,state)=>diagnostics.push({id:device?.device_id,state});
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../web/body_app.js"),"utf8"),context);
  Socket.last.onopen();
  const a={device_id:"A",body_slot:"right_upper_arm",source:"real",valid:true,quaternion:[1,0,0,0],stability:{enabled:true}};
  const b={device_id:"B",body_slot:"right_forearm",source:"real",valid:true,quaternion:[.7071,.7071,0,0],stability:{enabled:true}};
  function frame(selected="A"){return {mode:"LIVE",devices:[a,b],selected_device_id:selected,selected_node:selected==="A"?a:b,
    slots:[{id:a.body_slot,name:"右上臂",device_id:"A"},{id:b.body_slot,name:"右前臂",device_id:"B"}],
    command_result:null,body_frame:{segments:[]},endpoints:[],recording:{active:false},replay:{},initialization:{status:"idle"},
    attitude_config:{profiles:{magnetic_guarded:{name:"磁门控"}}}};}
  const flush=(ms=100)=>{now+=ms;animation(now);};
  const receive=(selected,extra={},paint=true)=>{Socket.last.onmessage({data:JSON.stringify({...frame(selected),...extra})});if(paint)flush();};
  return {context,document,sent,diagnostics,receive,runTimer(ms){for(const [id,timer] of [...timers])if(timer.ms===ms){timers.delete(id);timer.fn();}},get:id=>document.getElementById(id),select:document.getElementById("bodyDevice"),
    flush,setQuaternion(id,q){(id==="A"?a:b).quaternion=q;}};
}
{
  const h=harness();h.receive("A");const before=h.diagnostics.length;
  for(let i=0;i<1000;i++){h.setQuaternion("A",[1,0,0,i/1000]);h.receive("A",{},false);}
  assert.equal(h.diagnostics.length,before,"burst messages must not redraw the DOM individually");
  h.flush();assert.equal(h.diagnostics.length,before+1,"only latest UI state is rendered after a burst");
  assert.equal(h.context.BodyApp.latest().devices[0].quaternion[3],.999);
  h.flush(10);assert.equal(h.diagnostics.length,before+1,"unchanged UI must not repaint every animation frame");
}
{
  const h=harness();h.receive("A");h.context.BodyApp.command("calibrate");
  const id=h.sent.at(-1).request_id,old=h.context.BodyApp.latest();
  h.receive("B",{timestamp:Date.now()/1000-5,command_result:{request_id:id,ok:true,message:"校准已确认"}});
  assert.equal(h.context.BodyApp.latest(),old,"queued stale display state must not replace current state");
  assert.equal(h.context.BodyApp.diagnostics.staleStates,1);
  assert.match(h.get("commandFeedbackText").textContent,/校准已确认/,"stale pose filtering must preserve command acknowledgements");
}
{
  const h=harness();
  for(let i=0;i<9000;i++){h.receive("A",{},false);h.flush(1000/30);}
  assert.equal(h.context.BodyApp.diagnostics.receivedStates,9000);
  assert.ok(h.context.BodyApp.diagnostics.uiUpdates<=3001,"five-minute 30 Hz stream must retain bounded UI work");
}
{
  const h=harness();h.receive("A");
  // Native select can hold an uncommitted keyboard/mouse choice while the
  // 30Hz server heartbeat still reports A. Never reset that focused control.
  h.document.activeElement=h.select;h.select.value="B";h.receive("A");
  assert.equal(h.select.value,"B","heartbeat overwrote the user's pending native selection");
  h.select.onchange();
  assert.equal(h.sent.at(-1).action,"select");assert.equal(h.sent.at(-1).device_id,"B");
  assert.equal(h.diagnostics.at(-1).id,"B","diagnostics must update immediately after selection");
  // In-flight old frames must not revert the selection before the server ack.
  h.document.activeElement=null;h.receive("A");
  assert.equal(h.select.value,"B");assert.equal(h.diagnostics.at(-1).id,"B");
  h.context.BodyApp.command("calibrate");
  assert.equal(h.sent.at(-1).device_id,"B","mutation target must match the displayed device");
  h.receive("B");assert.equal(h.select.value,"B");
  assert.equal(h.diagnostics.at(-1).state.selected_device_id,"B");
  const bBefore=Array.from(h.diagnostics.at(-1).state.selected_node.quaternion);
  h.setQuaternion("A",[0,1,0,0]);h.receive("B");
  assert.deepEqual(Array.from(h.diagnostics.at(-1).state.selected_node.quaternion),bBefore,"A moving must not change B diagnostics");
  h.setQuaternion("B",[0,0,1,0]);h.receive("B");
  assert.deepEqual(Array.from(h.diagnostics.at(-1).state.selected_node.quaternion),[0,0,1,0],"B movement must update B diagnostics");
}
{
  const h=harness();h.receive("A");
  const slots=h.document.getElementById("bodySlots").children;
  slots[1].onclick();
  assert.equal(h.sent.at(-1).device_id,"B");
  assert.equal(h.diagnostics.at(-1).id,"B","slot selection and diagnostic model must agree");
  h.receive("A");assert.equal(h.diagnostics.at(-1).id,"B");
  h.receive("B");
  h.select.value="A";h.select.onchange();h.receive("B");
  assert.equal(h.diagnostics.at(-1).id,"A");
  h.context.BodyApp.command("set_processing",{profile:"six_axis_relative"});
  assert.equal(h.sent.at(-1).device_id,"A");
}
console.log("body selection: focused native choice, stale heartbeat, diagnostics and command identity passed");

{
  const h=harness();h.receive("A",{command_result:undefined});
  h.context.BodyApp.command("reset_reference");
  assert.equal(h.sent.length,0,"legacy backend must not receive an operation that cannot be confirmed");
  assert.match(h.get("commandFeedbackText").textContent,/后台.*本次操作未发送/);
  h.runTimer(10000);assert.equal(h.get("commandFeedback").hidden,true);
}
{
  const h=harness();h.receive("A");h.context.BodyApp.command("reset_reference");
  const id=h.sent.at(-1).request_id;
  h.context.BodyApp.command("reset_reference");assert.equal(h.sent.length,1,"pending request blocks duplicate submission");
  h.runTimer(15000);assert.match(h.get("commandFeedbackText").textContent,/尚未确认/);
  h.receive("A",{command_result:{request_id:id,ok:true,message:"参考重置已确认"}});
  assert.equal(h.get("commandFeedbackText").textContent,"参考重置已确认","late receipt must replace stale timeout");
  h.runTimer(4000);assert.equal(h.get("commandFeedback").hidden,true);
  h.context.BodyApp.notify("读取失败","error");h.get("commandFeedbackClose").onclick();assert.equal(h.get("commandFeedback").hidden,true);
}
console.log("command feedback: legacy guard, duplicate prevention, timeout, late receipt, auto-dismiss and manual close passed");
