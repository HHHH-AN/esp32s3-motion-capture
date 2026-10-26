"use strict";
(function(root){
  function rotate(v,q){const[w,x,y,z]=q,[vx,vy,vz]=v,tx=2*(y*vz-z*vy),ty=2*(z*vx-x*vz),tz=2*(x*vy-y*vx);return[vx+w*tx+y*tz-z*ty,vy+w*ty+z*tx-x*tz,vz+w*tz+x*ty-y*tx];}
  // Right/up/toward-camera is a proper orthonormal frame. Canvas Y alone
  // points down; negate camera-up only at the final pixel conversion.
  function cameraBasis(yaw=-.65,elevation=.35){
    const c=Math.cos(yaw),s=Math.sin(yaw),ce=Math.cos(elevation),se=Math.sin(elevation);
    return {right:[-s,c,0],up:[-se*c,-se*s,ce],toward:[ce*c,ce*s,se]};
  }
  function project(point,yaw,elevation,origin=[0,0],scale=1,center=[0,0,0]){
    const v=point.map((n,i)=>n-center[i]),b=cameraBasis(yaw,elevation);
    const dot=a=>a.reduce((sum,n,i)=>sum+n*v[i],0);
    return [origin[0]+scale*dot(b.right),origin[1]-scale*dot(b.up),dot(b.toward)];
  }
  // Legacy displacement signs may affect experimental position, never reflect
  // an attitude basis. Old recordings retain their saved position unchanged.
  function worldVertex(local,q,position,signs){return rotate(local,q).map((v,i)=>position[i]+v);}
  const api=Object.freeze({rotate,worldVertex,cameraBasis,project});root.PoseMath=api;
  if(typeof module!=="undefined")module.exports=api;
})(globalThis);
