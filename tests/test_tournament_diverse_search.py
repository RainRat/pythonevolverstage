import random

from tools.tournament_diverse_search import mutate_tournament


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
