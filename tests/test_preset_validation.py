# AI-assisted unit tests; no MongoDB or injection process is used.
import unittest
from preset_validation import validate_preset

class PresetValidationTests(unittest.TestCase):
    def test_four_types(self):
        for kind, parameters in [
            ("cpu", {"cpu_percent": 20, "duration_seconds": 10}),
            ("latency", {"latency_ms": 12.5}),
            ("packet_loss", {"packet_loss_percent": 2.5}),
            ("memory", {"memory_mb": 128, "duration_seconds": 10}),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(validate_preset(" Demo ", kind, parameters)["parameters"], parameters)
        self.assertEqual(validate_preset(" Demo ", "cpu", {"cpu_percent": 20, "duration_seconds": 10})["name"], "Demo")

    def test_invalid_parameters(self):
        for kind, parameters in [
            ("cpu", {"cpu_percent": 66, "duration_seconds": 10}),
            ("cpu", {"cpu_percent": True, "duration_seconds": 10}),
            ("cpu", {"cpu_percent": float("nan"), "duration_seconds": 10}),
            ("cpu", {"cpu_percent": 20, "duration_seconds": 1.5}),
            ("cpu", {"cpu_percent": 20}),
            ("cpu", {"cpu_percent": 20, "duration_seconds": 10, "extra": 1}),
            ("memory", {"memory_mb": 4097, "duration_seconds": 10}),
            ("latency", {"latency_ms": -1}),
            ("packet_loss", {"packet_loss_percent": 51}),
            ("unknown", {}),
        ]:
            with self.subTest(kind=kind, parameters=parameters):
                with self.assertRaises(ValueError): validate_preset("Demo", kind, parameters)

    def test_invalid_names(self):
        for name in [" ", "x" * 81, "x\ny", None]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): validate_preset(name, "latency", {"latency_ms": 0})

if __name__ == "__main__": unittest.main()
