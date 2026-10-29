"use strict";
const assert=require("node:assert/strict");
const {listSegments,segmentEnds,rotate,translatePoint,pointSegmentDistance,eulerDegrees}=require("../web/body_view.js");
function close(a,b,tolerance=1e-10){assert.equal(a.length,b.length);a.forEach((value,index)=>assert.ok(Math.abs(value-b[index])<tolerance,`${a} != ${b}`));}
const frame={segments:[{id:"left_upper_arm",start:[0,.2,1.5],end:[0,.2,1.2],measured:true}],root_position:[0,0,1]};
assert.equal(listSegments(frame).length,1);
assert.equal(listSegments({segments:{head:{start:[0,0,1],end:[0,0,2]}}})[0].slot,"head");
assert.deepEqual(segmentEnds(frame.segments[0],frame),[[0,.2,1.5],[0,.2,1.2]]);
assert.deepEqual(segmentEnds({start:"a",end:"b"},{positions:{a:[1,2,3],b:[4,5,6]}}),[[1,2,3],[4,5,6]]);
close(rotate([1,0,0],[Math.SQRT1_2,0,0,Math.SQRT1_2]),[0,1,0]);
close(rotate([0,1,0],[Math.SQRT1_2,Math.SQRT1_2,0,0]),[0,0,1]);
close(translatePoint([0,0,1],[2,3,0]),[2,3,1]);
assert.equal(pointSegmentDistance([1,1],[0,0],[2,0]),1);
assert.equal(pointSegmentDistance([3,0],[0,0],[2,0]),1);
assert.equal(pointSegmentDistance([1,1],[0,0],[0,0]),Math.SQRT2);
assert.deepEqual(listSegments(null),[]);
// Euler readouts follow the displayed quaternion, including signed rotations,
// normalized inputs and the pitch limit, rather than stale server Euler fields.
close(eulerDegrees([1,0,0,0]),[0,0,0]);
const h=Math.SQRT1_2;
close(eulerDegrees([h,h,0,0]),[90,0,0]);
close(eulerDegrees([h,0,-h,0]),[0,-90,0],1e-5);
close(eulerDegrees([h,0,0,h]),[0,0,90]);
close(eulerDegrees([2*h,0,0,-2*h]),[0,0,-90]);
close(eulerDegrees([-h,0,0,-h]),[0,0,90]);
for(const q of [null,[],[0,0,0,0],[1,NaN,0,0]])assert.equal(eulerDegrees(q),null);
const element=()=>({textContent:"",children:[],append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
const panel=element();panel.ownerDocument={createElement:element};
const view=new (require("../web/body_view.js").BodyView)({addEventListener(){}},{kind:"boards",anglePanel:panel});
const a={device_id:"A",source:"real",valid:true,quaternion:[h,0,0,h],euler_deg:[0,0,-40]};
const b={device_id:"B",source:"real",valid:false,quaternion:[h,h,0,0]};
view.drawAngles([a,b],"LIVE");
assert.deepEqual(view.angleRows[0].outputs.map(item=>item.textContent),["0.0°","0.0°","90.0°"]);
assert.deepEqual(view.angleRows[1].outputs.map(item=>item.textContent),["90.0°","0.0°","0.0°"]);
assert.match(view.angleRows[1].status.textContent,/最后姿态/);
view.drawAngles([b],"REPLAY");assert.equal(panel.children.length,1);assert.equal(view.angleRows[0].status.textContent,"回放姿态");
view.drawAngles([{device_id:"B",quaternion:[0,0,0,0]}],"LIVE");assert.ok(view.angleRows[0].outputs.every(item=>item.textContent==="—"));
view.drawAngles([],"LIVE");assert.equal(view.angleRows.length,0);assert.match(panel.children[0].textContent,/等待设备/);
console.log("body view math: known axes, translation isolation, geometry adapters and picking passed");
