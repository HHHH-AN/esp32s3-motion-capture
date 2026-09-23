import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";

const $=s=>document.querySelector(s), viewport=$("#poseViewport"), signal=$("#signalCanvas"), sctx=signal.getContext("2d");
const COLORS={bone:0x1b1b18,online:0xee4b3e,offline:0x2878e8,virtual:0x96938b};
let nodes=[],stats={},ws; const history={acc:[],gyro:[],mag:[]},maxPoints=160;

// Leading underscores mark derived joints, never physical IMU nodes.
const rest={head:[0,2.5,0],_face:[0,2.5,.3],_neck:[0,2.2,0],_chest:[0,1.66,0],waist:[0,.68,0],_pelvis:[0,.25,0],left_shoulder:[-.58,1.92,0],left_elbow:[-1.12,1.37,0],left_wrist:[-1.52,.83,0],_left_hand_tip:[-1.79,.47,0],right_shoulder:[.58,1.92,0],right_elbow:[1.12,1.37,0],right_wrist:[1.52,.83,0],_right_hand_tip:[1.79,.47,0],left_hip:[-.34,.18,0],left_knee:[-.38,-.98,0],left_ankle:[-.4,-2.02,.05],_left_toe:[-.4,-2.02,.48],right_hip:[.34,.18,0],right_knee:[.38,-.98,0],right_ankle:[.4,-2.02,.05],_right_toe:[.4,-2.02,.48]};
const bones=[["head","_neck"],["_neck","_chest"],["_chest","waist"],["waist","_pelvis"],["_chest","left_shoulder"],["left_shoulder","left_elbow"],["left_elbow","left_wrist"],["left_wrist","_left_hand_tip"],["_chest","right_shoulder"],["right_shoulder","right_elbow"],["right_elbow","right_wrist"],["right_wrist","_right_hand_tip"],["_pelvis","left_hip"],["left_hip","left_knee"],["left_knee","left_ankle"],["left_ankle","_left_toe"],["_pelvis","right_hip"],["right_hip","right_knee"],["right_knee","right_ankle"],["right_ankle","_right_toe"]];
const virtualIds=new Set(["_neck","_chest","_pelvis"]);
const structuralIds=new Set(["_face","_left_hand_tip","_right_hand_tip","_left_toe","_right_toe"]);

const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(36,1,.1,100),renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
camera.position.set(5.8,3.3,8.7);renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;viewport.appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.25,0);controls.enableDamping=true;controls.dampingFactor=.07;controls.minDistance=5;controls.maxDistance=18;
scene.add(new THREE.HemisphereLight(0xfffbef,0x786f62,2.1));const light=new THREE.DirectionalLight(0xffffff,2.5);light.position.set(4,7,6);scene.add(light);
const grid=new THREE.GridHelper(12,24,0xbeb5a2,0xd9d1c0);grid.position.y=-2.13;grid.material.transparent=true;grid.material.opacity=.48;scene.add(grid);
const group=new THREE.Group(),joints=new Map(),boneMeshes=[];scene.add(group);
const trails={body:[],node:[]};let latestPositions={};
const trailMaterials={body:new THREE.LineBasicMaterial({color:0x1eb7aa,transparent:true,opacity:.9}),node:new THREE.LineBasicMaterial({color:0xf06b4f,transparent:true,opacity:.95})};
const trailLines={body:new THREE.Line(new THREE.BufferGeometry(),trailMaterials.body),node:new THREE.Line(new THREE.BufferGeometry(),trailMaterials.node)};
scene.add(trailLines.body,trailLines.node);
const sphere=new THREE.SphereGeometry(1,24,16),sensorMarker=new THREE.ConeGeometry(.11,.25,3),cylinder=new THREE.CylinderGeometry(1,1,1,18),mat=(color,r=.45)=>new THREE.MeshStandardMaterial({color,roughness:r,metalness:.05});
Object.keys(rest).filter(id=>!structuralIds.has(id)).forEach(id=>{const virt=virtualIds.has(id),mesh=new THREE.Mesh(virt?sphere:sensorMarker,mat(virt?COLORS.virtual:COLORS.offline));if(virt)mesh.scale.setScalar(.065);group.add(mesh);joints.set(id,mesh)});
bones.forEach(([start,end])=>{const mesh=new THREE.Mesh(cylinder,mat(COLORS.bone,.7));mesh.userData={start,end};group.add(mesh);boneMeshes.push(mesh)});
const headShape=new THREE.Mesh(new THREE.SphereGeometry(1,24,18),new THREE.MeshStandardMaterial({color:COLORS.bone,transparent:true,opacity:.22,wireframe:true}));headShape.scale.set(.2,.27,.19);group.add(headShape);
const faceMarker=new THREE.Mesh(new THREE.ConeGeometry(.075,.22,3),mat(COLORS.bone,.7));faceMarker.rotation.x=Math.PI/2;group.add(faceMarker);
const vec=a=>new THREE.Vector3(...a),sensor=id=>nodes.find(n=>n.id===id);
function quat(a){const[w,x,y,z]=a||[1,0,0,0];return new THREE.Quaternion(x,y,z,w).normalize()}
function avg(...points){const out=new THREE.Vector3();points.forEach(p=>out.add(p));return out.multiplyScalar(1/points.length)}

// Fixed bone lengths + measured orientations. Missing data uses rest pose;
// there is no random motion and no acceleration double integration.
function solvePose(){
  const p=Object.fromEntries(Object.entries(rest).map(([id,v])=>[id,vec(v)]));
  const segment=(parent,child,driver)=>{const d=vec(rest[child]).sub(vec(rest[parent])),n=sensor(driver);if(n?.source==="real"&&n.valid)d.applyQuaternion(quat(n.quaternion));p[child]=p[parent].clone().add(d)};
  segment("waist","_pelvis","waist");segment("waist","_chest","waist");segment("_chest","_neck","waist");segment("_neck","head","head");segment("head","_face","head");
  segment("_chest","left_shoulder","left_shoulder");segment("left_shoulder","left_elbow","left_shoulder");segment("left_elbow","left_wrist","left_elbow");segment("left_wrist","_left_hand_tip","left_wrist");
  segment("_chest","right_shoulder","right_shoulder");segment("right_shoulder","right_elbow","right_shoulder");segment("right_elbow","right_wrist","right_elbow");segment("right_wrist","_right_hand_tip","right_wrist");
  segment("_pelvis","left_hip","left_hip");segment("left_hip","left_knee","left_hip");segment("left_knee","left_ankle","left_knee");segment("left_ankle","_left_toe","left_ankle");
  segment("_pelvis","right_hip","right_hip");segment("right_hip","right_knee","right_hip");segment("right_knee","right_ankle","right_knee");segment("right_ankle","_right_toe","right_ankle");
  p._chest.x=avg(p.left_shoulder,p.right_shoulder).x;p._neck.x=p._chest.x;p._pelvis.x=avg(p.left_hip,p.right_hip).x;return p;
}
function placeBone(mesh,a,b){const d=b.clone().sub(a),length=d.length();mesh.position.copy(a).add(b).multiplyScalar(.5);mesh.scale.set(.052,length,.052);mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize())}
function updateSkeleton(){const p=solvePose();latestPositions=p;joints.forEach((mesh,id)=>{mesh.position.copy(p[id]);if(virtualIds.has(id))mesh.material.color.setHex(COLORS.virtual);else{const n=sensor(id);mesh.material.color.setHex(n?.source==="real"&&n.valid?COLORS.online:COLORS.offline);mesh.quaternion.copy(n?.source==="real"&&n.valid?quat(n.quaternion):new THREE.Quaternion())}});boneMeshes.forEach(m=>placeBone(m,p[m.userData.start],p[m.userData.end]));headShape.position.copy(p.head);const head=sensor("head"),hq=head?.source==="real"&&head.valid?quat(head.quaternion):new THREE.Quaternion();headShape.quaternion.copy(hq);faceMarker.position.copy(p.head).lerp(p._face,.82);faceMarker.quaternion.copy(hq).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI/2,0,0)))}
function animate(){const w=viewport.clientWidth,h=viewport.clientHeight,ratio=renderer.getPixelRatio();if(w&&h&&(renderer.domElement.width!==Math.round(w*ratio)||renderer.domElement.height!==Math.round(h*ratio))){renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}updateSkeleton();controls.update();renderer.render(scene,camera);requestAnimationFrame(animate)}

function size(c){const r=c.getBoundingClientRect(),d=devicePixelRatio||1;if(c.width!==r.width*d||c.height!==r.height*d){c.width=r.width*d;c.height=r.height*d;c.getContext("2d").setTransform(d,0,0,d,0,0)}return r}
const magnitude=v=>Math.sqrt((v||[]).reduce((sum,n)=>sum+n*n,0));
function addHistory(n){if(!n||n.source!=="real")return;[["acc",n.accel],["gyro",n.gyro],["mag",n.mag]].forEach(([key,v])=>{history[key].push(magnitude(v));if(history[key].length>maxPoints)history[key].shift()})}
function drawSignals(){const r=size(signal);sctx.clearRect(0,0,r.width,r.height);sctx.strokeStyle="#cfc5ae";sctx.lineWidth=1;for(let i=1;i<5;i++){let y=i*r.height/5;sctx.beginPath();sctx.moveTo(22,y);sctx.lineTo(r.width-22,y);sctx.stroke()}[[history.acc,"#1eb7aa"],[history.gyro,"#2f75ee"],[history.mag,"#f06b4f"]].forEach(([arr,color])=>{if(arr.length<2)return;const max=Math.max(...arr,1),min=Math.min(...arr,0),range=max-min||1;sctx.strokeStyle=color;sctx.lineWidth=2.2;sctx.beginPath();arr.forEach((v,i)=>{const x=22+i*(r.width-44)/(maxPoints-1),y=r.height-18-(v-min)/range*(r.height-38);i?sctx.lineTo(x,y):sctx.moveTo(x,y)});sctx.stroke()});requestAnimationFrame(drawSignals)}
function renderNodes(){const grid=$("#nodeGrid");if(!grid.children.length&&nodes.length){nodes.forEach(n=>{const el=document.createElement("div");el.className="node-card";el.dataset.id=n.id;el.innerHTML=`<i></i><div><b>${n.name}</b><br><em>${n.source==="real"?"真实 IMU":"静止模拟"}</em></div><span>—</span>`;grid.append(el)});$("#nodeSelect").innerHTML=nodes.map(n=>`<option value="${n.id}" ${n.id==="right_wrist"?"selected":""}>${n.name}</option>`).join("")}nodes.forEach(n=>{const el=grid.querySelector(`[data-id="${n.id}"]`);if(!el)return;el.classList.toggle("real",n.source==="real"&&n.valid);el.classList.toggle("offline",!n.valid);el.querySelector("span").textContent=n.source==="real"?(n.valid?"实时 · ACTIVE":"等待数据"):"固定姿态"})}
function setTrail(kind,point){const list=trails[kind],previous=list[list.length-1];if(previous&&previous.distanceToSquared(point)<.000004)return;list.push(point.clone());if(list.length>600)list.shift();trailLines[kind].geometry.dispose();trailLines[kind].geometry=new THREE.BufferGeometry().setFromPoints(list)}
function clearTrails(){trails.body.length=trails.node.length=0;Object.values(trailLines).forEach(line=>{line.geometry.dispose();line.geometry=new THREE.BufferGeometry()})}
function updateTrails(data){const body=new THREE.Vector3(...(data.trajectory?.body||[0,0,0]));group.position.copy(body);setTrail("body",new THREE.Vector3(rest._pelvis[0],rest._pelvis[1],rest._pelvis[2]).add(body));const id=$("#nodeSelect").value||"right_wrist",position=latestPositions[id];if(position)setTrail("node",position.clone().add(body));trailLines.body.visible=$("#bodyTrailToggle").checked;trailLines.node.visible=$("#nodeTrailToggle").checked}
function update(data){nodes=data.nodes||nodes;stats=data.stats||stats;renderNodes();const real=nodes.find(n=>n.id==="right_wrist");addHistory(real);updateSkeleton();updateTrails(data);$("#rate").textContent=(stats.frame_rate||0).toFixed(1);$("#lossRate").textContent=(stats.estimated_loss_rate||0).toFixed(2)+"%";$("#packetAge").dataset.latest=data.latest_packet_at||"";$("#badFrames").textContent=stats.invalid_frames||0;$("#portBadge").textContent=stats.port||"COM21";$("#serialMessage").textContent=stats.message||"等待连接串口";$("#realOnline").textContent=real?.valid?1:0;$("#recordState").textContent=stats.recording?"● 正在记录":"未记录";$("#recordDetails").textContent=stats.recording?`${stats.record_duration_s.toFixed(1)} 秒 · ${stats.record_rows} 行 · ${stats.record_path}`:(stats.record_path?`已保存至 ${stats.record_path}`:"尚未开始记录");$("#recordBtn").textContent=stats.recording?"停止记录":"开始记录";$("#recordBtn").classList.toggle("recording",!!stats.recording);$("#connectBtn").textContent=stats.serial_status==="connected"?"断开串口":"连接串口";["#serviceState",".status-strip"].forEach(s=>{$(s).classList.toggle("connected",stats.serial_status==="connected");$(s).classList.toggle("error",stats.serial_status==="error")});$("#serviceState span").textContent=stats.serial_status==="connected"?"实时数据已连接":"接收服务已就绪"}
const send=(action,extra={})=>ws?.readyState===WebSocket.OPEN&&ws.send(JSON.stringify({action,...extra}));function openSocket(){const proto=location.protocol==="https:"?"wss":"ws";ws=new WebSocket(`${proto}://${location.host}/ws`);ws.onmessage=e=>update(JSON.parse(e.data));ws.onclose=()=>setTimeout(openSocket,1500)}openSocket();
$("#connectBtn").onclick=()=>send(stats.serial_status==="connected"?"disconnect":"connect");$("#recordBtn").onclick=()=>send(stats.recording?"stop_recording":"start_recording",{node_id:$("#nodeSelect").value});$("#zeroBtn").onclick=()=>send("zero");$("#resetViewBtn").onclick=()=>{camera.position.set(5.8,3.3,8.7);controls.target.set(0,.25,0);controls.update()};$("#clearTrailsBtn").onclick=clearTrails;$("#bodyTrailToggle").onchange=()=>trailLines.body.visible=$("#bodyTrailToggle").checked;$("#nodeTrailToggle").onchange=()=>trailLines.node.visible=$("#nodeTrailToggle").checked;$("#nodeSelect").onchange=()=>{trails.node.length=0;trailLines.node.geometry.dispose();trailLines.node.geometry=new THREE.BufferGeometry();send("select_record_node",{node_id:$("#nodeSelect").value})};setInterval(()=>{const latest=Number($("#packetAge").dataset.latest);$("#packetAge").textContent=latest?Math.max(0,Date.now()-latest*1000).toFixed(0)+" ms":"—"},200);
const recordsDialog=$("#recordsDialog"),sessionSelect=$("#recordSessionSelect"),fileSelect=$("#recordFileSelect");let recordingItems=[],activeSession=null;
const formatBytes=n=>n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(1)} KB`:`${(n/1048576).toFixed(1)} MB`;
async function loadRecordingCatalog(){const response=await fetch("/api/recordings");if(!response.ok)throw new Error("无法读取记录列表");const data=await response.json();recordingItems=data.items||[];activeSession=(data.active||"").split(/[\\/]/).pop();sessionSelect.innerHTML="";recordingItems.forEach(item=>{const option=document.createElement("option");option.value=item.id;option.textContent=`${item.id}${item.kind==="legacy_jsonl"?"（旧格式）":""}${item.id===activeSession?"（记录中）":""}`;sessionSelect.append(option)});populateRecordFiles();return recordingItems}
function populateRecordFiles(){const item=recordingItems.find(entry=>entry.id===sessionSelect.value);fileSelect.innerHTML="";(item?.files||[]).forEach(file=>{const option=document.createElement("option");option.value=file.name;option.textContent=`${file.name} · ${formatBytes(file.size)}`;fileSelect.append(option)});const canPreview=item?.kind==="csv_session";$("#refreshPreviewBtn").disabled=!canPreview;$("#dialogExportBtn").disabled=!item||item.id===activeSession;$("#previewEmpty").style.display=canPreview?"none":"grid"}
async function previewRecording(){const session=sessionSelect.value,file=fileSelect.value;if(!session||!file)return;const response=await fetch(`/api/recordings/${encodeURIComponent(session)}/preview?file=${encodeURIComponent(file)}&limit=100`);if(!response.ok){$("#previewMeta").textContent="预览失败";return}const data=await response.json(),head=$("#previewTable thead"),body=$("#previewTable tbody");head.innerHTML="";body.innerHTML="";const headerRow=document.createElement("tr");data.header.forEach(value=>{const th=document.createElement("th");th.textContent=value;headerRow.append(th)});head.append(headerRow);data.rows.forEach(row=>{const tr=document.createElement("tr");row.forEach(value=>{const td=document.createElement("td");td.textContent=value;tr.append(td)});body.append(tr)});$("#previewMeta").textContent=`${data.file}\n${formatBytes(data.size)} · 共 ${data.total_rows} 行\n时间 ${data.first_timestamp||"—"} 至 ${data.last_timestamp||"—"}`;$("#previewEmpty").style.display=data.rows.length?"none":"grid"}
function exportSession(id=sessionSelect.value){if(!id||id===activeSession)return;window.location.href=`/api/recordings/${encodeURIComponent(id)}/download`}
async function openRecords(){try{await loadRecordingCatalog();recordsDialog.showModal();if(recordingItems.length)await previewRecording()}catch(error){alert(error.message)}}
$("#previewRecordsBtn").onclick=openRecords;$("#closeRecordsBtn").onclick=()=>recordsDialog.close();$("#refreshPreviewBtn").onclick=previewRecording;$("#dialogExportBtn").onclick=()=>exportSession();sessionSelect.onchange=async()=>{populateRecordFiles();if(recordingItems.find(item=>item.id===sessionSelect.value)?.kind==="csv_session")await previewRecording()};fileSelect.onchange=previewRecording;$("#exportRecordsBtn").onclick=async()=>{try{await loadRecordingCatalog();const item=recordingItems.find(entry=>entry.id!==activeSession);if(item)exportSession(item.id);else alert("暂无可导出的已完成记录")}catch(error){alert(error.message)}};
if(new URLSearchParams(location.search).get("records")==="1")openRecords();
animate();drawSignals();

const transportSelect=$("#transportSelect"),wifiHost=$("#wifiHost"),wifiPort=$("#wifiPort");
const baseUpdate=update;
update=function(data){
  baseUpdate(data);
  const transport=data.stats?.transport||transportSelect.value;
  const connected=data.stats?.serial_status==="connected";
  if(document.activeElement!==transportSelect)transportSelect.value=transport;
  if(document.activeElement!==wifiHost&&data.stats?.host)wifiHost.value=data.stats.host;
  if(document.activeElement!==wifiPort&&data.stats?.tcp_port)wifiPort.value=data.stats.tcp_port;
  const wifi=transport==="wifi";
  $("#portBadge").textContent=wifi?`Wi-Fi · ${data.stats?.host}:${data.stats?.tcp_port}`:`USB串口 · ${data.stats?.port||"COM21"}`;
  $("#connectBtn").textContent=connected?"断开设备":"连接设备";
  transportSelect.disabled=connected;
  wifiHost.disabled=connected||!wifi;
  wifiPort.disabled=connected||!wifi;
};
function updateTransportInputs(){
  const wifi=transportSelect.value==="wifi";
  wifiHost.disabled=!wifi;
  wifiPort.disabled=!wifi;
}
transportSelect.onchange=updateTransportInputs;
$("#connectBtn").onclick=()=>{
  if(stats.serial_status==="connected")send("disconnect");
  else if(transportSelect.value==="wifi")send("connect",{transport:"wifi",host:wifiHost.value.trim(),tcp_port:Number(wifiPort.value)});
  else send("connect",{transport:"serial",device:"COM21"});
};
updateTransportInputs();
