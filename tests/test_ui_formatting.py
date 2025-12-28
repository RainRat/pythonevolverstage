import sys
import os
import unittest
import math

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestFormatTimeRemaining(unittest.TestCase):
    def test_zero_seconds(self):
        """Test formatting 0 seconds."""
        self.assertEqual(evolverstage.format_time_remaining(0), "00:00:00")

    def test_seconds_only(self):
        """Test formatting < 60 seconds."""
        self.assertEqual(evolverstage.format_time_remaining(59), "00:00:59")

    def test_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        # 61 seconds = 1 min 1 sec
        self.assertEqual(evolverstage.format_time_remaining(61), "00:01:01")
        # 119 seconds = 1 min 59 sec
        self.assertEqual(evolverstage.format_time_remaining(119), "00:01:59")

    def test_hours_minutes_seconds(self):
        """Test formatting hours, minutes, and seconds."""
        # 3600 seconds = 1 hour
        self.assertEqual(evolverstage.format_time_remaining(3600), "01:00:00")
        # 3661 seconds = 1 hour, 1 min, 1 sec
        self.assertEqual(evolverstage.format_time_remaining(3661), "01:01:01")

    def test_large_hours(self):
        """Test large number of hours."""
        # 100 hours = 360,000 seconds
        self.assertEqual(evolverstage.format_time_remaining(360000), "100:00:00")

    def test_negative_input(self):
        """Test negative input returns zero time."""
        self.assertEqual(evolverstage.format_time_remaining(-10), "00:00:00")

    def test_float_input(self):
        """Test floating point input is truncated properly."""
        # 60.9 seconds.
        # divmod(60.9, 60) -> (1.0, 0.9)
        # h, m = divmod(1.0, 60) -> (0.0, 1.0)
        # int(h)=0, int(m)=1, int(s)=0 (int(0.9) is 0)
        # So it should be 00:01:00
        self.assertEqual(evolverstage.format_time_remaining(60.9), "00:01:00")

class TestDrawProgressBar(unittest.TestCase):
    def test_zero_percent(self):
        """Test 0% progress."""
        # Default width 30
        result = evolverstage.draw_progress_bar(0)
        expected_bar = '-' * 30
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("0.00%", result)

    def test_hundred_percent(self):
        """Test 100% progress."""
        result = evolverstage.draw_progress_bar(100)
        expected_bar = '=' * 30
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("100.00%", result)

    def test_fifty_percent(self):
        """Test 50% progress."""
        result = evolverstage.draw_progress_bar(50)
        expected_bar = '=' * 15 + '-' * 15
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("50.00%", result)

    def test_custom_width(self):
        """Test with custom width."""
        result = evolverstage.draw_progress_bar(50, width=10)
        expected_bar = '=' * 5 + '-' * 5
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("50.00%", result)

    def test_negative_percent(self):
        """Test negative percentage is clamped to 0%."""
        result = evolverstage.draw_progress_bar(-10)
        expected_bar = '-' * 30
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("0.00%", result) # Note: function modifies percent variable locally

    def test_over_hundred_percent(self):
        """Test >100% is clamped to 100%."""
        result = evolverstage.draw_progress_bar(150)
        expected_bar = '=' * 30
        self.assertIn(f"[{expected_bar}]", result)
        self.assertIn("100.00%", result)
