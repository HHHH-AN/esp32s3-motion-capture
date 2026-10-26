"use strict";
// One view onto the existing body runtime. This controller never opens a
// transport or invents successful calibration from a local timer.
(function(root) {
  const byId=id=>document.getElementById(id), selected=new Set();
  const statusLabels={idle:"尚未开始",prepared:"已准备",capturing:"正在采集",collecting:"正在采集",neutral_ready:"中立采样完成",neutral_complete:"中立采样完成",ready_for_forward:"等待前举定姿",candidate:"拟合通过，待应用",ready:"拟合通过，待应用",fitted:"拟合通过，待应用",complete:"标定已应用",applied:"标定已应用",failed:"标定失败，需重采",cancelled:"已取消",invalidated:"标定已失效"};
  let state=null,deviceKey="",hasInitialSelection=false;
  const rows=new Map();
  function command(action,extra={}) {
    if(!root.BodyApp?.connected)return;
    root.BodyApp.command(action,extra);
  }
  function deviceIds(){return [...selected];}
  function guidedRole(role){return /^(left|right)_(upper_arm|forearm|hand)$/.test(role||"");}
  function number(value,digits=2){return Number.isFinite(value)?value.toFixed(digits):"—";}
  function residual(device) {
    const measured=device.corrected_gyro_dps||device.residual_gyro_dps;
    if(Array.isArray(measured)&&measured.length===3)return Math.hypot(...measured);
    const gyro=device.gyro,bias=device.stability?.gyro_bias_dps||[0,0,0];
    return Array.isArray(gyro)&&gyro.length===3?Math.hypot(...gyro.map((v,i)=>v-(bias[i]||0))):null;
  }
  function renderDevices(locked) {
    const devices=state.devices||[],key=devices.map(d=>`${d.device_id}:${d.body_slot}`).join("|");
    if(!hasInitialSelection&&devices.some(d=>guidedRole(d.body_slot))){const preferred=devices.find(d=>d.device_id===state.selected_device_id&&guidedRole(d.body_slot))||devices.find(d=>guidedRole(d.body_slot));selected.add(preferred.device_id);hasInitialSelection=true;}
    for(const identity of selected)if(!devices.some(d=>d.device_id===identity))selected.delete(identity);
    if(key!==deviceKey){
      deviceKey=key;rows.clear();const container=byId("directionDevices");container.replaceChildren();
      if(!devices.length){const p=document.createElement("p");p.className="hint";p.textContent="先连接设备，再明确选择本次标定范围。";container.append(p);}
      for(const device of devices){
        const label=document.createElement("label"),input=document.createElement("input"),text=document.createElement("span"),title=document.createElement("strong"),details=document.createElement("small");
        label.className="direction-device";input.type="checkbox";input.value=device.device_id;input.checked=selected.has(device.device_id);input.setAttribute("aria-label",`方向标定设备 ${device.device_id}`);
        input.onchange=()=>{if(input.checked)selected.add(device.device_id);else selected.delete(device.device_id);render();};
        text.append(title,details);label.append(input,text);container.append(label);rows.set(device.device_id,{input,title,details});
      }
    }
    for(const device of devices){const row=rows.get(device.device_id);if(!row)continue;row.input.checked=selected.has(device.device_id);row.input.disabled=locked||!guidedRole(device.body_slot);row.title.textContent=`${device.device_id} · ${device.body_slot||"未绑定"}`;const stability=device.stability||{},quality=device.quality||{};row.details.textContent=`${device.source==="real"?"真实输入":"记录来源"} · ${device.valid?"数据有效":"失鲜 / 离线"} · ${device.processing_profile||device.fusion_version||"模式未知"}${guidedRole(device.body_slot)?"":" · 本向导仅用于上臂 / 前臂 / 手"}\n残余角速度 ${number(residual(device),3)} °/s · 停稳保持 ${stability.holding?"生效（不能证明无漂移）":"未生效"} · 磁场 ${stability.magnetic_used?"参与融合":"未参与融合"} · 数据年龄 ${number(quality.age_ms,0)} ms · 坏帧 ${quality.invalid_frames||0}`;}
  }
  function resultEntries(calibration) {
    const raw=calibration.results||calibration.candidates||{};
    if(Array.isArray(raw))return raw.map((value,index)=>[value.device_id||String(index),value]);
    return Object.entries(raw);
  }
  function renderResults(calibration) {
    const container=byId("directionResults");container.replaceChildren();
    for(const [identity,result] of resultEntries(calibration)){
      const item=document.createElement("article"),title=document.createElement("strong"),status=document.createElement("p"),quality=document.createElement("p");
      const failed=result.success===false||result.status==="failed"||!!result.error;item.className="direction-result"+(failed?" failed":"");title.textContent=`${identity} · ${result.body_slot||result.metadata?.body_slot||result.role||"角色见设备列表"}`;
      status.textContent=failed?`失败：${result.error||result.reason||result.message||"质量条件未满足"}`:(result.message||`${statusLabels[result.status]||statusLabels[calibration.status]||"结果待检查"}；仅覆盖本设备 / 角色 / 当前启动会话`);
      const q=result.quality||{};quality.textContent=`动作幅度 ${number(q.excursion_deg??q.amplitude_deg??q.peak_angle_deg,1)}° · 重力一致性误差 ${number(q.gravity_error_deg,2)}° · 前举稳定波动 ${number(q.forward?.quaternion_spread_deg,2)}° · 排除偶发异常 ${q.forward?.excluded_samples??0} 帧 · 算法 ${result.algorithm_version||result.version||calibration.algorithm_version||"见详细记录"}`;
      item.append(title,status,quality);container.append(item);
    }
  }
  function render() {
    if(!state)return;
    const calibration=state.direction_calibration||{},status=calibration.status||"idle";
    const capturing=status==="collecting"||status==="capturing"||calibration.collecting===true;
    const locked=!!state.recording?.active||state.mode==="REPLAY",scope=calibration.devices||calibration.device_ids||[];
    const phaseLabels={preparing:"准备倒计时",collecting:"收集稳定窗口",waiting:"等待更稳定的数据"};
    byId("directionState").textContent=capturing?(phaseLabels[calibration.capture_phase]||statusLabels[status]||status):(statusLabels[status]||status);
    byId("directionState").className="badge"+(status==="failed"||status==="invalidated"?" error":["complete","applied"].includes(status)?" success":"");
    const selectionLocked=!!calibration.has_neutral||status==="candidate";
    renderDevices(locked||capturing||selectionLocked);
    const ids=deviceIds(),eligible=ids.length&&ids.every(id=>(state.devices||[]).some(d=>d.device_id===id&&d.valid&&guidedRole(d.body_slot)&&!d.stability?.calibrating));
    byId("directionNeutralStart").textContent=capturing&&calibration.stage==="neutral"?"中立采样中…":"采样中立姿态";
    byId("directionForwardStart").textContent=capturing&&calibration.stage==="forward"?"前举采样中…":"采样前举姿态";
    byId("directionNeutralStart").disabled=locked||capturing||!eligible;
    const hasNeutral=calibration.has_neutral??["neutral_ready","candidate","complete"].includes(status);
    byId("directionForwardStart").disabled=locked||capturing||!eligible||!hasNeutral||["complete","invalidated","cancelled"].includes(status);
    byId("directionCancel").textContent=capturing?"取消采样":"结束本轮并调整设备";
    byId("directionCancel").disabled=locked||status==="idle";
    byId("directionApply").disabled=locked||!["candidate","ready","fitted"].includes(status);
    const stage=calibration.stage==="neutral"?"中立定姿":calibration.stage==="forward"?"前举定姿":calibration.stage||"";
    byId("directionMessage").textContent=locked?(state.mode==="REPLAY"?"正在回放当时保存的标定结果；先返回实时再采集或应用。":"录制中锁定标定；先停止并保存，再改变安装 / 方向参考。"):(calibration.message||calibration.error||"先选择设备，点击中立采样；抬臂停稳后再点击前举采样。")+(capturing?` · ${stage}${Number.isFinite(calibration.elapsed_s)?` ${number(calibration.elapsed_s,1)} s`:""}`:"")+(selectionLocked&&!locked&&!capturing?" · 本轮设备范围已锁定；点击“结束本轮并调整设备”后重新选择设备。已应用标定保留；重新采中立会撤销所选设备旧参考。":"");
    const counts=Object.entries(calibration.sample_counts||{}).map(([id,count])=>`${id}: ${count} 帧`).join("；");
    byId("directionScope").textContent=`已选：${ids.join("、")||"无"}。${scope.length?`本次采集范围：${scope.map(d=>typeof d==="string"?d:d.device_id).join("、")}`:"尚无本次采集范围。"}${calibration.coverage?.length?` · 骨段 ${calibration.coverage.join("、")}`:""}${counts?` · ${counts}`:""}${calibration.calibration_id?` · 标定 ID ${calibration.calibration_id}`:""}`;
    renderResults(calibration);byId("directionDetails").textContent=Object.keys(calibration).length?JSON.stringify(calibration,null,2):"尚无方向标定记录";
  }
  byId("directionNeutralStart").onclick=()=>command("direction_start",{stage:"neutral",device_ids:deviceIds()});
  byId("directionForwardStart").onclick=()=>command("direction_start",{stage:"forward",device_ids:deviceIds()});
  byId("directionCancel").onclick=()=>command("direction_cancel");
  byId("directionApply").onclick=()=>command("direction_apply");
  root.DirectionApp={update(next){state=next;render();}};
})(window);
