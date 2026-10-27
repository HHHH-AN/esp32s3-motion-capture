"""Calibration must recover known distortion and reject plausible bad fits."""
import math
from pathlib import Path
import tempfile
import unittest

from dashboard.magnetometer import fit, correct, load, save, validate, _eigen
from dashboard.body_engine import BodyEngine
from dashboard.models import SensorSample


def sphere(count=1200, hemisphere=False):
    points=[]
    for i in range(count):
        z=1-2*(i+.5)/count
        if hemisphere:
            z=.8+.2*(z+1)/2
        phi=i*math.pi*(3-math.sqrt(5))
        points.append((450*math.sqrt(1-z*z)*math.cos(phi),450*math.sqrt(1-z*z)*math.sin(phi),450*z))
    return points


class MagnetometerCalibrationTests(unittest.TestCase):
    def test_known_offset_and_cross_axis_soft_iron_are_recovered(self):
        distortion=((1.2,.1,.05),(.1,.9,-.04),(.05,-.04,1.05))
        bias=(300.,-250.,700.)
        truth=sphere()
        raw=[[sum(distortion[i][j]*v[j] for j in range(3))+bias[i] for i in range(3)] for v in truth]
        calibration=fit(raw)
        for a,b in zip(calibration['bias_mG'],bias):
            self.assertAlmostEqual(a,b,places=5)
        self.assertLess(calibration['quality']['relative_rms'],1e-8)
        for original,distorted in zip(truth[::20],raw[::20]):
            restored=correct(distorted,calibration)
            cosine=sum(a*b for a,b in zip(original,restored))/math.hypot(*original)/math.hypot(*restored)
            self.assertGreater(cosine,1-1e-10)

    def test_static_planar_and_narrow_direction_captures_are_rejected(self):
        cases=[[(400.,20.,-100.)]*600,
               [(450*math.cos(i*.03),450*math.sin(i*.03),0.) for i in range(600)],
               sphere(600,hemisphere=True)]
        for values in cases:
            with self.subTest(case=cases.index(values)):
                with self.assertRaises(ValueError):
                    fit(values)

    def test_eigenvectors_reconstruct_the_original_symmetric_matrix(self):
        matrix=[[2.,.4,-.3],[.4,1.,.2],[-.3,.2,3.]]
        values,basis=_eigen(matrix)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(sum(basis[i][k]*values[k]*basis[j][k] for k in range(3)),matrix[i][j],places=9)

    def test_persistence_identity_and_input_ownership(self):
        calibration=fit(sphere())
        raw=(300.,0.,400.)
        self.assertEqual(correct(raw,None),raw)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'calibration.json'
            self.assertIsNone(load('A',path))
            saved=save('A',calibration,path)
            calibration['bias_mG'][0]=1000
            self.assertEqual(load('A',path),saved)
            self.assertIsNone(load('B',path))
            changed=dict(saved,matrix=[[float('nan'),0,0],[0,1,0],[0,0,1]])
            with self.assertRaises(ValueError):
                validate(changed)

    def test_live_pipeline_corrects_raw_sensor_axes_and_preserves_evidence(self):
        from dashboard.coordinates import CoordinateSettings
        bias=(100.,-200.,600.)
        calibration=fit([[v[i]+bias[i] for i in range(3)] for v in sphere()])
        calibration['source_device_id']='calibration-test'
        engine=BodyEngine()
        raw=SensorSample((0.,0.,1.),(0.,0.,0.),(400.,-200.,1000.),25.,0.,
                         received_monotonic=100.,device_us=0,sequence=0,node_id='calibration-test',
                         boot_id='boot',body_slot='head',protocol_version='IMU3')
        engine.ingest(raw,'tcp')
        node=engine.devices['calibration-test']
        node.coordinates=CoordinateSettings.parse({'sensor_axes':['-X','+Y','-Z']})
        node.stability.bias=(.1,.2,.3)
        node.stability.calibrated=True
        engine.set_magnetic_calibration('calibration-test',calibration)
        from dataclasses import replace
        engine.ingest(replace(raw,received_monotonic=100.01,sequence=1,device_us=10000),'tcp')
        self.assertEqual(node.last_sample.mag,raw.mag)
        for actual,expected in zip(node.mapped_sample.mag,(-300.,0.,-400.)):
            self.assertAlmostEqual(actual,expected,places=5)
        self.assertEqual(node.stability.bias,(.1,.2,.3))
        self.assertTrue(node.stability.calibrated)
        self.assertIsNone(node.reference)
        self.assertEqual(node.snapshot(100.01)['magnetic_calibration']['source_device_id'],'calibration-test')
        with self.assertRaises(ValueError):
            node.set_magnetic_calibration(dict(calibration,source_device_id='other-board'))


if __name__=='__main__':
    unittest.main()
