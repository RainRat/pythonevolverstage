import random

from tools.tournament_hillclimb import fitness, mutate
from tools.tournament_diverse_search import choose_diverse


def test_hillclimb_preserves_length_and_rewards_survival():
    lines = ['MOV.I $0, $1'] * 50
    for seed in range(100):
        assert len(mutate(lines, lines, random.Random(seed))) == 50
    assert lines == ['MOV.I $0, $1'] * 50

    field = [[1.5 if i == j else 1 + (i - j) / 20 for j in range(12)]
             for i in range(12)]
    scores = []
    for candidate_score in (0, 1, 2):
        matrix = [row.copy() for row in field]
        for i in range(11):
            matrix[i][11] = 3 - candidate_score
            matrix[11][i] = candidate_score
        scores.append(fitness(matrix))
    assert scores[0][0] < scores[1][0] < scores[2][0]
    assert scores[0][1] == (9, 12)  # First eliminated from both fields.
    assert scores[2][1] == (1, 1)  # Survives both push-offs.


def test_archive_seeds_are_distinct(tmp_path):
    candidates = []
    for index in range(5):
        path = tmp_path / f'{index}.red'
        path.write_text((f'MOV.I ${index}, $0\n') * 50)
        candidates.append((1 - index/10, (1 - index/10, 0, 0), path))
    chosen = choose_diverse(candidates, 3)
    assert len(set(chosen)) == 3
    assert chosen[0] == candidates[0][2]
