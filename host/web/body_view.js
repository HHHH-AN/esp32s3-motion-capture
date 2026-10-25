"use strict";
(function(root) {
  const COLORS={measured:"#087fad",online:"#087fad",initialized:"#087fad",uninitialized:"#b17a19",missing:"#aebbc4",unmeasured:"#aebbc4",stale:"#cc8a24",disconnected:"#b26464",conflict:"#c84646",invalid:"#c84646"};
  function listSegments(frame) {
    const source=frame?.segments||frame?.bones||{};
    return Array.isArray(source)?source:Object.entries(source).map(([slot,value])=>({slot,...value}));
  }
  function vector(value,fallback=[0,0,0]) {return Array.isArray(value)&&value.length===3&&value.every(Number.isFinite)?value:fallback;}
  function segmentEnds(segment,frame) {
    const positions=frame?.positions||frame?.joints||{};
    const resolve=value=>typeof value==="string"?positions[value]:value;
    return [vector(resolve(segment.start||segment.origin||segment.start_position)),vector(resolve(segment.end||segment.tip||segment.end_position))];
  }
  function rotate(v,q) {
    const [w,x,y,z]=q||[1,0,0,0],[a,b,c]=v,tx=2*(y*c-z*b),ty=2*(z*a-x*c),tz=2*(x*b-y*a);
    return [a+w*tx+y*tz-z*ty,b+w*ty+z*tx-x*tz,c+w*tz+x*ty-y*tx];
  }
  function translatePoint(point,offset) {return vector(point).map((value,i)=>value+vector(offset)[i]);}
  function pointSegmentDistance(p,a,b) {
    const dx=b[0]-a[0],dy=b[1]-a[1],d=dx*dx+dy*dy;
    const t=d?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d)):0;
    return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);
  }
  class BodyView {
    constructor(canvas,{kind="fixed",onSelect=()=>{}}={}) {
      this.canvas=canvas;this.kind=kind;this.onSelect=onSelect;this.yaw=-.65;this.elevation=.22;this.zoom=1;this.pan=[0,0];this.trail=[];this.hits=[];this.epoch=null;
      let drag=null;
      canvas.addEventListener("pointerdown",event=>{drag={x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,pan:event.shiftKey};canvas.setPointerCapture(event.pointerId);});
      canvas.addEventListener("pointermove",event=>{if(!drag)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(drag.pan){this.pan[0]+=dx;this.pan[1]+=dy;}else{this.yaw+=dx*.009;this.elevation=Math.max(-1.2,Math.min(1.2,this.elevation+dy*.009));}drag.x=event.clientX;drag.y=event.clientY;});
      canvas.addEventListener("pointerup",event=>{if(drag&&Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)<5){const box=canvas.getBoundingClientRect(),point=[event.clientX-box.left,event.clientY-box.top];const found=this.hits.map(item=>({...item,d:pointSegmentDistance(point,item.a,item.b)})).sort((a,b)=>a.d-b.d)[0];if(found&&found.d<15)this.onSelect(found.slot,found.device_id);}drag=null;});
      canvas.addEventListener("pointercancel",()=>{drag=null;});
      canvas.addEventListener("wheel",event=>{event.preventDefault();this.zoom=Math.min(2.8,Math.max(.45,this.zoom*Math.exp(-event.deltaY*.001)));},{passive:false});
    }
    reset(){this.yaw=-.65;this.elevation=.22;this.zoom=1;this.pan=[0,0];}
    clearTrail(){this.trail=[];}
    draw(frame,{selectedSlot,devices=[],position=[0,0,0],positionSource="off",mode="LIVE",epoch=null}={}) {
      const canvas=this.canvas,box=canvas.getBoundingClientRect();if(!box.width||!box.height)return;
      const dpr=Math.min(root.devicePixelRatio||1,2),w=Math.round(box.width*dpr),h=Math.round(box.height*dpr);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,box.width,box.height);this.hits=[];
      const scale=Math.min(box.width*.34,box.height*.43)*this.zoom,origin=[box.width/2+this.pan[0],box.height*.89+this.pan[1]],rootOffset=this.kind==="translated"?vector(position):[0,0,0];
      const project=p=>{const [x,y,z]=vector(p),horizontal=Math.cos(this.yaw)*y-Math.sin(this.yaw)*x,depth=Math.sin(this.yaw)*y+Math.cos(this.yaw)*x;return [origin[0]-horizontal*scale,origin[1]+(Math.sin(this.elevation)*depth-Math.cos(this.elevation)*z)*scale,depth];};
      const line=(a,b,color,width=1,dash=[])=>{ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();ctx.setLineDash([]);};
      for(let i=-2;i<=2;i+=.25){line(project([i,-2,0]),project([i,2,0]),"#e3ebf0");line(project([-2,i,0]),project([2,i,0]),"#e3ebf0");}
      const o=project([0,0,0]);[[.35,0,0],[0,.35,0],[0,0,.35]].forEach((axis,i)=>{const end=project(axis);line(o,end,["#e66354","#279975","#397fd7"][i],2);ctx.fillStyle=["#e66354","#279975","#397fd7"][i];ctx.font="11px system-ui";ctx.fillText("XYZ"[i],end[0]+4,end[1]);});
      if(this.epoch!==epoch){this.trail=[];this.epoch=epoch;}
      if(this.kind==="boards") {this.drawBoards(ctx,box,devices,selectedSlot);return;}
      if(this.kind==="translated"&&positionSource!=="off") {
        const previous=this.trail[this.trail.length-1];if(!previous||rootOffset.some((value,i)=>Math.abs(value-previous[i])>.001)){this.trail.push([...rootOffset]);if(this.trail.length>2000)this.trail.shift();}
        for(let i=1;i<this.trail.length;i++)line(project(this.trail[i-1]),project(this.trail[i]),"#d79729",2);
      }
      const segments=listSegments(frame);
      const bySegment=Object.fromEntries(segments.map(segment=>[segment.id||segment.slot,segment]));
      for(const segment of segments) {
        const slot=segment.slot||segment.id||segment.body_slot,[start,end]=segmentEnds(segment,frame),a=project(translatePoint(start,rootOffset)),b=project(translatePoint(end,rootOffset)),status=segment.status||segment.state||(segment.measured?"measured":"unmeasured"),selected=slot===selectedSlot;
        const color=COLORS[status]||COLORS[segment.measured?"measured":"unmeasured"];
        // The links between joint anchors are virtual geometry, not additional
        // sampled segments. Connect to the nearest point on the parent bone.
        const parent=bySegment[segment.parent];
        if(parent){const [p0,p1]=segmentEnds(parent,frame),d=p1.map((v,i)=>v-p0[i]),n=d.reduce((sum,v)=>sum+v*v,0),t=n?Math.max(0,Math.min(1,d.reduce((sum,v,i)=>sum+v*(start[i]-p0[i]),0)/n)):0,anchor=p0.map((v,i)=>v+t*d[i]);if(Math.hypot(...anchor.map((v,i)=>v-start[i]))>1e-5)line(project(translatePoint(anchor,rootOffset)),a,"#aebbc4",2,[3,3]);}
        line(a,b,selected?"#e7732e":color,selected?8:5,segment.measured?[]:[5,4]);
        ctx.fillStyle=selected?"#e7732e":color;for(const point of [a,b]){ctx.beginPath();ctx.arc(point[0],point[1],selected?5:3,0,Math.PI*2);ctx.fill();}
        this.hits.push({slot,device_id:segment.device_id,a,b});
        if(slot==="head"){const face=rotate([.12,0,0],segment.world_quaternion||[1,0,0,0]),tip=end.map((v,i)=>v+face[i]);line(b,project(translatePoint(tip,rootOffset)),color,3);}
        if(selected){[[.1,0,0],[0,.1,0],[0,0,.1]].forEach((axis,i)=>{const delta=rotate(axis,segment.world_quaternion||[1,0,0,0]);line(a,project(translatePoint(start.map((v,j)=>v+delta[j]),rootOffset)),["#e66354","#279975","#397fd7"][i],2);});}
      }
      ctx.font="12px system-ui";ctx.fillStyle="#526b7a";ctx.fillText(this.kind==="fixed"?"固定根部 · 仅姿态":`独立位置来源：${positionSource==="off"?"关闭":positionSource}`,12,23);
      if(!segments.length){ctx.fillText("等待骨架帧；未接入节点不推测动作",12,44);}
      if(this.kind==="translated"){ctx.fillStyle="#9a681a";ctx.fillText("相机拖动只改变观察视角，不是测量平移",12,box.height-12);}
    }
    drawBoards(ctx,box,devices,selectedSlot) {
      const shown=devices.length?devices:[],columns=shown.length>4?4:shown.length>1?2:1,rows=Math.max(1,Math.ceil(shown.length/columns)),cellW=box.width/columns,cellH=box.height/rows;
      if(!shown.length){ctx.font="13px system-ui";ctx.fillStyle="#617482";ctx.fillText("暂无设备。模拟设备会显式标识，不计为硬件在线。",18,28);return;}
      shown.forEach((device,index)=>{const cx=(index%columns+.5)*cellW,cy=(Math.floor(index/columns)+.49)*cellH,s=Math.min(cellW*.9,cellH*1.8),q=device.quaternion||device.q||[1,0,0,0],slot=device.body_slot||device.slot,points=[[-.18,-.12,0],[.18,-.12,0],[.18,.12,0],[-.18,.12,0]].map(v=>rotate(v,q)).map(([x,y,z])=>[cx+(y-x*.35)*s,cy+(x*.2-z)*s]);
        ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.fillStyle=device.source==="real"?"#c1e0ee":"#f4dca8";ctx.fill();ctx.strokeStyle=slot===selectedSlot?"#e7732e":"#4a8ba6";ctx.lineWidth=slot===selectedSlot?3:1.5;ctx.stroke();
        [[.25,0,0],[0,.25,0],[0,0,.25]].forEach((axis,i)=>{const [x,y,z]=rotate(axis,q),tip=[cx+(y-x*.35)*s,cy+(x*.2-z)*s];ctx.strokeStyle=["#e66354","#279975","#397fd7"][i];ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(...tip);ctx.stroke();});
        ctx.font="11px system-ui";ctx.fillStyle="#163044";ctx.textAlign="center";ctx.fillText(String(device.device_id||device.node_id||device.id||"未识别").slice(0,27),cx,(Math.floor(index/columns)+1)*cellH-24);ctx.fillStyle=device.source==="real"?"#617482":"#9a681a";ctx.fillText(`${slot||"未绑定"} · ${device.source==="real"?"真实输入":"模拟"}`,cx,(Math.floor(index/columns)+1)*cellH-8);ctx.textAlign="left";
        this.hits.push({slot,device_id:device.device_id||device.node_id||device.id,a:[cx-cellW*.4,cy],b:[cx+cellW*.4,cy]});
      });
    }
  }
  const api={BodyView,listSegments,segmentEnds,rotate,translatePoint,pointSegmentDistance};root.BodyView=api;
  if(typeof module!=="undefined")module.exports=api;
})(globalThis);
