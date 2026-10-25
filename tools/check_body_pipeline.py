"""Offline multi-device load/record/replay check. Never opens serial or TCP."""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
from time import monotonic, process_time, perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from dashboard.body_runtime import BodyRuntime
from dashboard.body_recording import BodyReplay
from dashboard.models import SensorSample


async def run(nodes, seconds, record):
    runtime = BodyRuntime()
    roles = [s["id"] for s in runtime.engine.config["segments"]][:nodes]
    if record:
        runtime.recorder.start(runtime.payload())
    started, cpu = monotonic(), process_time()
    durations, frames, ticks = [], 0, 0
    next_frame, next_body = started, started
    try:
        while monotonic()-started < seconds:
            now = monotonic()
            if now < next_frame:
                await asyncio.sleep(next_frame-now)
            arrival = monotonic()
            begin = perf_counter()
            for i, slot in enumerate(roles):
                sample = SensorSample((0.,0.,1.),(0.,0.,0.),(300.,0.,100.),25.,0.,
                                      received_monotonic=arrival, node_id=f"load{i}",
                                      sequence=frames, device_us=frames*10000 % 2**32,
                                      body_slot=slot, boot_id="offline-load", protocol_version="IMU3")
                runtime.consume(sample, f"offline{i}", "simulation_sensor")
            if arrival >= next_body:
                await runtime.tick()
                ticks += 1
                next_body = started+ticks/30
            durations.append(1000*(perf_counter()-begin))
            frames += 1
            next_frame = started+frames*.01
        state = runtime.payload()
        result = {"kind":"offline_simulated_load_not_hardware", "nodes":nodes,
                  "requested_hz_per_node":100, "elapsed_s":monotonic()-started,
                  "cpu_s":process_time()-cpu, "accepted_samples":sum(d["quality"]["valid_frames"] for d in state["devices"]),
                  "expected_samples":frames*nodes, "body_ticks":ticks,
                  "batch_processing_ms_median":statistics.median(durations),
                  "batch_processing_ms_p95":sorted(durations)[int((len(durations)-1)*.95)],
                  "invalid_frames":sum(d["quality"]["invalid_frames"] for d in state["devices"]),
                  "hardware_online":state["live_device_count"], "recorded":record}
        if record:
            await asyncio.to_thread(runtime.recorder.stop)
            replay = BodyReplay(runtime.recorder.root)
            try:
                replay.open(runtime.recorder.session)
                replay.seek(replay.duration)
                result.update(session=runtime.recorder.session, counts=runtime.recorder.counts,
                              recording_error=runtime.recorder.error, replay_final_frame_present=replay.frame() is not None)
            finally:
                replay.close()
        if result["accepted_samples"] != result["expected_samples"] or result["invalid_frames"] or result.get("recording_error"):
            raise RuntimeError(json.dumps(result))
        return result
    finally:
        await runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=14, choices=range(1,15))
    parser.add_argument("--seconds", type=float, default=5.)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not .1 <= args.seconds <= 300:
        parser.error("--seconds must be between .1 and 300")
    result = asyncio.run(run(args.nodes, args.seconds, args.record))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(encoded+"\n",encoding="utf-8")
    print(encoded)
