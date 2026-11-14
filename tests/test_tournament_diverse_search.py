import random

import pytest

from tools.tournament_diverse_search import crossover_lines, mutate_tournament


def test_padding_choices_are_available_only_in_94_arenas():
    source = ['MOV.I $1, $1'] * 50
    variants = [mutate_tournament(source, source, random.Random(seed), 0)
                for seed in range(300)]
    assert all(len(lines) == 50 for lines in variants)
    assert any('DAT.F $0, $0' in lines for lines in variants)
    assert any(any(line.startswith('DAT.F $') and line != 'DAT.F $0, $0'
                   for line in lines) for lines in variants)
    assert all('DAT.F $0, $0' not in mutate_tournament(
        source, source, random.Random(seed), 2) for seed in range(300))


def test_crossover_sources_strip_directives_and_pad_short_warriors(tmp_path):
    old88 = tmp_path / 'old88.red'
    old88.write_text('SPL $1, $0\nMOV $0, $1\nEND 0\n')
    lines = crossover_lines(old88, 2)
    assert len(lines) == 50 and lines[:2] == ['SPL $1, $0', 'MOV $0, $1']
    assert lines[2:] == ['DAT #0, #0'] * 48

    old94 = tmp_path / 'old94.red'
    old94.write_text('ORG START\nSTART MOV.I $0, $1\nEND START\n')
    lines = crossover_lines(old94, 3)
    assert len(lines) == 50 and lines[0] == 'MOV.I $0, $1'
    assert lines[1:] == ['DAT.F $0, $0'] * 49

    old88.write_text('SPL $1, $0\nEND 0\nMOV $0, $1\n')
    with pytest.raises(ValueError):
        crossover_lines(old88, 2)
