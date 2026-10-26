"""Explicit offline reference fixture for exercising the *actual* capture UI.

Only AHRS output is supplied as known geometry; raw samples still traverse the
registry, quality checks and capture/fit/solver. This is never a hardware source
or a claim that the AHRS has been physically validated.
"""
import math
from time import monotonic, perf_counter

from .body_math import IDENTITY, inverse, multiply, quaternion, rotate
from .models import SensorSample


def axis_angle(axis, degrees):
    size = math.hypot(*axis)
    half = math.radians(degrees)/2
    return quaternion((math.cos(half),*(math.sin(half)*v/size for v in axis)))


class ReferenceFixture:
    version = "simulation-known-reference/1"
    def __init__(self):
        self.next_q = self.q = IDENTITY
    def update(self,sample,correction_scale=1.):
        self.q = self.next_q
        return self.q
    def reset(self):
        self.q = IDENTITY


class DirectionDemo:
    def __init__(self, runtime, scenario):
        if scenario not in ("valid","degenerate"):
            raise ValueError("未知方向标定模拟场景")
        self.runtime, self.scenario = runtime, scenario
        self.started, self.sequence = monotonic(), 0
        self.device_started = perf_counter()
        self.cases = [("direction-demo-upper","right_upper_arm",axis_angle((1,2,3),113),axis_angle((0,0,1),137)),
                      ("direction-demo-fore","right_forearm",axis_angle((-2,.3,1),71),axis_angle((0,0,1),-103))]
        self.ports = []
        for identity,role,mount,frame in self.cases:
            endpoint = "demo-"+role
            self.ports.append(endpoint)
            runtime.endpoints[endpoint] = {"endpoint_id":endpoint,"transport":"offline-reference-fixture",
                                           "status":"connected","simulation":True,"invalid_frames":0}
            processor = runtime.engine._device(identity)
            processor.set_processing("six_axis_relative")
            processor.fusion = ReferenceFixture()
            processor.fusion_version = processor.fusion.version
            processor.stability_enabled = False
        self.validation_pose = None
        self.validation_started = self.started

    def set_validation(self,pose):
        if pose not in ("neutral","forward","side","elbow","rigid"):
            raise ValueError("未知离线验证动作")
        self.validation_pose = pose
        self.validation_started = monotonic()

    def feed(self,now=None):
        now = monotonic() if now is None else now
        state = self.runtime.engine.direction.state
        angle, speed, axis = 0.,0.,(0.,-1.,0.)
        if state.get("stage") == "forward" and state["status"] == "capturing":
            t = now-state["started"]
            moving = 3.
            phase = (t-.5)/moving
            if 0 < phase < 1:
                angle = 70*math.sin(math.pi*phase)**2
                speed = 70*math.pi/moving*math.sin(2*math.pi*phase)
            if self.scenario == "degenerate":
                axis = (0.,0.,1.)
        elif self.validation_pose and state["status"] == "complete":
            angle = 55.
            axis = (-1.,0.,0.) if self.validation_pose=="side" else (0.,-1.,0.)
            if self.validation_pose=="neutral":
                angle=0.
            if self.validation_pose=="rigid":
                axis=(1.,-2.,.7)
        for i,(identity,role,mount,fusion_frame) in enumerate(self.cases):
            body_q = axis_angle(axis,angle)
            if self.validation_pose=="elbow" and state["status"]=="complete" and i==0:
                body_q = IDENTITY
            sensor_world = multiply(body_q,mount)
            inv = inverse(sensor_world)
            processor = self.runtime.engine.devices[identity]
            processor.fusion.next_q = multiply(fusion_frame,sensor_world)
            sample = SensorSample(rotate((0.,0.,1.),inv),rotate(tuple(speed*v for v in axis),inv),
                                  rotate((300.,40.,80.),inv),25.,0.,received_monotonic=now,
                                  node_id=identity,sequence=self.sequence,device_us=int((perf_counter()-self.device_started)*1e6)%2**32,
                                  body_slot=role,boot_id="direction-demo-boot",protocol_version="IMU3",
                                  firmware_version="simulation-only",config_version="direction-demo/1")
            self.runtime.consume(sample,self.ports[i],"simulation_sensor_truth")
        self.sequence=(self.sequence+1)%2**32
