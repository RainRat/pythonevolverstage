from subprocess import CompletedProcess

from tools import tiny_hill_search


def test_tiny_battle_uses_sampled_placements(monkeypatch, tmp_path):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, 0, "candidate scores 17\nopponent scores 23\nResults: 4 6 0\n", "")

    monkeypatch.setattr(tiny_hill_search.subprocess, "run", fake_run)
    candidate = tmp_path / "candidate.red"
    opponent = tmp_path / "opponent.red"
    assert tiny_hill_search.battle(candidate, opponent, 12345, 10) == 17
    command = commands[0]
    assert command[command.index("-F") + 1] == "12345"
    assert command[command.index("-r") + 1] == "10"
    assert "-P" not in command
    assert all(flag in command for flag in ("-s", "-p", "-c", "-d", "-l"))
