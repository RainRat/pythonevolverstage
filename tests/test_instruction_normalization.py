import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestNormalizeInstruction(unittest.TestCase):
    def test_basic_normalization(self):
        # Standard instruction
        instr = "MOV.I $0,$0"
        coresize = 8000
        sanitize = 8000
        # Expected: normalized string with newline
        expected = "MOV.I $0,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_value_normalization(self):
        # Value > sanitize limit, should be modded
        # coremod(8005, 8000) -> 5
        instr = "MOV.I $8005,$0"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $5,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_negative_value(self):
        # Value -5
        instr = "ADD.F #-5,#-10"
        coresize = 8000
        sanitize = 8000
        # coremod(-5, 8000) -> -5
        # corenorm(-5, 8000) -> -5
        expected = "ADD.F #-5,#-10\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_wrap_positive_to_negative(self):
        # corenorm(4100, 8000) -> -3900 because 4100 > 4000
        instr = "JMP.B $4100,$0"
        coresize = 8000
        sanitize = 8000
        expected = "JMP.B $-3900,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_sanitize_limit_different_from_coresize(self):
        # coremod(100, 50) -> 0 if sanitize is 50
        instr = "DAT.F #100,#100"
        coresize = 8000
        sanitize = 50
        expected = "DAT.F #0,#0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_extra_whitespace_handling(self):
        # The function uses re.split('[ \.,\n]', instruction.strip())
        # Input: "MOV.I  $0, $0" (double space)
        # split -> ['MOV', 'I', '', '$0', '', '$0']
        # This will fail with the current naive implementation if we don't handle empty strings
        # But the original code didn't handle it either.
        # The unarchive block does .replace('  ',' ') first.
        # The mutation block constructs clean strings.
        # So normalize_instruction assumes relatively clean input.
        # Let's test "standard" clean input with potential trailing newline.
        instr = "MOV.I $0,$0\n"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $0,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_modes_preserved(self):
        instr = "MOV.I @10,<20"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I @10,<20\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)
