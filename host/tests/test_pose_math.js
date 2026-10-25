const assert=require("node:assert/strict");
const {worldVertex}=require("../web/pose_math.js");
const q=[Math.SQRT1_2,0,0,Math.SQRT1_2];
function near(actual,expected){actual.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-10));}
near(worldVertex([1,0,0],q,[2,3,4],[1,1,1]),[2,4,4]);
near(worldVertex([0,1,0],q,[2,3,4],[-1,1,1]),[3,3,4]);
near(worldVertex([0,0,0],q,[2,3,4],[-1,-1,-1]),[2,3,4]);
console.log("3D pose rotation, translation and axis reflection tests passed");
