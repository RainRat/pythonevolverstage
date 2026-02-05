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
        # The function should handle varied whitespace
        instr = "MOV.I   $0,  $0\n"
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

    def test_no_modifier_default_to_i(self):
        # Instruction without modifier should default to .I
        instr = "MOV $0,$0"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $0,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_no_addressing_modes_default_to_direct(self):
        # Instruction without addressing modes should default to $
        instr = "MOV.I 0,0"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $0,$0\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_case_insensitivity(self):
        # Lowercase should be normalized to uppercase
        instr = "mov.i $1,$2"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $1,$2\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_spaces_around_comma(self):
        instr = "MOV.I $1 , $2"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $1,$2\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)

    def test_tab_characters(self):
        instr = "MOV.I\t$1,\t$2"
        coresize = 8000
        sanitize = 8000
        expected = "MOV.I $1,$2\n"
        result = evolverstage.normalize_instruction(instr, coresize, sanitize)
        self.assertEqual(result, expected)
