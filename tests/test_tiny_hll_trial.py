import random

from tools.tiny_hll_trial import compile_spec, mutate_spec, random_spec
from tools.tiny_hill_search import assemble
from tools.tiny_hll_rich import compile_genome, mutate_genome, random_genome


def test_structural_mutation_stays_legal():
    rng = random.Random(10)
    for _ in range(100):
        spec = mutate_spec(random_spec(rng), rng)
        entry, body = assemble(compile_spec(spec))
        assert entry == 0 and len(body) == 20


def test_richer_genomes_stay_legal():
    bodies = [["DAT.F $0, $0"] * 20,
              ["MOV.I $0, $1"] + ["DAT.F $0, $0"] * 19]
    rng = random.Random(11)
    for _ in range(100):
        genome = mutate_genome(random_genome(rng, len(bodies)), rng, len(bodies))
        entry, body = assemble(compile_genome(genome, bodies))
        assert entry == 0 and len(body) == 20
