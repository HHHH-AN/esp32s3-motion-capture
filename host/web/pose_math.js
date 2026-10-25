"use strict";
(function(root){
  function rotate(v,q){const[w,x,y,z]=q,[vx,vy,vz]=v,tx=2*(y*vz-z*vy),ty=2*(z*vx-x*vz),tz=2*(x*vy-y*vx);return[vx+w*tx+y*tz-z*ty,vy+w*ty+z*tx-x*tz,vz+w*tz+x*ty-y*tx];}
  // Position is already expressed in the display frame. Axis reflection is
  // applied to orientation geometry too, not solely to its translation.
  function worldVertex(local,q,position,signs){return rotate(local,q).map((v,i)=>position[i]+signs[i]*v);}
  const api=Object.freeze({rotate,worldVertex});root.PoseMath=api;
  if(typeof module!=="undefined")module.exports=api;
})(globalThis);
