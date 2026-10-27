"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const source=fs.readFileSync(require("node:path").join(__dirname,"../web/app.js"),"utf8");
let canvasCalls=0;
const hidden={getClientRects(){return [];}};
const context={$:()=>hidden,canvasSize(){canvasCalls++;throw new Error("hidden canvas must not be painted");},console};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("function drawPose()"),source.indexOf("function addHistory(")),context);
context.drawPose();context.drawChart(hidden,[[1,2,3]]);assert.equal(canvasCalls,0);
let models=0,charts=0;
const animation={replay:null,latest:null,playing:false,histories:{accel:[],gyro:[],mag:[]},
  $:()=>hidden,drawPose(){models++;},drawChart(){charts++;},requestAnimationFrame(){},window:{},orientation:[1,0,0,0]};
vm.createContext(animation);
vm.runInContext(source.slice(source.indexOf("let chartLastDraw="),source.indexOf("try{const saved=",source.indexOf("let chartLastDraw="))),animation);
for(let i=0;i<60;i++)animation.animate(i*1000/60);
assert.equal(models,60,"model animation must keep its frame cadence");
assert.ok(charts<=30,`${charts} chart paints exceeded ten updates per second per chart`);
console.log("Rendering: collapsed canvases perform no drawing; charts throttle without reducing model frame rate");
