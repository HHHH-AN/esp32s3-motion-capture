"""Known sensor/body geometry for direction-calibration regression tests.

The mounting C maps sensor vectors to a neutral bone/body frame. F maps the
human world to an arbitrary, fixed AHRS reference. Thus Q = F R C, while raw
gravity/gyro observations use R C and never use the untrusted AHRS reference.
"""
from dataclasses import dataclass
from math import cos, pi, sin

from dashboard.body_math import IDENTITY, inverse, multiply, quaternion, rotate
from dashboard.models import SensorSample


def axis_angle(axis, degrees):
    length = sum(v*v for v in axis)**.5
    if length <= 1e-12:
        raise ValueError("rotation axis must be nonzero")
    half = degrees*pi/360
    return quaternion((cos(half), *(v/length*sin(half) for v in axis)))


@dataclass(frozen=True)
class MountCase:
    device_id: str
    body_slot: str
    mount: tuple = IDENTITY
    fusion: tuple = IDENTITY


@dataclass(frozen=True)
class TruthFrame:
    sample: SensorSample
    quaternion: tuple
    body_quaternion: tuple

    def calibration_sample(self):
        return {"quaternion":self.quaternion, "accel":self.sample.accel,
                "gyro":self.sample.gyro, "time":self.sample.received_monotonic,
                "device_id":self.sample.node_id, "body_slot":self.sample.body_slot,
                "boot_id":self.sample.boot_id, "processing_profile":"truth_fixture",
                "fusion_version":"synthetic-known-reference/1"}


def make_frame(case, body_q=IDENTITY, time_s=100., seq=0,
               angular_world=(0.,0.,0.), boot="fixture-boot"):
    sensor_to_world = multiply(body_q,case.mount)
    world_to_sensor = inverse(sensor_to_world)
    sample = SensorSample(rotate((0.,0.,1.),world_to_sensor),
                          rotate(angular_world,world_to_sensor),
                          rotate((300.,50.,80.),world_to_sensor),25.,0.,
                          received_monotonic=time_s, received_unix=1_790_000_000.+time_s,
                          node_id=case.device_id, sequence=seq,
                          device_us=int(time_s*1e6) % 2**32,
                          body_slot=case.body_slot, boot_id=boot,
                          firmware_version="truth-fixture/1",config_version="mount-fixture/1",
                          protocol_version="IMU3")
    return TruthFrame(sample,multiply(case.fusion,sensor_to_world),quaternion(body_q))


def neutral_window(case,start=100.,duration=1.2,hz=100,first_sequence=0):
    return [make_frame(case,time_s=start+i/hz,seq=first_sequence+i)
            for i in range(round(duration*hz)+1)]


def hinge_window(case,start=102.,duration=4.,axis=(0.,-1.,0.),peak_deg=70.,
                 hz=100,first_sequence=1000,rest_s=.5):
    """Complete raised/returned hinge action; exact peak is only fixture truth.

    The physically signed direction of the first excursion is known to the
    calibration. It does not receive or need the fixture's numerical amplitude.
    """
    moving = duration-2*rest_s
    if moving <= 0:
        raise ValueError("duration must leave time for raising and return")
    norm = sum(v*v for v in axis)**.5
    frames = []
    for i in range(round(duration*hz)+1):
        t = i/hz
        phase = (t-rest_s)/moving
        if 0 < phase < 1:
            angle = peak_deg*sin(pi*phase)**2
            speed = peak_deg*pi/moving*sin(2*pi*phase)
        else:
            angle = speed = 0.
        frames.append(make_frame(case,axis_angle(axis,angle),start+t,first_sequence+i,
                                 tuple(v/norm*speed for v in axis)))
    return frames


def fusion_factory(table):
    """Inject only AHRS reference truth; all other pipeline stages stay real."""
    class KnownReferenceFusion:
        version = "synthetic-known-reference/1"
        def __init__(self):
            self.q = IDENTITY
            self.last_time = self.last_device_us = None
        def reset(self):
            self.q = IDENTITY
            self.last_time = self.last_device_us = None
        def update(self,sample,correction_scale=1.):
            self.q = table[(sample.node_id,sample.sequence)]
            self.last_time,self.last_device_us = sample.received_monotonic,sample.device_us
            return self.q
    return KnownReferenceFusion


def register_truth(table,frames):
    for frame in frames:
        table[(frame.sample.node_id,frame.sample.sequence)] = frame.quaternion


def feed(engine,table,frames):
    register_truth(table,frames)
    return [engine.ingest(frame.sample,"fixture-"+frame.sample.node_id,
                          "simulation_sensor_truth") for frame in frames]
