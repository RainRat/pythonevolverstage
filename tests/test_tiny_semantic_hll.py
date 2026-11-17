import battle_runner

from tools.tiny_hill_search import assemble
from tools.tiny_semantic_hll import ARCHES, behavior, compile_program


def test_compiled_architectures_and_measured_behavior():
    battle_runner._load_cpp_worker_library()
    worker = battle_runner._get_internal_worker_library()
    profile = {}
    for arch in ARCHES:
        source = compile_program({"arch": arch, "step": 37, "offset": 311,
                                  "second": 509, "count": 28})
        entry, instructions = assemble(source)
        assert entry == 0 and len(instructions) == 20
        profile[arch] = behavior(source, worker)[-1]
    assert profile["paper"]["max_processes"] > 1
    assert profile["paper"]["executed_outside"] == 1
    assert profile["paper_booted"]["max_processes"] > profile["paper"]["max_processes"]
    assert profile["scan_clear"]["max_processes"] == 1
    assert profile["bounded_scan_clear"]["max_processes"] == 1
    assert profile["clear"]["null_died"] == 1
