import sys
import os
import unittest
import math
import shutil
from unittest import mock

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
        # Check for color codes in result
        self.assertIn(evolverstage.Colors.GREEN, result)
        self.assertIn(evolverstage.Colors.ENDC, result)
        # Check content ignoring color codes for bar part logic
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("0.00%", clean_result)

    def test_hundred_percent(self):
        """Test 100% progress."""
        result = evolverstage.draw_progress_bar(100)
        expected_bar = '=' * 30
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("100.00%", clean_result)

    def test_fifty_percent(self):
        """Test 50% progress."""
        result = evolverstage.draw_progress_bar(50)
        expected_bar = '=' * 15 + '-' * 15
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("50.00%", clean_result)

    def test_custom_width(self):
        """Test with custom width."""
        result = evolverstage.draw_progress_bar(50, width=10)
        expected_bar = '=' * 5 + '-' * 5
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("50.00%", clean_result)

    def test_negative_percent(self):
        """Test negative percentage is clamped to 0%."""
        result = evolverstage.draw_progress_bar(-10)
        expected_bar = '-' * 30
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("0.00%", clean_result)

    def test_over_hundred_percent(self):
        """Test >100% is clamped to 100%."""
        result = evolverstage.draw_progress_bar(150)
        expected_bar = '=' * 30
        clean_result = evolverstage.strip_ansi(result)
        self.assertIn(f"[{expected_bar}]", clean_result)
        self.assertIn("100.00%", clean_result)

class TestStripAnsi(unittest.TestCase):
    def test_strip_colors(self):
        """Test stripping basic color codes."""
        text = f"{evolverstage.Colors.GREEN}Green Text{evolverstage.Colors.ENDC}"
        self.assertEqual(evolverstage.strip_ansi(text), "Green Text")

    def test_strip_mixed_styles(self):
        """Test stripping multiple different codes."""
        text = f"{evolverstage.Colors.BOLD}{evolverstage.Colors.RED}Bold Red{evolverstage.Colors.ENDC}"
        self.assertEqual(evolverstage.strip_ansi(text), "Bold Red")

    def test_strip_complex_sequences(self):
        """Test stripping sequences with multiple parameters."""
        # \033[1;31m is Bold Red in many terminals
        text = "\033[1;31mComplex\033[0m"
        self.assertEqual(evolverstage.strip_ansi(text), "Complex")

    def test_no_ansi(self):
        """Test string without any ANSI codes."""
        text = "Plain Text"
        self.assertEqual(evolverstage.strip_ansi(text), "Plain Text")

    def test_empty_string(self):
        """Test empty string."""
        self.assertEqual(evolverstage.strip_ansi(""), "")

    def test_non_string_input(self):
        """Test non-string inputs are converted to string and stripped."""
        self.assertEqual(evolverstage.strip_ansi(123), "123")
        self.assertEqual(evolverstage.strip_ansi(None), "None")

class TestGetStrategyColor(unittest.TestCase):
    def test_paper_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Paper (Replicator)"), evolverstage.Colors.GREEN)

    def test_stone_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Stone (Bomb-thrower)"), evolverstage.Colors.RED)

    def test_imp_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Imp (Pulse)"), evolverstage.Colors.YELLOW)

    def test_vampire_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Vampire / Pittrap"), evolverstage.Colors.HEADER)

    def test_mover_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Mover / Runner"), evolverstage.Colors.BLUE)

    def test_experimental_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Experimental"), evolverstage.Colors.CYAN)

    def test_default_color(self):
        self.assertEqual(evolverstage.get_strategy_color("Unknown"), evolverstage.Colors.ENDC)
        self.assertEqual(evolverstage.get_strategy_color("Wait / Shield"), evolverstage.Colors.ENDC)

    def test_case_insensitivity(self):
        self.assertEqual(evolverstage.get_strategy_color("PAPER"), evolverstage.Colors.GREEN)

class TestGetSeparator(unittest.TestCase):
    @mock.patch('shutil.get_terminal_size')
    def test_separator_standard(self, mock_size):
        mock_size.return_value = os.terminal_size((80, 24))
        # Default char '-', default max_width 100. 80 < 100.
        self.assertEqual(evolverstage.get_separator(), "-" * 80)

    @mock.patch('shutil.get_terminal_size')
    def test_separator_capped(self, mock_size):
        mock_size.return_value = os.terminal_size((120, 24))
        # 120 > 100. Should be 100.
        self.assertEqual(evolverstage.get_separator(), "-" * 100)

    @mock.patch('shutil.get_terminal_size')
    def test_separator_custom(self, mock_size):
        mock_size.return_value = os.terminal_size((80, 24))
        self.assertEqual(evolverstage.get_separator(char="=", max_width=50), "=" * 50)

    @mock.patch('shutil.get_terminal_size')
    def test_separator_fallback_oserror(self, mock_size):
        mock_size.side_effect = OSError("No terminal")
        self.assertEqual(evolverstage.get_separator(), "-" * 80)

class TestPrintStatusLine(unittest.TestCase):
    @mock.patch('shutil.get_terminal_size')
    @mock.patch('builtins.print')
    def test_print_status_line_standard(self, mock_print, mock_size):
        mock_size.return_value = os.terminal_size((80, 24))
        # Visible length of "Test" is 4. Padding = 80 - 4 - 1 = 75.
        evolverstage.print_status_line("Test")
        expected_text = "\rTest" + " " * 75
        mock_print.assert_called_once_with(expected_text, end='\r', flush=True)

    @mock.patch('shutil.get_terminal_size')
    @mock.patch('builtins.print')
    def test_print_status_line_with_ansi(self, mock_print, mock_size):
        mock_size.return_value = os.terminal_size((80, 24))
        text = f"{evolverstage.Colors.GREEN}Test{evolverstage.Colors.ENDC}"
        # Visible length is 4.
        evolverstage.print_status_line(text)
        expected_text = f"\r{text}" + " " * 75
        mock_print.assert_called_once_with(expected_text, end='\r', flush=True)

    @mock.patch('shutil.get_terminal_size')
    @mock.patch('builtins.print')
    def test_print_status_line_fallback(self, mock_print, mock_size):
        mock_size.side_effect = OSError("No terminal")
        evolverstage.print_status_line("Test")
        # Should fallback to standard print with newline
        mock_print.assert_called_once_with("Test", end='\n', flush=True)

if __name__ == '__main__':
    unittest.main()
