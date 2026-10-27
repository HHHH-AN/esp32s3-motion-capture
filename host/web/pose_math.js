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
  function slerp(a,b,t){
    const unit=q=>{if(!Array.isArray(q)||q.length!==4)return [1,0,0,0];const n=Math.hypot(...q);return n>1e-9?q.map(v=>v/n):[1,0,0,0];};
    a=unit(a);b=unit(b);let dot=a.reduce((s,v,i)=>s+v*b[i],0);
    if(dot<0){b=b.map(v=>-v);dot=-dot;}
    t=Math.max(0,Math.min(1,t));
    if(dot>.9995)return unit(a.map((v,i)=>v+t*(b[i]-v)));
    const angle=Math.acos(Math.min(1,dot)),den=Math.sin(angle);
    return a.map((v,i)=>(v*Math.sin((1-t)*angle)+b[i]*Math.sin(t*angle))/den);
  }
  // Presentation only: interpolate received states, never predict across a
  // pause, restart, reference change or live/replay switch. Recorded data is
  // untouched. A small delay absorbs ordinary 30 Hz delivery jitter.
  class DisplayBuffer {
    constructor(delayMs=50,maxGapMs=250){this.delayMs=delayMs;this.maxGapMs=maxGapMs;this.frames=[];this.key=null;}
    push(state,time){
      const key=JSON.stringify([state.mode,state.epoch,state.replay?.session,
        (state.devices||[]).map(d=>[d.device_id,d.boot_id,d.reference_revision,d.processing_profile,d.source,d.valid,d.connected])]);
      if(key!==this.key||state.mode!=="LIVE"){this.frames=[];this.key=key;}
      const last=this.frames[this.frames.length-1];
      if(last&&time<=last.time)this.frames.pop();
      this.frames.push({state,time});if(this.frames.length>12)this.frames.shift();
    }
    sample(now){
      if(!this.frames.length)return null;
      const latest=this.frames[this.frames.length-1],target=now-this.delayMs;
      if(latest.state.mode!=="LIVE"||now-latest.time>this.maxGapMs)return latest.state;
      const index=this.frames.findIndex(f=>f.time>=target);
      if(index<0)return latest.state;if(index===0)return this.frames[0].state;
      const a=this.frames[index-1],b=this.frames[index],gap=b.time-a.time;
      if(gap<=0||gap>this.maxGapMs)return latest.state;
      const t=Math.max(0,Math.min(1,(target-a.time)/gap));
      const blend=(x,y)=>Array.isArray(x)&&Array.isArray(y)&&x.length===y.length?x.map((v,i)=>v+(y[i]-v)*t):y;
      const devices=(b.state.devices||[]).map(d=>{const old=(a.state.devices||[]).find(v=>v.device_id===d.device_id);
        return old&&d.valid?{...d,quaternion:slerp(old.quaternion,d.quaternion,t)}:d;});
      const oldSegments=a.state.body_frame?.segments||[];
      const segments=(b.state.body_frame?.segments||[]).map(s=>{const old=oldSegments.find(v=>v.id===s.id);return old?{...s,
        start:blend(old.start,s.start),end:blend(old.end,s.end),
        world_quaternion:slerp(old.world_quaternion,s.world_quaternion,t),
        local_quaternion:slerp(old.local_quaternion,s.local_quaternion,t)}:s;});
      return {...b.state,devices,selected_node:devices.find(d=>d.device_id===b.state.selected_device_id)||b.state.selected_node,
        body_frame:{...b.state.body_frame,segments}};
    }
  }
  const api=Object.freeze({rotate,worldVertex,cameraBasis,project,slerp,DisplayBuffer});root.PoseMath=api;
  if(typeof module!=="undefined")module.exports=api;
})(globalThis);
