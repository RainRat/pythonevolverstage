import random

from tools.tiny_hll_trial import compile_spec, mutate_spec, random_spec
from tools.tiny_hill_search import assemble


def test_structural_mutation_stays_legal():
    rng = random.Random(10)
    for _ in range(100):
        spec = mutate_spec(random_spec(rng), rng)
        entry, body = assemble(compile_spec(spec))
        assert entry == 0 and len(body) == 20
