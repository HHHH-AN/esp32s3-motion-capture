"""Compare attitude filters using saved HTTP snapshots, without any hardware I/O.

The old HTTP log contains about 10 snapshots/s, not every 100 Hz sensor frame.
A selected four-second window is *assumed* stationary for a counterfactual bias
estimate. Its mean is injected only into this offline replay: the real >=200
sample calibration is never bypassed in the monitor, and no frames are invented.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "host"
sys.path.insert(0, str(HOST))

from dashboard.attitude_stability import AttitudeStabilizer, mean_std, norm
from dashboard.fusion import ComplementaryFusion, euler_degrees, relative
from dashboard.models import SensorSample


def vector(value, label):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"{label} must contain three finite numbers")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} contains non-finite values")
    return result


def read_samples(path, slot, nominal_hz):
    payloads = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payloads, list):
        raise ValueError("Input must be a JSON list of saved /api/status payloads")
    samples, seen = [], set()
    duplicates = 0
    first_sequence = None
    elapsed_ticks = 0
    previous_sequence = None
    node_ids = set()
    device_time_fields = 0
    for payload in payloads:
        node = payload.get("nodes", {}).get(slot)
        if not node or not node.get("valid"):
            continue
        sequence = node.get("sequence")
        if type(sequence) is not int or not 0 <= sequence < 2**32:
            raise ValueError("A valid uint32 sequence is required")
        if sequence in seen:
            duplicates += 1
            continue
        seen.add(sequence)
        if first_sequence is None:
            first_sequence = sequence
        if previous_sequence is not None:
            delta = (sequence-previous_sequence) % 2**32
            if delta >= 2**31:
                raise ValueError("Sequence restart/reordering requires a separate recording")
            elapsed_ticks += delta
        previous_sequence = sequence
        node_ids.add(node["node_id"])
        actual_device_us = node.get("device_us")
        if actual_device_us is not None:
            if type(actual_device_us) is not int:
                raise ValueError("device_us must be an integer")
            device_time_fields += 1
        device_us = (actual_device_us if actual_device_us is not None else
                     round(sequence*1_000_000/nominal_hz)) % 2**32
        samples.append(SensorSample(
            accel=vector(node["accel"], "accel"),
            gyro=vector(node["gyro"], "gyro"),
            mag=vector(node["mag"], "mag"),
            temperature=0., aux_temperature=0.,
            received_monotonic=elapsed_ticks/nominal_hz,
            received_unix=elapsed_ticks/nominal_hz,
            node_id=node["node_id"], sequence=sequence,
            device_us=device_us, sensor_flags=int(node["sensor_flags"])))
    if len(node_ids) != 1 or len(samples) < 10:
        raise ValueError("Need at least ten valid snapshots from exactly one device")
    return samples, {"http_payloads": len(payloads), "unique_snapshots": len(samples),
                     "duplicate_sequences_removed": duplicates,
                     "snapshots_with_actual_device_us": device_time_fields,
                     "node_id": next(iter(node_ids))}


def choose_assumed_rest(samples, seconds):
    candidates = []
    for start in range(len(samples)):
        end = start
        while end < len(samples) and samples[end].received_monotonic-samples[start].received_monotonic < seconds:
            end += 1
        # Keep a separate subsequent evaluation period of at least two seconds.
        if end >= len(samples)-2 or samples[-1].received_monotonic-samples[end].received_monotonic < 2:
            continue
        window = samples[start:end+1]
        bias, gyro_std = mean_std([item.gyro for item in window])
        accel_mean, accel_std = mean_std([item.accel for item in window])
        magnetic = [item.mag for item in window if item.sensor_flags & 2 and norm(item.mag) > 1e-6]
        mag_reference = None
        mag_cv = None
        if magnetic:
            mag_mean, mag_std = mean_std(magnetic)
            mag_reference = sum(map(norm, magnetic))/len(magnetic)
            mag_cv = mag_std/max(norm(mag_mean), 1e-6)
        # These are only sparse-data plausibility checks, never a live-calibration pass.
        plausible = (gyro_std <= .35 and accel_std <= .01 and
                     all(.85 <= norm(item.accel) <= 1.15 for item in window) and
                     all(max(map(abs, item.gyro)) <= 20 for item in window) and
                     (mag_cv is None or mag_cv <= .025))
        if plausible:
            candidates.append((gyro_std, start, end, bias, norm(accel_mean),
                               accel_std, mag_reference, mag_cv))
    if not candidates:
        raise ValueError("No plausible four-second assumed-rest window with later evaluation data")
    return min(candidates, key=lambda candidate: candidate[0]), len(candidates)


def angle_degrees(q):
    return math.degrees(2*math.acos(min(1., abs(q[0]))))


def replay(samples, stability=None):
    fusion = ComplementaryFusion()
    reference = None
    poses, held, rejected_mag = [], 0, 0
    for sample in samples:
        if stability is None:
            q = fusion.update(sample)
            holding = False
        else:
            # Exactly the monitor's processing order, using actual snapshots only.
            stability.update(sample)
            corrected = stability.guard_magnetometer(stability.corrected(sample))
            holding = stability.stationary
            fusion_sample = replace(corrected, gyro=(0., 0., 0.)) if holding else corrected
            q = fusion.update(fusion_sample, correction_scale=0. if holding else 1.)
            rejected_mag += int(not stability.magnetic_used)
        if reference is None:
            reference = q
        pose = relative(q, reference)
        held += int(holding)
        poses.append({"nominal_s": sample.received_monotonic,
                      "relative_rotation_deg": angle_degrees(pose),
                      "euler_deg": euler_degrees(pose), "holding": holding})
    return {"end_relative_rotation_deg": poses[-1]["relative_rotation_deg"],
            "peak_relative_rotation_deg": max(item["relative_rotation_deg"] for item in poses),
            "end_euler_deg": poses[-1]["euler_deg"],
            "holding_snapshots": held, "holding_ratio": held/len(poses),
            "magnetic_rejected_snapshots": rejected_mag, "trajectory": poses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT/"docs"/"validation"/"evidence"/"wifi-20261025-151516-938679"/"monitor_polls.json")
    parser.add_argument("--slot", choices=("A", "B", "C"), default="A")
    parser.add_argument("--nominal-hz", type=float, default=100.)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.nominal_hz) or args.nominal_hz <= 0:
        parser.error("--nominal-hz must be positive and finite")
    try:
        samples, source = read_samples(args.input, args.slot, args.nominal_hz)
        selected, candidates = choose_assumed_rest(samples, AttitudeStabilizer.CALIBRATION_SECONDS)
        gyro_std, start, end, bias, gravity, accel_std, magnetic, mag_cv = selected
        stability = AttitudeStabilizer()
        # This explicit offline hypothesis does not call/start/pass live calibration.
        stability.bias, stability.calibrated, stability._gravity = bias, True, gravity
        stability._mag_reference = magnetic
        evaluation = samples[end+1:]
        original, corrected = replay(evaluation), replay(evaluation, stability)
        raw_peak = original["peak_relative_rotation_deg"]
        reduction = (1-corrected["peak_relative_rotation_deg"]/raw_peak)*100 if raw_peak > 1e-9 else None
        report = {
            "kind": "offline_historical_http_snapshot_counterfactual",
            "input": str(args.input.resolve()), "slot": args.slot, "source": source,
            "hardware_connected_by_tool": False, "wifi_or_serial_access": False,
            "formal_live_calibration_passed": False,
            "time_assumption": {"nominal_sensor_hz": args.nominal_hz,
                                "received_monotonic": "elapsed sequence / nominal_hz",
                                "missing_device_us": "sequence * 1e6 / nominal_hz modulo 2^32",
                                "exact_hardware_timing_known": source["snapshots_with_actual_device_us"] == len(samples)},
            "assumed_rest_window": {
                "selection": "minimum gyro vector standard deviation among plausible four-second windows",
                "plausible_window_candidates": candidates,
                "nominal_start_s": samples[start].received_monotonic,
                "nominal_end_s": samples[end].received_monotonic,
                "snapshot_count": end-start+1, "bias_dps": bias,
                "gyro_vector_std_dps": gyro_std, "accel_vector_std_g": accel_std,
                "gravity_norm_g": gravity, "magnetic_norm_mG": magnetic,
                "magnetic_vector_coefficient_of_variation": mag_cv},
            "evaluation": {"nominal_start_s": evaluation[0].received_monotonic,
                           "nominal_end_s": evaluation[-1].received_monotonic,
                           "duration_s": evaluation[-1].received_monotonic-evaluation[0].received_monotonic,
                           "snapshot_count": len(evaluation),
                           "both_filters_reset_before_evaluation": True},
            "original_fusion": original, "bias_guard_and_hold_fusion": corrected,
            "peak_relative_rotation_reduction_percent": reduction,
            "limitations": [
                "Historical user motion was not prescribed or independently measured; selecting a quiet window assumes rest.",
                "Sparse HTTP snapshots omit most 100 Hz samples; there is no interpolation, duplication or invented frame.",
                "The bias is injected as an offline hypothesis; the >=200 frame real calibration is not executed or claimed passed.",
                "At roughly 10 Hz, the >=20 samples in a 0.6 s rest detector cannot normally be satisfied; zero hold is expected.",
                "Sequence-based time assumes nominal frequency; fusion's normal 0.1 s dt clamp still applies.",
                "This compares reconstructed relative attitude change, not absolute accuracy, and is not a new board test.",
                "Sensor vectors are already coordinate-mapped by the saved API and are not mapped a second time."]}
        output = args.output or HOST/"hardware_tests"/f"attitude-drift-offline-{args.slot}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"output": str(output.resolve()), "slot": args.slot,
                          "assumed_bias_dps": bias,
                          "original_peak_deg": raw_peak,
                          "corrected_peak_deg": corrected["peak_relative_rotation_deg"],
                          "peak_reduction_percent": reduction,
                          "holding_ratio": corrected["holding_ratio"],
                          "formal_live_calibration_passed": False}, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
