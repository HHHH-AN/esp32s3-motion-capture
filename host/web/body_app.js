"use strict";
(function() {
  const byId=id=>document.getElementById(id);
  const labels={unmeasured:"未测量 · 局部零姿态",uninitialized:"在线 · 未初始化",online:"已初始化",delayed:"延迟",stale:"失鲜 · 保持",disconnected:"持续断线",conflict:"位置冲突 · 隔离",invalid:"异常 · 拒绝"};
  let socket,state=null,selectedSlot=null,prepared=false,selectedDevice="",lastDeviceOptions="",lastSourceKey="",lastBindingKey="",slotConfigKey="",endpointKey="",sessionKey="",lastMode="LIVE",lastProcessingKey="";
  const views=[new BodyView.BodyView(byId("bodyFixed"),{kind:"fixed",onSelect:selectSlot}),new BodyView.BodyView(byId("bodyTranslated"),{kind:"translated",onSelect:selectSlot}),new BodyView.BodyView(byId("bodyBoards"),{kind:"boards",onSelect:selectSlot})];
  const api={enabled:true,connected:false,command,latest:()=>state};window.BodyApp=api;
  function command(action,extra={}) {
    const aliases={start_recording:"record_start",stop_recording:"record_stop"};
    if(action==="zero"){byId("bodyInitBegin").click();byId("bodyInitBegin").scrollIntoView({behavior:"smooth",block:"center"});return;}
    if(!api.connected){byId("message").textContent="服务未连接，命令未发送";return;}
    socket.send(JSON.stringify({action:aliases[action]||action,device_id:state?.selected_device_id||selectedDevice||undefined,...extra}));
  }
  function selectSlot(slot,deviceId) {
    if(slot)selectedSlot=slot;
    const found=state?.slots?.find(item=>(item.id||item.slot)===slot);
    if(deviceId||found?.device_id){selectedDevice=deviceId||found.device_id;command("select",{device_id:selectedDevice});}
    renderSlots();draw();
  }
  function optionList(select,items,value) {
    select.replaceChildren();for(const item of items){const option=document.createElement("option");option.value=item.id;option.textContent=item.label;select.append(option);}if(items.some(item=>item.id===value))select.value=value;
  }
  function bodySlotId(slot){return slot.id||slot.slot||slot.body_slot;}
  function renderSlots() {
    const slots=state?.slots||[],key=slots.map(slot=>`${bodySlotId(slot)}:${slot.name}`).join("|");
    if(slots.length&&api.layoutCount!==slots.length){api.layoutCount=slots.length;const count=byId("bodySimCount").value,counts=[...new Set([1,Math.min(3,slots.length),slots.length])];optionList(byId("bodySimCount"),counts.map(n=>({id:String(n),label:`${n} 个节点`})),count);}
    if(key!==slotConfigKey){slotConfigKey=key;byId("bodySlots").replaceChildren();for(const slot of slots){const button=document.createElement("button");button.type="button";button.dataset.slot=bodySlotId(slot);button.className="body-slot";const name=document.createElement("strong"),status=document.createElement("span"),detail=document.createElement("small");button.append(name,status,detail);button.onclick=()=>selectSlot(bodySlotId(slot));byId("bodySlots").append(button);}const options=slots.map(slot=>({id:bodySlotId(slot),label:`${slot.name||bodySlotId(slot)} / ${bodySlotId(slot)}`}));optionList(byId("bodyBinding"),options,selectedSlot);optionList(byId("bodySimSlot"),options,"left_forearm");}
    for(const slot of slots){const id=bodySlotId(slot),button=[...byId("bodySlots").children].find(item=>item.dataset.slot===id);if(!button)continue;button.className=`body-slot ${slot.status||"unmeasured"}${selectedSlot===id?" selected":""}`;button.setAttribute("aria-pressed",String(selectedSlot===id));button.children[0].textContent=slot.name||id;button.children[1].textContent=labels[slot.status]||slot.status||"未测量";const age=slot.age_ms==null?"":` · ${Math.round(slot.age_ms)} ms`;button.children[2].textContent=(slot.device_id||"无设备")+` · ${slot.source==="real"?"硬件":slot.source?.startsWith("simulation")?"模拟":"无来源"}`+age+(slot.override?" · 临时覆盖":"")+(slot.conflict?" · 冲突":"");}
  }
  function renderEndpoints() {
    const endpoints=state?.endpoints||[],key=JSON.stringify(endpoints.map(item=>[item.endpoint_id||item.id,item.status,item.connected,item.error,item.message,item.device_id]));if(key===endpointKey)return;endpointKey=key;
    const container=byId("bodyEndpoints");container.replaceChildren();
    if(!endpoints.length){const empty=document.createElement("p");empty.className="hint";empty.textContent="尚无端点。上方选择 USB / Wi-Fi，再手动添加；不会自动连接板卡。";container.append(empty);}
    for(const endpoint of endpoints){const row=document.createElement("div");row.className="endpoint-row";const text=document.createElement("span"),detail=document.createElement("small"),button=document.createElement("button"),id=endpoint.endpoint_id||endpoint.id;text.textContent=id||"端点";detail.textContent=`${endpoint.transport||""} · ${endpoint.device||endpoint.host||endpoint.endpoint||""}${endpoint.tcp_port?":"+endpoint.tcp_port:""} · ${endpoint.status||(endpoint.connected?"connected":"disconnected")} ${endpoint.error||endpoint.message||""}`;button.textContent="断开此端点";button.disabled=endpoint.simulation||(!endpoint.connected&&!["connecting","connected"].includes(endpoint.status));button.onclick=()=>command("disconnect",{endpoint_id:id});row.append(text,detail,button);container.append(row);}
  }
  function renderDevices() {
    const devices=state?.devices||[],key=devices.map(item=>`${item.device_id}:${item.body_slot}:${item.override}`).join("|");
    selectedDevice=state.selected_device_id||selectedDevice;
    if(key!==lastDeviceOptions){lastDeviceOptions=key;optionList(byId("bodyDevice"),[{id:"",label:"选择物理设备"},...devices.map(item=>({id:item.device_id,label:`${item.device_id} · ${item.body_slot||"未绑定"}${item.override?" · 临时覆盖":""}`}))],selectedDevice);}
    if([...byId("bodyDevice").options].some(option=>option.value===selectedDevice))byId("bodyDevice").value=selectedDevice;
    const device=state.selected_node||devices.find(item=>item.device_id===selectedDevice)||null;
    const sourceKey=JSON.stringify([device?.device_id,device?.endpoint_id,device?.endpoint_ids]);
    if(sourceKey!==lastSourceKey){lastSourceKey=sourceKey;optionList(byId("bodyPrimarySource"),(device?.endpoint_ids||[]).map(id=>({id,label:id})),device?.endpoint_id);}
    if(device?.body_slot&&!selectedSlot)selectedSlot=device.body_slot;
    const bindingKey=JSON.stringify([device?.device_id,device?.body_slot]);if(bindingKey!==lastBindingKey){lastBindingKey=bindingKey;if(device?.body_slot)byId("bodyBinding").value=device.body_slot;}
    byId("bodySelectedDetails").textContent=device?`${device.device_id} · ${device.body_slot||"未绑定，不驱动骨架"} · 来源 ${device.source||"未知"} · 会话 ${device.boot_id||"旧协议未知"} · 绑定 ${device.binding_source||"未指定"}${device.override?"（网页临时覆盖，已记录）":""} · 固件 ${device.firmware_version||"未知"} / 配置 ${device.config_version||"未知"}`:"尚未选择设备。IP/COM 只表示连接地址；未指定身体位置时只作诊断。";
    byId("bodyDiagnosticLayers").textContent=device?JSON.stringify({device_id:device.device_id,body_slot:device.body_slot,unknown_slot:device.unknown_slot,boot_id:device.boot_id,source:device.source,endpoint:device.endpoint_id,endpoints:device.endpoint_ids,quality:device.quality,stability:device.stability,raw_sample:device.raw_sample,sensor_flags:device.sensor_flags,last_error:device.last_error,initialized:device.initialized,reference:device.reference||device.calibration,reference_reason:device.reference_reason,quaternion:device.quaternion,coordinates:device.coordinates,firmware_version:device.firmware_version,config_version:device.config_version},null,2):"等待选择设备";
    window.renderBodyDiagnostic?.(device,state);
    const processingKey=JSON.stringify([device?.device_id,device?.processing_profile,state.attitude_config?.config_version]);
    if(processingKey!==lastProcessingKey){lastProcessingKey=processingKey;const profiles=state.attitude_config?.profiles||{};optionList(byId("bodyProcessing"),Object.entries(profiles).map(([id,value])=>({id,label:value.name||id})),device?.processing_profile);}
    if(document.activeElement!==byId("bodyHold"))byId("bodyHold").checked=device?.stability?.enabled??true;
    const phases={idle:"未校准",waiting:"等待放稳",collecting:"连续采样",complete:"已完成",failed:"超时失败",cancelled:"已取消"},stability=device?.stability;
    byId("bodyProcessingStatus").textContent=device?`融合 ${device.processing_profile||device.fusion_version||"未知"} · 算法 ${device.fusion_version||"未知"} · 校准 ${phases[stability?.phase]||stability?.phase||"未开始"} · 重试 ${stability?.retries||0}。${stability?.magnetic_message||""} 轴映射仍以当前设备设置为准。`:"选择设备后可切换融合策略；磁场原值保留。重力校正不等于消除长期航向漂移。";
  }
  function renderWorkflow() {
    const init=state.initialization||{},recording=!!state.recording?.active,replaying=state.mode==="REPLAY",locked=recording||replaying;
    const status=init.status||init.state||"未初始化";byId("bodyInitStatus").textContent=status;
    byId("bodyInitDetails").textContent=init.message||`已初始化 ${(state.devices||[]).filter(device=>device.initialized).length} 个设备；仅已标定范围参与驱动。重新佩戴、换人、换板、改位置或融合参考重置后须重新初始化。`;
    byId("bodyInitBegin").disabled=locked||status==="collecting";byId("bodyInitConfirm").disabled=locked||status!=="prepared";
    for(const id of ["bodyBind","bodyBindingClear","bodyChooseSource","bodyPrimarySource","bodyRewear","bodySimStart","bodySimStop","bodyPositionApply"]){byId(id).disabled=locked;}
    byId("bodyApplyProcessing").disabled=byId("bodyProcessing").disabled=byId("bodyHold").disabled=locked||!state.selected_node;
    byId("cancelCalibration").disabled=locked||!state.selected_node?.stability?.calibrating;
    byId("calibrate").disabled=locked||!state.selected_node?.valid||!state.selected_node?.raw_sample||!!state.selected_node?.stability?.calibrating;
    byId("bodyRecord").textContent=recording?"停止并保存记录":"开始记录";byId("bodyRecord").disabled=replaying;
    byId("bodyRecordState").textContent=recording?`录制中 · ${state.recording.session||""}`:replaying?"回放中 · 实时不覆盖":"未录制";
    if(state.recording?.error)byId("bodyRecordDetails").textContent="记录异常："+state.recording.error;
    else if(recording)byId("bodyRecordDetails").textContent=`保存 ${state.recording.session||""} · 原始 ${state.recording.counts?.samples??0} · 骨架帧 ${state.recording.counts?.body_frames??0}；绑定、初始化及标定已锁定，先停止再修改。`;
    else if(replaying)byId("bodyRecordDetails").textContent="回放保存的完整骨架帧；实时连接可以保留，但实时数据不驱动模型。新算法重算属于独立分析。";
    else byId("bodyRecordDetails").textContent="会话保存到 host/recordings；原始采样、融合、实际骨架帧、身份绑定和版本化配置分别保存。录制与回放互斥。";
    const replay=state.replay||{},duration=replay.duration_s??replay.duration??0,time=replay.time_s??replay.position_s??0;
    byId("bodyReplaySeek").max=duration;byId("bodyReplaySeek").disabled=!replaying;if(document.activeElement!==byId("bodyReplaySeek"))byId("bodyReplaySeek").value=time;
    byId("bodyReplayTime").textContent=`${Number(time).toFixed(2)} / ${Number(duration).toFixed(2)} s`;
    byId("bodyReplayOpen").disabled=recording||!byId("bodySessions").value;
    for(const id of ["bodyReplayPlay","bodyReplayPause","bodyReplayClose"]){byId(id).disabled=!replaying;}
    const position=state.position||{},source=position.source||"off";byId("bodyPositionStatus").textContent=`位置来源：${source}。${source==="experimental"?"实验惯性积分会漂移；不是可靠绝对定位。":source==="simulated"?"模拟位置，不是真实测量。":"固定根部与位置估算分离。"}`;
  }
  function update(next) {
    state=next;api.state=next;
    byId("message").textContent=next.message||"等待输入";byId("bodyMode").textContent=`${next.mode||"LIVE"}${next.mode==="REPLAY"?" · 保存姿态回放":" · 实时来源"}`;
    byId("bodyMode").className="badge"+(next.mode==="REPLAY"?" simulation":"");
    const devices=next.devices||[],real=devices.filter(device=>device.source==="real"&&device.valid).length,sim=devices.filter(device=>device.source?.startsWith("simulation")&&device.valid).length;
    byId("bodyCounts").textContent=`硬件有效 ${real} · 模拟 ${sim} · 已初始化 ${devices.filter(device=>device.initialized).length}`;
    if(lastMode!==next.mode){views.forEach(view=>view.clearTrail());lastMode=next.mode;}
    renderDevices();renderSlots();renderEndpoints();renderWorkflow();
  }
  function draw() {
    if(!state)return;
    const position=state.position||{},offset=position.position||position.value||[0,0,0],frame=state.body_frame||{};
    for(const view of views)view.draw(frame,{selectedSlot,devices:state.devices||[],position:offset,positionSource:position.source||"off",mode:state.mode,epoch:`${state.mode}:${state.replay?.session||""}:${state.epoch||""}`});
  }
  function connect() {
    socket=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/ws/body`);
    socket.onopen=()=>{api.connected=true;byId("socketState").textContent="统一接收服务在线";byId("socketState").className="badge online";byId("connect").disabled=false;refreshSessions();};
    socket.onmessage=event=>{try{update(JSON.parse(event.data));}catch(error){console.error(error);byId("message").textContent="无法显示服务状态："+error.message;}};
    socket.onclose=()=>{api.connected=false;byId("socketState").textContent="服务断开，正在重连";byId("socketState").className="badge error";byId("connect").disabled=true;setTimeout(connect,1500);};
  }
  byId("connect").onclick=()=>{const transport=byId("transport").value,device=byId("serialPort").value;if(transport==="serial"&&!device){byId("message").textContent="请选择当前板卡实际串口";return;}const extra={endpoint_id:byId("endpointName").value.trim()||"node-1",transport,host:byId("host").value.trim(),tcp_port:Number(byId("tcpPort").value),device};command("connect",extra);try{localStorage.setItem("imu-connection",JSON.stringify(extra));}catch{}};
  byId("bodyDevice").onchange=()=>{selectedDevice=byId("bodyDevice").value;const device=state?.devices?.find(item=>item.device_id===selectedDevice);selectedSlot=device?.body_slot||null;command("select",{device_id:selectedDevice});};
  byId("bodyBind").onclick=()=>{if(!byId("bodyDevice").value)return;selectedSlot=byId("bodyBinding").value;command("bind",{device_id:byId("bodyDevice").value,body_slot:selectedSlot,override:true});};
  byId("bodyBindingClear").onclick=()=>command("bind",{device_id:byId("bodyDevice").value,body_slot:null,override:false});
  byId("bodyChooseSource").onclick=()=>command("choose_source",{endpoint_id:byId("bodyPrimarySource").value});
  byId("bodyRewear").onclick=()=>command("reset_reference");
  byId("bodyApplyProcessing").onclick=()=>command("set_processing",{profile:byId("bodyProcessing").value});
  byId("bodyHold").onchange=()=>command("set_stability",{enabled:byId("bodyHold").checked});
  byId("cancelCalibration").onclick=()=>command("cancel_calibration");
  byId("bodyInitBegin").onclick=()=>{prepared=true;command("initialize",{stage:"begin"});renderWorkflow();};
  byId("bodyInitConfirm").onclick=()=>{if(!prepared)return;command("initialize",{stage:"confirm"});};
  byId("bodySimStart").onclick=()=>command("simulate",{path:byId("bodySimPath").value,count:Number(byId("bodySimCount").value),slot:byId("bodySimSlot").value,axis:byId("bodySimAxis").value,angle_deg:Number(byId("bodySimAngle").value)});
  byId("bodySimStop").onclick=()=>command("simulate_stop");
  byId("bodyPositionApply").onclick=()=>command("position",{source:byId("bodyPositionSource").value,position:["X","Y","Z"].map(axis=>Number(byId("bodyPosition"+axis).value))});
  byId("bodyViewMode").onchange=()=>{const mode=byId("bodyViewMode").value;for(const element of byId("bodyViews").children)element.hidden=mode!=="all"&&element.dataset.view!==mode;byId("bodyViews").classList.toggle("single-view",mode!=="all");draw();};
  byId("bodyResetViews").onclick=()=>views.forEach(view=>view.reset());byId("bodyClearTrail").onclick=()=>views.forEach(view=>view.clearTrail());
  byId("bodyRecord").onclick=()=>{const stopping=state?.recording?.active;command(stopping?"record_stop":"record_start");if(stopping)setTimeout(refreshSessions,250);};
  byId("record").onclick=()=>byId("bodyRecord").click();byId("records").textContent="完整动作会话列表";byId("records").onclick=()=>{refreshSessions();byId("bodySessions").scrollIntoView({behavior:"smooth",block:"center"});};
  async function refreshSessions() {try{const response=await fetch("/api/body/recordings");if(!response.ok)throw new Error("读取会话列表失败");const result=await response.json(),items=result.items||[],options=[{id:"",label:"请选择已保存会话"},...items.map(item=>({id:item.id||item.session,label:`${item.id||item.session}${item.incomplete?" · 未完整结束":""}`}))],old=byId("bodySessions").value;optionList(byId("bodySessions"),options,old||options[1]?.id||"");sessionKey=JSON.stringify(items);if(state)renderWorkflow();}catch(error){byId("bodyRecordDetails").textContent=error.message;}}
  byId("bodyRefreshSessions").onclick=refreshSessions;byId("bodySessions").onchange=()=>state&&renderWorkflow();
  byId("bodyReplayOpen").onclick=()=>command("replay_open",{session:byId("bodySessions").value});byId("bodyReplayPlay").onclick=()=>command("replay_play");byId("bodyReplayPause").onclick=()=>command("replay_pause");byId("bodyReplayClose").onclick=()=>command("replay_close");byId("bodyReplaySeek").oninput=()=>command("replay_seek",{time_s:Number(byId("bodyReplaySeek").value)});
  function animate(){draw();requestAnimationFrame(animate);}connect();requestAnimationFrame(animate);
})();
