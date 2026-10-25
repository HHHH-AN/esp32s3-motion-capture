"""Standalone, offline HTML playback and charts; no server or CDN required."""
import html
import json


def write_report(path, preset, result):
    payload = json.dumps({"preset": preset, "result": result}, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    document = TEMPLATE.replace("__TITLE__", html.escape(preset["title"])).replace("__DATA__", payload)
    path.write_text(document, encoding="utf-8")


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#18314a;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1160px;margin:auto;padding:30px 24px}h1{font-size:28px;margin:8px 0}h2{font-size:18px;margin:0 0 12px}p{margin:8px 0}.eyebrow{font-size:12px;letter-spacing:2px;color:#62778a}.badge{display:inline-block;border-radius:20px;background:#e4edf8;color:#245c96;padding:4px 12px;font-size:13px}.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:20px;margin:22px 0}.panel{background:white;border:1px solid #dce4ee;border-radius:14px;padding:22px;min-width:0}.wide{grid-column:1/-1}.muted{color:#62778a;font-size:13px}canvas{width:100%;display:block}#skeleton{height:350px;background:#f7fafe;border-radius:8px}#chart{height:270px}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}button{background:#245c96;color:white;border:0;border-radius:7px;padding:9px 18px;cursor:pointer}input[type=range]{flex:1;min-width:110px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e2e8f0;padding:9px 7px;text-align:left}th{color:#536b82}ul{padding-left:22px}.metric{font-variant-numeric:tabular-nums}#instant{min-height:55px}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}details{margin-top:16px}pre{overflow:auto;max-height:330px;background:#f7f9fc;padding:14px;font-size:12px}@media(max-width:760px){main{padding:18px 12px}.grid{grid-template-columns:1fr}h1{font-size:24px}.panel{padding:17px}#skeleton{height:300px}}
</style></head><body><main>
<div class="eyebrow">IMU · THREE NODE EXPERIMENT</div><h1>__TITLE__</h1>
<span class="badge" id="source"></span><p id="description"></p><p class="muted">旋转驱动固定根部骨架 · 不做惯性位移积分 · 软件插值匹配不代表已验证的真实采样同步</p>
<div class="grid"><section class="panel"><h2>三段骨架回放</h2><canvas id="skeleton" aria-label="固定根部三段骨架"></canvas>
<div class="controls"><button id="play">播放</button><input id="seek" type="range" min="0" value="0" aria-label="回放进度"><span id="time" class="metric"></span></div>
<div class="controls"><label for="view">观察方向</label><input id="view" type="range" min="-180" max="180" value="-35"></div>
<div id="instant" class="metric"></div><p class="muted" id="placements"></p></section>
<section class="panel"><h2>角度曲线</h2><div id="legend" class="legend"></div><canvas id="chart" aria-label="肢段角度曲线"></canvas><p class="muted">角度单位 °。空白为无法匹配数据；缺口处不计完整动作。水平轴为标定后共同时间 / s。</p></section>
<section class="panel wide"><h2>本次统计</h2><div style="overflow:auto"><table><thead><tr><th>指标</th><th>最小角度</th><th>最大角度</th><th>角度范围</th><th>均值</th><th>标准差</th></tr></thead><tbody id="metrics"></tbody></table></div><p id="cycles"></p><p id="gyro"></p><p class="muted">角度范围为本次最大值减最小值。计数阈值是可调的实验参数，不是动作规范或临床评价标准。</p></section>
<section class="panel wide"><h2>使用边界与数据质量</h2><ul id="limits"></ul><div id="warnings"></div><details><summary>每节点校准与链路统计</summary><pre id="quality"></pre></details></section></div>
<p class="muted">配套文件：raw.csv 原始协议帧；aligned.csv 匹配后的角度、角速度与四元数；summary.json 统计；session.json 来源与设置。演示文件不能充当实板实验数据。</p>
</main><script id="session-data" type="application/json">__DATA__</script><script>
'use strict';
const {preset,result}=JSON.parse(document.getElementById('session-data').textContent);
const $=id=>document.getElementById(id),frames=result.frames,keys=Object.keys(preset.angle_labels),colors=['#2777c5','#d77536','#299879'];
const synthetic=result.original_source_kind==='synthetic_demo';
$('source').textContent=synthetic?'合成演示数据 · 尚未实板验证':'实测采集数据 · 测量精度尚待独立验证';
$('description').textContent=preset.description;
$('placements').textContent=preset.placements.map((text,i)=>`${'ABC'[i]}：${text}`).join(' ｜ ');
$('seek').max=frames.length-1;
for(const [i,key] of keys.entries()){
 const span=document.createElement('span'),dot=document.createElement('i');dot.className='dot';dot.style.background=colors[i];span.append(dot,document.createTextNode(preset.angle_labels[key]));$('legend').append(span);
 const item=result.metrics[key],row=document.createElement('tr');
 for(const value of [item.label,...['min_deg','max_deg','range_deg','mean_deg','std_deg'].map(k=>item[k].toFixed(2)+'°')]){const td=document.createElement('td');td.textContent=value;row.append(td);}$('metrics').append(row);
}
$('cycles').textContent=Object.entries(result.repetitions).map(([key,v])=>`${preset.angle_labels[key]}：${v.count} 次完整往返；平均周期 ${v.mean_period_s===null?'样本不足':v.mean_period_s.toFixed(2)+' s'}；周期变异 ${v.period_cv_percent===null?'样本不足':v.period_cv_percent.toFixed(1)+'%'}`).join(' ｜ ')||'本预设不做动作计数。';
$('gyro').textContent='峰值传感器角速度：'+Object.entries(result.peak_sensor_gyro_dps).map(([slot,v])=>`${slot} ${v.toFixed(1)} °/s`).join(' ｜ ');
for(const text of result.limitations){const li=document.createElement('li');li.textContent=text;$('limits').append(li);}
for(const text of result.warnings){const p=document.createElement('p');p.textContent=text;$('warnings').append(p);}
$('quality').textContent=JSON.stringify({valid_aligned_frames:result.valid_aligned_frames,invalid_aligned_frames:result.invalid_aligned_frames,nodes:result.nodes},null,2);
let index=0,playing=false,last=0;
function canvas(id){const element=$(id),ratio=devicePixelRatio||1,rect=element.getBoundingClientRect();element.width=Math.round(rect.width*ratio);element.height=Math.round(rect.height*ratio);const c=element.getContext('2d');c.scale(ratio,ratio);return {c,w:rect.width,h:rect.height};}
function skeleton(frame){const {c,w,h}=canvas('skeleton'),yaw=Number($('view').value)*Math.PI/180;
 const project=p=>{const x=Math.cos(yaw)*p[0]-Math.sin(yaw)*p[1],depth=Math.sin(yaw)*p[0]+Math.cos(yaw)*p[1];return [w*.48+x*Math.min(w,h)*.75,h*.82-p[2]*Math.min(w,h)*.65+depth*35];};
 c.strokeStyle='#dde6f0';c.lineWidth=1;for(let i=-5;i<=5;i++){for(const line of [[[-.8,i*.15,0],[.8,i*.15,0]],[[i*.15,-.8,0],[i*.15,.8,0]]]){const a=project(line[0]),b=project(line[1]);c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();}}
 for(const [i,axis] of [[[.3,0,0],'X'],[[0,.3,0],'Y'],[[0,0,.3],'Z']].entries()){const a=project([0,0,0]),b=project(axis[0]);c.strokeStyle=colors[i];c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();c.fillStyle=colors[i];c.fillText(axis[1],b[0]+4,b[1]);}
 if(!frame.valid){c.fillStyle='#62778a';c.fillText('当前时刻无法匹配三节点数据',20,30);return;}
 for(const [i,line] of frame.lines.entries()){const a=project(line[0]),b=project(line[1]);c.strokeStyle=colors[i%3];c.lineWidth=8;c.lineCap='round';c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();for(const p of [a,b]){c.fillStyle='white';c.strokeStyle=colors[i%3];c.lineWidth=3;c.beginPath();c.arc(...p,6,0,Math.PI*2);c.fill();c.stroke();}}
}
function chart(frame){const {c,w,h}=canvas('chart'),left=42,top=24,right=w-15,bottom=h-32,maxT=frames.at(-1).t||1;
 const largest=Math.max(10,...Object.values(result.metrics).map(v=>v.max_deg));const maxY=Math.ceil(largest/30)*30;
 c.font='11px system-ui';c.fillStyle='#62778a';c.strokeStyle='#e4eaf2';c.lineWidth=1;
 for(let i=0;i<=4;i++){const y=bottom-(bottom-top)*i/4;c.beginPath();c.moveTo(left,y);c.lineTo(right,y);c.stroke();c.fillText((maxY*i/4).toFixed(0),3,y+4);const x=left+(right-left)*i/4;c.fillText((maxT*i/4).toFixed(1),x-7,h-9);}
 for(const [number,key] of keys.entries()){c.strokeStyle=colors[number];c.lineWidth=2;c.beginPath();let connected=false;for(const f of frames){if(!f.valid){connected=false;continue;}const x=left+(right-left)*f.t/maxT,y=bottom-(bottom-top)*f.angles[key]/maxY;if(connected)c.lineTo(x,y);else c.moveTo(x,y);connected=true;}c.stroke();}
 const x=left+(right-left)*frame.t/maxT;c.strokeStyle='#18314a';c.lineWidth=1;c.beginPath();c.moveTo(x,top);c.lineTo(x,bottom);c.stroke();
}
function render(){const frame=frames[index];$('seek').value=index;$('time').textContent=`${frame.t.toFixed(2)} s`;$('instant').textContent=frame.valid?keys.map(k=>`${preset.angle_labels[k]} ${frame.angles[k].toFixed(1)}°`).join(' ｜ '):'当前帧缺失，未补造动作';skeleton(frame);chart(frame);}
$('seek').oninput=()=>{index=Number($('seek').value);render();};$('view').oninput=render;
$('play').onclick=()=>{if(index===frames.length-1)index=0;playing=!playing;$('play').textContent=playing?'暂停':'播放';last=0;render();};
function animate(now){if(playing){if(!last)last=now;if(now-last>=20){const step=Math.floor((now-last)/20);last+=step*20;index=Math.min(frames.length-1,index+step);if(index===frames.length-1){playing=false;$('play').textContent='播放';}render();}}requestAnimationFrame(animate);}addEventListener('resize',render);render();requestAnimationFrame(animate);
</script></body></html>'''
