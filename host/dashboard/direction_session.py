"""Bounded functional-calibration acquisition, atomic apply and invalidation.

This controller observes accepted per-device samples; it never opens a device,
changes processing modes or starts gyro/magnetic calibration on the user's behalf.
"""
from copy import deepcopy
import hashlib
import json
import math
from time import monotonic
from uuid import uuid4

from .body_math import angle_degrees, IDENTITY, inverse, multiply


class DirectionSession:
    FORMAT = "body-direction-session/2"
    MAX_SECONDS = 30.
    MAX_SAMPLES = 4000

    def __init__(self, engine):
        self.engine = engine
        self.state = {"schema_version": self.FORMAT, "status":"idle", "stage":None,
                      "devices":[], "message":"确认身份、角色、处理模式和人体前方后，分别静止采集中立和前举姿态", "results":{}}
        self.neutral, self.motion, self.evidence = {}, {}, {}
        self.signatures = {}
        self.attempt_id = None
        self.neutral_valid = False
        self.capture_bases = {}
        self.selected_windows = {"neutral":{}, "forward":{}}
        self.last_window_check = None

    @staticmethod
    def signature(node):
        return {"device_id":node.device_id, "body_slot":node.body_slot, "boot_id":node.boot_id,
                "processing_profile":node.processing_profile, "processing_settings":dict(node.processing_settings),
                "fusion_version":node.fusion_version, "sensor_axes":list(node.coordinates.sensor_axes),
                "gyro_bias":list(node.stability.bias), "reference_revision":node.reference_revision,
                "stability_enabled":node.stability_enabled,
                "processing_config_version":node.attitude_config["config_version"],
                "skeleton_version":node.config["skeleton_version"],
                "config_version":node.config_version, "firmware_version":node.firmware_version}

    @property
    def capturing(self):
        return self.state["status"] == "capturing"

    def _fail(self, reason, device_id=None):
        self.state.update(status="failed", message=reason)
        self.engine._event("direction_calibration_failed", reason=reason, device_id=device_id,
                           stage=self.state.get("stage"), devices=self.state["devices"])

    def _check(self, now):
        for identity in self.state["devices"]:
            node = self.engine.devices.get(identity)
            if node is None or self.signature(node) != self.signatures.get(identity):
                return f"{identity} 身份/启动会话/位置/轴映射/处理模式/零偏或融合参考已改变，请重采中立姿态"
            if not node.connected or node.latest_at is None or now-node.latest_at > .25:
                return f"{identity} 数据断开或失鲜，请重采"
            if node.stability.calibrating:
                return f"{identity} 正在陀螺零偏校准，请完成后重新采集"
            if len(self.engine._bindings().get(node.body_slot, [])) != 1:
                return f"{identity} 身体位置冲突，请先解除冲突"
            initial = self.state["initial_quality"][identity]
            if (node.invalid_frames != initial["invalid_frames"] or node.sampling_gaps != initial["sampling_gaps"]
                    or node.missing_frames != initial["missing_frames"]):
                return f"{identity} 动作窗口出现坏帧、缺帧或采样中断，请重采"
        return None

    def start(self, stage, device_ids=None, now=None):
        now = monotonic() if now is None else now
        if self.capturing:
            raise ValueError("先结束或取消当前方向标定窗口")
        if stage not in ("neutral", "forward"):
            raise ValueError("方向标定阶段应为 neutral 或 forward")
        if stage == "neutral":
            ids = list(dict.fromkeys(device_ids or []))
            if not ids:
                raise ValueError("请明确选择要标定的设备")
            for identity in ids:
                node = self.engine.devices.get(identity)
                if node is None or node.body_slot is None or not node.body_slot.endswith(("_upper_arm", "_forearm", "_hand")):
                    raise ValueError("当前引导仅支持已绑定上臂/前臂/手骨段；其他槽位需对应的功能动作配置")
                if node.last_sample is None or node.source == "simulation_pose":
                    raise ValueError("需要真实处理链或合成原始传感器采样，不能用场景已知姿态冒充标定采集")
                if not node.connected or node.latest_at is None or now-node.latest_at > .25 or node.stability.calibrating:
                    raise ValueError("所选设备断开、失鲜或正在零偏校准，请先确认质量")
                if len(self.engine._bindings().get(node.body_slot, [])) != 1:
                    raise ValueError("所选身体位置冲突，请先解除冲突")
            for identity in ids:
                node = self.engine.devices[identity]
                node.reset_reference("开始新的安装/方向标定：旧参考已撤销，等待完成并显式应用")
                self.engine._clear_local(node.body_slot)
            self.state = {"schema_version":self.FORMAT, "status":"ready", "stage":stage, "devices":ids,
                          "results":{}, "coverage":[self.engine.devices[d].body_slot for d in ids],
                          "initial_quality":{d:{"invalid_frames":self.engine.devices[d].invalid_frames,
                                                 "sampling_gaps":self.engine.devices[d].sampling_gaps,
                                                 "missing_frames":self.engine.devices[d].missing_frames} for d in ids}}
            self.attempt_id = uuid4().hex
            self.state["attempt_id"] = self.attempt_id
            self.signatures = {d:self.signature(self.engine.devices[d]) for d in ids}
            self.neutral = {d:[] for d in ids}
            self.motion = {d:[] for d in ids}
            self.neutral_valid = False
            self.selected_windows = {"neutral":{}, "forward":{}}
        elif not self.neutral_valid:
            raise ValueError("请先完成有效中立采集")
        elif self.state["status"] not in ("neutral_ready", "failed", "candidate"):
            raise ValueError("请先完成有效中立采集")
        reason = self._check(now)
        if reason:
            self._fail(reason)
            raise ValueError(reason)
        if stage == "forward":
            self.motion = {d:[] for d in self.state["devices"]}
            self.selected_windows["forward"] = {}
        self.capture_bases = {}
        from .direction_calibration import load_settings
        settings = load_settings()
        capture_seconds = settings["static_capture_seconds"]
        self.last_window_check = None
        self.state.update(status="capturing", stage=stage, started=now, elapsed_s=0.,
                          capture_seconds=capture_seconds,
                          prepare_seconds=settings["static_prepare_seconds"],
                          timeout_seconds=settings["static_wait_timeout_seconds"],
                          capture_policy="stable-window/1", capture_phase="preparing", waiting_reason="",
                          window_rejections={},
                          results={},errors={},
                          sample_counts={d:0 for d in self.state["devices"]},
                          message="准备中立采样：双臂伸直自然下垂，允许轻微晃动，稍后自动寻找稳定窗口" if stage=="neutral" else
                          "准备前举采样：保持肘伸直和前举姿态，允许轻微晃动；自动等待稳定窗口，不用放回")
        self.engine._event("direction_window_started", stage=stage, devices=self.state["devices"],
                           signatures=deepcopy(self.signatures))
        return self.snapshot(now)

    def observe(self, node):
        if not self.capturing or node.device_id not in self.state["devices"]:
            return
        now = node.latest_at
        reason = self._check(now)
        if reason:
            self._fail(reason, node.device_id)
            return
        target = self.neutral if self.state["stage"] == "neutral" else self.motion
        values = target[node.device_id]
        if len(values) >= self.MAX_SAMPLES or now-self.state["started"] > self.MAX_SECONDS:
            self._fail("采集窗口超出有界容量或30秒，请重新采集", node.device_id)
            return
        sample = node.mapped_sample
        corrected = node.stability.corrected(sample)
        # Windows host clock ticks may coincide for distinct 100Hz packets.
        # Anchor the monotonic *device* clock once per window; keep actual
        # arrivals separately. Do not invent samples or assume arrival spacing.
        stamp = now
        clock_source = "host_arrival"
        if node.unwrapped_device_us is not None:
            base = self.capture_bases.setdefault(node.device_id,(node.unwrapped_device_us,now))
            stamp = base[1]+(node.unwrapped_device_us-base[0])/1e6
            clock_source = "device_clock_anchored_to_host"
        values.append({"time":stamp, "received_monotonic":now, "received_unix":sample.received_unix,
                       "window_clock_source":clock_source,
                       "quaternion":list(node.quaternion), "accel":list(sample.accel),
                       "gyro":list(corrected.gyro), "raw_gyro":list(sample.gyro),
                       "sequence":sample.sequence, "device_us":sample.device_us,
                       "sensor_flags":sample.sensor_flags, "holding":bool(node.stability_enabled and node.stability.stationary),
                       "magnetic_used":node.stability.magnetic_used, **deepcopy(self.signatures[node.device_id])})

    def _stable_windows(self, now):
        from .direction_calibration import CalibrationError, summarize_neutral
        target = self.neutral if self.state["stage"] == "neutral" else self.motion
        if now-self.state["started"] < self.state["prepare_seconds"]+self.state["capture_seconds"]-1e-9:
            raise CalibrationError("insufficient_duration", "准备后仍需收集完整稳定窗口")
        if any(not target[d] for d in self.state["devices"]):
            raise CalibrationError("insufficient_samples", "等待所选设备的数据")
        # All selected devices must be stable in the same host-anchored interval.
        # Do not independently select unrelated poses at different times.
        end = min(target[d][-1]["time"] for d in self.state["devices"])
        start = max(self.state["started"]+self.state["prepare_seconds"], end-self.state["capture_seconds"])
        windows = {d:[s for s in target[d] if start-1e-9 <= s["time"] <= end+1e-9]
                   for d in self.state["devices"]}
        errors = {}
        for identity, samples in windows.items():
            try:
                summarize_neutral(samples, tolerant=True)
            except CalibrationError as exc:
                errors[identity] = {"code":exc.code,"reason":str(exc),"quality":exc.quality}
        if errors:
            self.state["window_rejections"] = errors
            message = "；".join(f"{d}: {e['reason']}" for d,e in errors.items())
            raise CalibrationError("window_not_stable", message, errors)
        self.state["window_rejections"] = {}
        self.state["selected_window"] = {"start":start,"end":end,"approximate_alignment":True,
                                         "samples":{d:len(s) for d,s in windows.items()}}
        return windows

    def finish(self, now=None, *, windows=None):
        from .direction_calibration import fit_static_direction, summarize_neutral
        now = monotonic() if now is None else now
        if not self.capturing:
            raise ValueError("没有正在采集的方向标定窗口")
        reason = self._check(now)
        if reason:
            self._fail(reason)
            return self.snapshot(now)
        stage = self.state["stage"]
        if windows is None:
            try:
                windows = self._stable_windows(now)
            except ValueError as exc:
                self.state["errors"] = {"window":str(exc)}
                self._fail(str(exc))
                return self.snapshot(now)
        self.selected_windows[stage] = deepcopy(windows)
        self.state.update(capture_phase="accepted", waiting_reason="")
        errors, results, rejections = {}, {}, {}
        for identity in self.state["devices"]:
            try:
                if stage == "neutral":
                    results[identity] = summarize_neutral(windows[identity], tolerant=True)
                else:
                    results[identity] = fit_static_direction(self.selected_windows["neutral"][identity], windows[identity])
            except ValueError as exc:
                errors[identity] = str(exc)
                rejections[identity] = {"code":getattr(exc,"code","invalid_window"),"quality":getattr(exc,"quality",{}),"reason":str(exc)}
                self.engine._event("direction_fit_rejected", device_id=identity, stage=stage,
                                   code=getattr(exc,"code","invalid_window"), quality=getattr(exc,"quality",{}), reason=str(exc))
        if errors:
            self.state["errors"] = errors
            self.state["rejections"] = rejections
            self._fail("；".join(f"{d}: {reason}" for d,reason in errors.items()))
        elif stage == "neutral":
            self.neutral_valid = True
            self.state.update(status="neutral_ready", neutral_quality=results,
                              message="中立采样完成。保持肘伸直，向正前方抬臂停稳，再点击前举采样")
            self.engine._event("direction_neutral_accepted", devices=self.state["devices"], quality=deepcopy(results))
        else:
            # Both rigid segments start down and end in the same straight-arm
            # pose. Only compare endpoint excursions: no motion path is sampled.
            for side in ("right", "left"):
                chain = [d for d in self.state["devices"] if self.engine.devices[d].body_slot in (side+"_upper_arm", side+"_forearm")]
                if len(chain) == 2:
                    difference = abs(results[chain[0]]["quality"]["excursion_deg"]-results[chain[1]]["quality"]["excursion_deg"])
                    if difference > 12.:
                        self._fail("上臂和前臂抬起幅度不一致；保持肘伸直，两段一起前举并停稳，重新采两次定姿")
                        self.neutral_valid = False
                        return self.snapshot(now)
            self.state.update(status="candidate", results=results, errors={},
                              message="拟合候选通过检查；核对质量后显式应用。需再以未参与拟合的侧举、再次前举和独立屈肘验证")
            self.engine._event("direction_candidate", devices=self.state["devices"], results=deepcopy(results))
        return self.snapshot(now)

    def apply(self, now=None):
        now = monotonic() if now is None else now
        if self.state["status"] != "candidate":
            raise ValueError("没有通过质量检查的待应用结果")
        reason = self._check(now)
        if reason:
            self._fail(reason)
            raise ValueError(reason)
        calibration_id = uuid4().hex
        for identity, result in self.state["results"].items():
            node = self.engine.devices[identity]
            windows = {"neutral":deepcopy(self.neutral[identity]), "forward":deepcopy(self.motion[identity]),
                       "selected_windows":{stage:deepcopy(self.selected_windows[stage][identity]) for stage in ("neutral","forward")},
                       "capture_policy":"stable-window/1"}
            digest = hashlib.sha256(json.dumps(windows,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
            applied = {**deepcopy(result), "calibration_id":calibration_id, "valid":True,
                       "metadata":deepcopy(self.signatures[identity]), "applied_monotonic":now,
                       "window_sha256":digest, "validation":"held_out_actions_pending"}
            node.direction_calibration = applied
            node.reference = tuple(result["reference"])
            node.fusion_to_world = tuple(result["fusion_to_world"])
            node.calibration_id = calibration_id
            node.reference_reason = "中立+前举两次定姿安装/方向标定；不消除航向漂移；独立验证待完成"
            self.evidence[identity] = {"calibration_id":calibration_id,"window_sha256":digest,**windows}
            self.engine._clear_local(node.body_slot)
        self.state.update(status="complete", calibration_id=calibration_id,
                          message="方向标定已应用；请用未参与拟合的侧举、再次前举和独立屈肘验证。不是漂移或角度精度验收")
        self.engine._event("direction_calibration_applied", calibration_id=calibration_id,
                           devices=self.state["devices"], results=deepcopy(self.state["results"]))
        return self.snapshot(now)

    def cancel(self):
        self.neutral_valid = False
        self.state.update(status="cancelled", message="方向标定采集已取消，未自动应用候选变换")
        self.engine._event("direction_calibration_cancelled", devices=self.state["devices"])

    def snapshot(self, now=None):
        now = monotonic() if now is None else now
        if self.capturing or self.state["status"] in ("neutral_ready", "candidate"):
            reason = self._check(now)
            if reason:
                self._fail(reason)
        if self.capturing:
            from .direction_calibration import load_settings
            elapsed = now-self.state["started"]
            prepare = self.state["prepare_seconds"]
            ready_after = prepare+self.state["capture_seconds"]
            self.state["prepare_remaining_s"] = max(0.,prepare-elapsed)
            if elapsed >= self.state["timeout_seconds"]:
                reason = self.state.get("waiting_reason") or "没有足够的稳定数据"
                self._fail("等待稳定窗口超时，请放稳后重试；"+reason)
            elif elapsed < prepare:
                self.state.update(capture_phase="preparing",message=f"请摆好姿态，准备倒计时 {prepare-elapsed:.1f} 秒；允许轻微自然晃动")
            elif elapsed < ready_after-1e-9:
                self.state.update(capture_phase="collecting",message="正在收集稳定姿态；允许轻微晃动，达到质量后自动结束")
            elif self.last_window_check is None or now-self.last_window_check >= load_settings()["static_check_interval_seconds"]:
                self.last_window_check = now
                try:
                    windows = self._stable_windows(now)
                except ValueError as exc:
                    self.state.update(capture_phase="waiting",waiting_reason=str(exc),
                                      message="等待更稳定的一段数据，无需反复点击："+str(exc))
                else:
                    return self.finish(now, windows=windows)
        if self.state["status"] == "complete":
            invalid = [d for d in self.state["devices"] if d not in self.engine.devices or not self.engine.devices[d].direction_calibration or not self.engine.devices[d].direction_calibration.get("valid")]
            if invalid:
                self.state.update(status="invalidated", message="方向标定因参考/身份/配置变化失效，请重采："+", ".join(invalid))
                self.engine._event("direction_calibration_invalidated", devices=invalid)
        result = deepcopy(self.state)
        if result.get("stage"):
            target = self.neutral if result["stage"] == "neutral" else self.motion
            result["sample_counts"] = {d:len(target.get(d,[])) for d in self.state["devices"]}
        if result.get("started") is not None:
            result["elapsed_s"] = max(0.,now-result["started"])
        result["has_neutral"] = self.neutral_valid
        return result

    def evidence_snapshot(self):
        return {"applied":deepcopy(self.evidence), "attempt_id":self.attempt_id,
                "state":deepcopy(self.state), "signatures":deepcopy(self.signatures),
                "device_results":{d:deepcopy(n.direction_calibration) for d,n in self.engine.devices.items() if n.direction_calibration},
                "captured_windows":{"neutral":deepcopy(self.neutral),"forward":deepcopy(self.motion)},
                "selected_windows":deepcopy(self.selected_windows)}
