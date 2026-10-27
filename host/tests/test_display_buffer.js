"use strict";
const assert=require("node:assert/strict");
const {DisplayBuffer,slerp,rotate}=require("../web/pose_math.js");
const q=degrees=>[Math.cos(degrees*Math.PI/360),0,0,Math.sin(degrees*Math.PI/360)];
function frame(degrees,extra={}){return {mode:"LIVE",epoch:0,selected_device_id:"A",
  devices:[{device_id:"A",boot_id:"boot1",reference_revision:0,valid:true,connected:true,quaternion:q(degrees),...extra}],
  body_frame:{segments:[{id:"head",start:[0,0,0],end:[0,0,1],world_quaternion:q(degrees),local_quaternion:q(degrees)}]}};}
const angle=q=>Math.atan2(rotate([1,0,0],q)[1],rotate([1,0,0],q)[0])*180/Math.PI;
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
{
  const buffer=new DisplayBuffer(50),a=frame(0),b=frame(90);buffer.push(a,0);buffer.push(b,100);
  const shown=buffer.sample(100);near(angle(shown.devices[0].quaternion),45);
  near(angle(shown.body_frame.segments[0].world_quaternion),45);
  assert.equal(shown.selected_node.device_id,"A");
  near(angle(a.devices[0].quaternion),0);near(angle(b.devices[0].quaternion),90);
  near(angle(buffer.sample(1000).devices[0].quaternion),90); // No extrapolation through a stall.
  for(let now=50;now<=150;now+=5)near(angle(buffer.sample(now).devices[0].quaternion),(now-50)*.9);
}
{
  for(const changed of [{boot_id:"boot2"},{reference_revision:1},{valid:false},{processing_profile:"six_axis_relative"}]){
    const buffer=new DisplayBuffer(50);buffer.push(frame(0),0);buffer.push(frame(90,changed),100);
    near(angle(buffer.sample(100).devices[0].quaternion),90);
  }
  const buffer=new DisplayBuffer(50);buffer.push(frame(0),0);buffer.push({...frame(90),mode:"REPLAY"},100);
  near(angle(buffer.sample(100).devices[0].quaternion),90); // Saved replay frames stay exact.
}
{
  const buffer=new DisplayBuffer(50);buffer.push(frame(0),0);buffer.push(frame(90),500);
  near(angle(buffer.sample(500).devices[0].quaternion),90);
  for(let i=0;i<100;i++)buffer.push(frame(i),600+i*30);assert.ok(buffer.frames.length<=12);
  near(angle(slerp(q(10),q(10).map(v=>-v),.5)),10); // Quaternion sign is not a full revolution.
}
console.log("Display interpolation: smooth known rotation, no fabricated motion, restart/reference/stale/replay isolation passed");
