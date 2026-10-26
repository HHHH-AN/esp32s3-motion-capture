"use strict";
// Execute the shipped controller. All states and commands are offline; no
// transport or hardware calibration is invoked by this test harness.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

function harness(){
  const elements=new Map(),sent=[];
  function element(){return {value:"",children:[],disabled:false,checked:false,textContent:"",className:"",type:"",
    append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(){}};}
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element};
  const context={document,BodyApp:{connected:true,command(action,payload){sent.push(JSON.parse(JSON.stringify({action,...payload})));}}};context.window=context;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../web/direction_app.js"),"utf8"),context);
  const a={device_id:"physical-a",body_slot:"right_upper_arm",source:"simulation_sensor",valid:true,connected:true,
    gyro:[18,0,0],stability:{gyro_bias_dps:[17,0,0],holding:true,magnetic_used:false},processing_profile:"six_axis_relative",quality:{age_ms:12}};
  const b={device_id:"physical-b",body_slot:"right_forearm",source:"simulation_sensor",valid:true,connected:true,
    gyro:[0,0,0],stability:{gyro_bias_dps:[0,0,0],holding:false,magnetic_used:true},processing_profile:"magnetic_guarded",quality:{age_ms:8}};
  const pelvis={device_id:"pelvis-node",body_slot:"pelvis",source:"simulation_sensor",valid:true,stability:{}};
  function state(calibration={},extra={}){return {mode:"LIVE",devices:[a,b,pelvis],selected_device_id:"physical-a",recording:{active:false},direction_calibration:calibration,...extra};}
  return {context,sent,a,b,pelvis,state,update(value){context.DirectionApp.update(value);},get(id){return document.getElementById(id);},checkbox(index){return document.getElementById("directionDevices").children[index].children[0];}};
}

{
  const h=harness();h.update(h.state());
  assert.equal(h.sent.length,0,"render must not connect, switch processing or start calibration");
  assert.equal(h.checkbox(0).checked,true);
  assert.equal(h.checkbox(1).checked,false);
  assert.equal(h.checkbox(2).disabled,true,"arm guide must not pretend to calibrate pelvis");
  assert.equal(h.get("directionForwardStart").disabled,true,"forward stage needs a neutral window");
  h.checkbox(1).checked=true;h.checkbox(1).onchange();h.get("directionNeutralStart").onclick();
  assert.deepEqual(h.sent.at(-1),{action:"direction_start",stage:"neutral",device_ids:["physical-a","physical-b"]});
  const rows=h.get("directionDevices").children;
  assert.match(rows[0].children[1].children[1].textContent,/残余角速度 1\.000/);
  assert.match(rows[0].children[1].children[1].textContent,/不能证明无漂移/);
  assert.match(rows[1].children[1].children[1].textContent,/磁场 参与融合/);
}
{
  const h=harness();h.update(h.state({status:"capturing",stage:"neutral",devices:["physical-a"],elapsed_s:1.2,message:"采集静止窗口"}));
  assert.equal(h.get("directionNeutralStart").disabled,true);
  assert.equal(h.checkbox(0).disabled,true);
  assert.equal(h.get("directionApply").disabled,true,"elapsed time alone cannot produce a successful calibration");
  h.update(h.state({status:"capturing",stage:"neutral",capture_phase:"preparing",message:"准备倒计时 1.5 秒"}));
  assert.equal(h.get("directionState").textContent,"准备倒计时");
  h.update(h.state({status:"capturing",stage:"neutral",capture_phase:"waiting",message:"角速度持续偏大，继续等待"}));
  assert.equal(h.get("directionState").textContent,"等待更稳定的数据");
  assert.equal(h.get("directionApply").disabled,true);
  assert.equal(h.sent.length,0,"waiting for stability must not send another capture command");
  h.update(h.state({status:"neutral_ready",stage:"neutral",devices:["physical-a"],message:"中立完成，尚未方向标定"}));
  assert.equal(h.get("directionForwardStart").disabled,false);
  assert.equal(h.get("directionApply").disabled,true);
  assert.equal(h.get("directionState").textContent,"中立采样完成");
  h.get("directionForwardStart").onclick();assert.equal(h.sent.at(-1).stage,"forward");
}
{
  const h=harness();h.update(h.state({status:"failed",stage:"forward",message:"动作幅度不足，请重采",devices:["physical-a"],results:{"physical-a":{status:"failed",error:"动作幅度不足"}}}));
  assert.equal(h.get("directionApply").disabled,true);
  assert.match(h.get("directionMessage").textContent,/动作幅度不足/);
  assert.match(h.get("directionResults").children[0].children[1].textContent,/失败：动作幅度不足/);
  assert.equal(h.get("directionState").className,"badge error");
  h.update(h.state({status:"candidate",devices:["physical-a"],results:{"physical-a":{body_slot:"right_upper_arm",quality:{excursion_deg:42.3,return_error_deg:.5,axis_consistency:.99}}}}));
  assert.equal(h.get("directionApply").disabled,false);
  assert.equal(h.get("directionState").textContent,"拟合通过，待应用");
  h.get("directionApply").onclick();assert.equal(h.sent.at(-1).action,"direction_apply");
  h.update(h.state({status:"complete",calibration_id:"saved-result",devices:["physical-a"],results:{}}));
  assert.equal(h.get("directionApply").disabled,true);
  assert.match(h.get("directionScope").textContent,/saved-result/);
}
{
  const h=harness();h.update(h.state({status:"candidate"},{recording:{active:true}}));
  for(const id of ["directionNeutralStart","directionForwardStart","directionApply","directionCancel"]){assert.equal(h.get(id).disabled,true,`recording must lock ${id}`);}
  h.update(h.state({status:"complete",results:{}},{mode:"REPLAY"}));
  assert.match(h.get("directionMessage").textContent,/回放当时保存/);
  assert.equal(h.get("directionApply").disabled,true);
  h.a.source="real";h.update(h.state());
  assert.equal(h.sent.length,0,"status changes must never send automatic hardware commands");
}
{
  const h=harness();h.a.body_slot="right_forearm";h.b.body_slot="right_hand";
  h.update(h.state());
  assert.equal(h.checkbox(1).disabled,false,"the right hand must be selectable alongside the forearm");
  assert.equal(h.checkbox(2).disabled,true,"hand support must not enable unrelated pelvis calibration");
  h.checkbox(1).checked=true;h.checkbox(1).onchange();
  h.get("directionNeutralStart").onclick();
  assert.deepEqual(h.sent.at(-1),{action:"direction_start",stage:"neutral",device_ids:["physical-a","physical-b"]});
  assert.doesNotMatch(h.get("directionDevices").children[1].children[1].children[1].textContent,/本向导仅用于/);
  h.update(h.state({status:"complete",has_neutral:true,devices:["physical-a"],calibration_id:"kept-reference"}));
  assert.equal(h.checkbox(1).disabled,true,"an existing capture scope must stay locked until explicitly ended");
  assert.equal(h.get("directionCancel").textContent,"结束本轮并调整设备");
  assert.match(h.get("directionMessage").textContent,/重新选择设备/);
  h.get("directionCancel").onclick();
  assert.equal(h.sent.at(-1).action,"direction_cancel");
  assert.equal(h.checkbox(1).disabled,true,"wait for the server acknowledgement before unlocking the scope");
  h.update(h.state({status:"cancelled",has_neutral:false,devices:["physical-a"]}));
  assert.equal(h.checkbox(1).disabled,false);
  h.update(h.state({status:"cancelled",has_neutral:false},{recording:{active:true}}));
  assert.equal(h.checkbox(1).disabled,true,"recording must still lock hand selection");
  h.update(h.state({status:"cancelled",has_neutral:false},{mode:"REPLAY"}));
  assert.equal(h.checkbox(1).disabled,true,"replay must still lock hand selection");
}
{
  const h=harness();h.b.body_slot="left_hand";
  h.update(h.state({}, {selected_device_id:"physical-b"}));
  assert.equal(h.checkbox(1).checked,true,"a selected left hand is also an eligible initial choice");
  assert.equal(h.checkbox(1).disabled,false);
  h.get("directionNeutralStart").onclick();
  assert.deepEqual(h.sent.at(-1),{action:"direction_start",stage:"neutral",device_ids:["physical-b"]});
  assert.equal(h.checkbox(2).disabled,true);
}
console.log("direction UI: arm/forearm/hand scope, explicit scope reset, capture stages and record/replay locks passed");
