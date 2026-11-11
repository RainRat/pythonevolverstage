from tools.tournament_evidence import push_off


def test_push_off_returns_elimination_positions():
    matrix = [
        [1.5, 0, 0],
        [3, 1.5, 0],
        [3, 3, 1.5],
    ]
    ranks = push_off(matrix, [0, 1, 2])
    assert sorted(ranks.values()) == [1, 2, 3]
    assert ranks[2] == 1
