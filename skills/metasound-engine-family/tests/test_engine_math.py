import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import engine_math as m  # noqa: E402


class EngineMath(unittest.TestCase):
    def test_octave(self):
        self.assertAlmostEqual(m.semitone_ratio(12), 2.0)
        self.assertAlmostEqual(m.semitone_ratio(-12), 0.5)
        self.assertAlmostEqual(m.semitone_ratio(0), 1.0)

    def test_engine_hz(self):
        self.assertAlmostEqual(m.engine_hz(100, 12, 0, 0, 0), 100)
        self.assertAlmostEqual(m.engine_hz(100, 12, 0, 1, 0), 200)
        self.assertAlmostEqual(m.engine_hz(100, 0, 12, 0, 1), 50)
        self.assertAlmostEqual(m.engine_hz(100, 12, 0, 5, 0), 200)  # limitado

    def test_doppler_static(self):
        self.assertAlmostEqual(m.doppler_pitch(0, 0), 1.0)

    def test_doppler_approach_and_clamp(self):
        self.assertGreater(m.doppler_pitch(30, 0), 1.0)
        self.assertEqual(m.doppler_pitch(105, 0), 1.2)   # valor crudo 1.44
        self.assertEqual(m.doppler_pitch(-105, 0), 0.8)  # alejándose rápido
        self.assertTrue(0.8 <= m.doppler_pitch(400, 0) <= 1.2)  # sin división por cero

    def test_pulse_rate(self):
        self.assertAlmostEqual(m.pulse_rate(6000, 2), 100)
        self.assertAlmostEqual(m.pulse_rate(6000, 4), 50)
        self.assertAlmostEqual(m.pulse_rate(6000, kind="prop", blades=2), 200)
        self.assertAlmostEqual(m.pulse_rate(6000, kind="electric", pole_pairs=7), 700)
        with self.assertRaises(ValueError):
            m.pulse_rate(1, stroke=3)


if __name__ == "__main__":
    unittest.main()
