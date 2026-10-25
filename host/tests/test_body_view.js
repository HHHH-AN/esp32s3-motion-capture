"use strict";
const assert=require("node:assert/strict");
const {listSegments,segmentEnds,rotate,translatePoint,pointSegmentDistance}=require("../web/body_view.js");
function close(a,b){assert.equal(a.length,b.length);a.forEach((value,index)=>assert.ok(Math.abs(value-b[index])<1e-10,`${a} != ${b}`));}
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
console.log("body view math: known axes, translation isolation, geometry adapters and picking passed");
