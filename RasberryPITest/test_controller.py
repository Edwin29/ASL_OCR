import unittest
from unittest.mock import patch

import raspberry_pi_load as load


class ControllerTests(unittest.TestCase):
    def test_cpu_percent(self):
        self.assertEqual(load.cpu_percent((100, 40), (200, 60)), 80.0)

    def test_cpu_percent_handles_no_elapsed_ticks(self):
        self.assertEqual(load.cpu_percent((100, 40), (100, 40)), 0.0)

    def test_defaults_are_below_hard_limit(self):
        settings = load.Settings()
        settings.validate()
        self.assertLess(settings.cpu_target, settings.upper_limit)
        self.assertLess(settings.memory_target, settings.upper_limit)
        self.assertLess(settings.upper_limit, 90.0)

    def test_rejects_ninety_percent_limit(self):
        with self.assertRaises(ValueError):
            load.Settings(upper_limit=90.0).validate()

    @patch("raspberry_pi_load.Path.read_text")
    def test_memory_usage_uses_mem_available(self, read_text):
        read_text.return_value = "MemTotal: 1000 kB\nMemAvailable: 160 kB\n"
        total, available, percent = load.read_memory()
        self.assertEqual(total, 1000 * 1024)
        self.assertEqual(available, 160 * 1024)
        self.assertEqual(percent, 84.0)


if __name__ == "__main__":
    unittest.main()
