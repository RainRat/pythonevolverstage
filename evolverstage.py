# A Python-based Evolver for Core War
# This script manages the evolution, breeding, and battling of warriors across multiple arenas.

'''
Core War Evolver

Evolve and test Redcode warriors using an evolutionary process.
For license information, see LICENSE.md.

Usage:
  python evolverstage.py [COMMAND] [OPTIONS]

General Commands:
  --check, -c          Check your configuration and simulator setup.
  --status, -s         Display the current status of all arenas and population.
                       Add --watch or -w for real-time monitoring.
                       Add --interval <N> to set refresh rate (default 2s).
                       Add --json for machine-readable output.
  --leaderboard, -l    Show the top-performing warriors based on recent win streaks.
                       Usage: --leaderboard [--arena <N>] [--top <N>] [--json]
  --trends, -r         Analyze evolution trends by comparing the population to the top performers.
                       Usage: --trends [--arena <N>]
  --report, -g         Generate a comprehensive health and performance report for an arena.
                       Usage: --report [--arena <N>]
  --dump-config, -d    Show the active configuration from settings.ini and exit.

Evolution:
  --restart            Start a new evolution from scratch (overwrites existing files).
  --resume             Continue evolution using existing warriors and logs.
  --seed               Populate an arena with a set of specific warriors.
                       Usage: --seed <targets...> [--arena <N>]
  (Run with no command to start/continue evolution based on settings.ini)

Battle Tools:
  --battle, -b         Run a match between two specific warriors.
                       Defaults to 'top' vs 'top2' if no targets provided.
                       Usage: --battle [target1] [target2] [--arena <N>]
  --tournament, -t     Run an everyone-vs-everyone tournament between a group of warriors.
                       Defaults to the top 10 warriors of the current arena if no targets provided.
                       Use --champions to automatically include winners from every arena.
                       Usage: --tournament <folder|selectors...> [--champions] [--arena <N>]
  --benchmark, -m      Test one warrior against every opponent in a folder.
                       Usage: --benchmark <warrior> <folder> [--arena <N>]

Analysis & Utilities:
  --inspect, -x        Get a comprehensive profile of a warrior's performance and code.
                       Usage: --inspect [targets...] [--arena <N>]
                       Supports multiple targets. Defaults to 'top' if none provided.
  --lineage, -j        Trace the genealogy (parentage) of a warrior from the battle log.
                       Usage: --lineage [warrior|selector] [--depth <N>] [--arena <N>]
                       Defaults to the current champion ('top') if no target is provided.
  --analyze, -i        Get statistics on instructions, opcodes, and addressing modes.
                       Usage: --analyze [file|folder|selector] [--arena <N>] [--json]
                       Defaults to the current champion ('top') if no target is provided.
  --meta, -u           Analyze the distribution of strategies in the population or a folder.
                       Usage: --meta [file|folder|selector] [--arena <N>] [--json]
                       Defaults to the current arena if no target is provided.
  --gauntlet, -G       Test a warrior against the champions of all arenas.
                       Usage: --gauntlet [warrior|selector] [--arena <N>]
                       Defaults to the current champion ('top') if no target is provided.
  --compare, -y        Compare two warriors, folders, or selectors side-by-side.
                       Defaults to 'top' vs 'top2' if no targets provided.
                       Usage: --compare [target1] [target2] [--arena <N>] [--json]
  --diff, -f           Perform a line-by-line code comparison between two warriors.
                       Defaults to 'top' vs 'top2' if no targets provided.
                       Usage: --diff [target1] [target2] [--arena <N>]
  --view, -v           Display the source code of a warrior.
                       Usage: --view [warrior|selector] [--arena <N>]
                       Defaults to the current champion ('top') if no target is provided.
  --normalize, -n      Clean and standardize a warrior's Redcode format.
                       Usage: --normalize <warrior|selector> [--arena <N>]
  --harvest, -p        Collect the best warriors from the leaderboard into a folder.
                       Usage: --harvest <folder> [--top <N>] [--arena <N>]
  --export, -e         Save a warrior with a standard Redcode header and normalization.
                       Usage: --export [selector] [--output <file>] [--arena <N>]
                       Defaults to the current champion ('top') if no target is provided.
  --collect, -k        Extract and normalize instructions from warriors into a library file.
                       Usage: --collect <targets...> [-o <output>] [--arena <N>]

Dynamic Selectors:
  Instead of a filename, you can use these keywords in most commands:
  top, topN            Select the #1 (or #N) warrior from the leaderboard.
  random               Select a random warrior from the current population.
  selector@N           Target a specific arena (e.g., top@0, random@2).

Examples:
  python evolverstage.py --status
  python evolverstage.py --battle top1 top2
  python evolverstage.py --inspect top1 top2 top3
  python evolverstage.py --battle top@0 top@1
  python evolverstage.py --compare top@0 top@1
  python evolverstage.py --export top@0 --output champion.red
  python evolverstage.py --tournament --champions
  python evolverstage.py --benchmark top archive/
  python evolverstage.py --view random@2
  python evolverstage.py --lineage top --depth 5
  python evolverstage.py --seed best_warriors/ --arena 0
  python evolverstage.py --gauntlet top
'''

import random
import itertools
import os
import re
import time
import sys
import shutil
import json
import difflib
#import psutil #Not currently active. See bottom of code for how it could be used.
import configparser
import subprocess
from enum import Enum
import csv
import hashlib
from collections import deque

from evolver.logger import DataLogger

VERSION = "1.1.0"

# Standard Redcode instruction parser regex
# Format: OPCODE[.MODIFIER] [<MODE>A-VAL[,<MODE>B-VAL]]
RE_INSTRUCTION = re.compile(r'^([A-Z]+)(?:\.([A-Z]+))?(?:\s+([^,]+)(?:,\s*(.+))?)?$', re.I)

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class Marble(Enum):
  DO_NOTHING = 0
  MAJOR_MUTATION = 1
  NAB_INSTRUCTION = 2
  MINOR_MUTATION = 3
  MICRO_MUTATION = 4
  INSTRUCTION_LIBRARY = 5
  MAGIC_NUMBER_MUTATION = 6

def format_time_remaining(seconds):
    """Formats seconds into HH:MM:SS."""
    if seconds < 0: seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "{:02d}:{:02d}:{:02d}".format(int(h), int(m), int(s))

def strip_ansi(text):
    """Removes ANSI escape codes from a string."""
    return re.sub(r'\033\[[0-9;]*m', '', str(text))

def draw_progress_bar(percent, width=30):
    """Returns a string representing a progress bar."""
    if percent < 0: percent = 0
    if percent > 100: percent = 100
    filled_length = int(width * percent // 100)
    filled_bar = '=' * filled_length
    empty_bar = '-' * (width - filled_length)
    return f"[{Colors.GREEN}{filled_bar}{Colors.ENDC}{empty_bar}] {percent:6.2f}%"

def print_status_line(text, end='\r'):
    """Clears the current line and prints the status text with proper terminal width handling."""
    try:
        cols, _ = shutil.get_terminal_size()
        visible_len = len(strip_ansi(text))
        padding = " " * max(0, cols - visible_len - 1)
        print(f"\r{text}{padding}", end=end, flush=True)
    except (OSError, ValueError):
        try:
            # Fallback for environments without a proper terminal or closed stdout
            print(text, end='\n', flush=True)
        except OSError:
            pass

def _get_nmars_cmd():
    """Returns the nMars executable name based on the operating system."""
    return "nmars.exe" if os.name == "nt" else "nmars"

def run_nmars_subprocess(cmd):
    """
    Executes the nmars command with the given arguments.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    except FileNotFoundError:
        print(f"Error: The simulator '{cmd[0]}' was not found.")
        print("Please ensure the nMars executable is in the project folder and has the correct permissions (e.g., 'chmod +x nmars' on Linux/macOS).")
    except subprocess.SubprocessError as e:
        print(f"An unexpected error occurred while running the simulator: {e}")
    return None

def construct_battle_command(file1, file2, arena_idx, coresize=None, cycles=None, processes=None, warlen=None, wardistance=None, rounds=None):
    """
    Constructs the nMars command for battling two specific files.
    """
    s = coresize if coresize is not None else CORESIZE_LIST[arena_idx]
    c = cycles if cycles is not None else CYCLES_LIST[arena_idx]
    p = processes if processes is not None else PROCESSES_LIST[arena_idx]
    l = warlen if warlen is not None else WARLEN_LIST[arena_idx]
    d = wardistance if wardistance is not None else WARDISTANCE_LIST[arena_idx]
    if rounds is None:
        # Use the battlerounds from the last era (Optimization) as default for manual battles
        rounds = BATTLEROUNDS_LIST[-1] if BATTLEROUNDS_LIST else 100

    return [
        _get_nmars_cmd(),
        file1,
        file2,
        "-s", str(s),
        "-c", str(c),
        "-p", str(p),
        "-l", str(l),
        "-d", str(d),
        "-r", str(rounds)
    ]

def run_custom_battle(file1, file2, arena_idx):
    """
    Runs a single battle between two warrior files using the specified arena configuration.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    if not os.path.exists(file1):
        print(f"Error: File '{file1}' not found.")
        return
    if not os.path.exists(file2):
        print(f"Error: File '{file2}' not found.")
        return

    # Determine rounds to use for the battle and visual scaling
    rounds = BATTLEROUNDS_LIST[-1] if BATTLEROUNDS_LIST else 100
    cmd = construct_battle_command(file1, file2, arena_idx, rounds=rounds)

    print(f"{Colors.BOLD}Starting battle: {file1} vs {file2}{Colors.ENDC}")
    print(f"Arena: {arena_idx} (Size: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]}, Rounds: {rounds})")

    output = run_nmars_subprocess(cmd)

    if output:
        scores, warriors = parse_nmars_output(output)
        if len(scores) >= 2:
            # ID 1 is file1, ID 2 is file2 (based on construct_battle_command order)
            score_map = {warriors[i]: scores[i] for i in range(len(warriors))}
            s1 = score_map.get(1, 0)
            s2 = score_map.get(2, 0)

            res_winner_id, res_loser_id = determine_winner([s1, s2], [1, 2])

            w1_name = os.path.basename(file1)
            w2_name = os.path.basename(file2)
            w1_id = w1_name.replace(".red", "")
            w2_id = w2_name.replace(".red", "")

            # Retrieve current win-streaks from the leaderboard for performance context
            leaderboard = get_leaderboard(arena_idx=arena_idx)
            streaks = {w1_id: 0, w2_id: 0}
            if arena_idx in leaderboard:
                for wid, streak in leaderboard[arena_idx]:
                    if str(wid) == w1_id: streaks[w1_id] = streak
                    if str(wid) == w2_id: streaks[w2_id] = streak

            # Color-coding for scores (Green for winner, Red for loser, Yellow for tie)
            c1 = Colors.GREEN if s1 > s2 else Colors.RED if s1 < s2 else Colors.YELLOW
            c2 = Colors.GREEN if s2 > s1 else Colors.RED if s2 < s1 else Colors.YELLOW

            # Implementation of a visual horizontal comparison bar for scores
            bar_width = 20
            total_for_bar = max(s1 + s2, rounds)
            b1_fill = int(bar_width * s1 / total_for_bar)
            b2_fill = int(bar_width * s2 / total_for_bar)
            bar1 = f"[{c1}{'=' * b1_fill}{' ' * (bar_width - b1_fill)}{Colors.ENDC}]"
            bar2 = f"[{c2}{'=' * b2_fill}{' ' * (bar_width - b2_fill)}{Colors.ENDC}]"

            # Standardized Polished Output Format
            print("-" * 75)
            print(f"{Colors.BOLD}BATTLE RESULT (Arena {arena_idx}){Colors.ENDC}")
            print("-" * 75)

            # Identify strategies for both contestants to provide tactical context
            s1_strat = identify_strategy(analyze_warrior(file1))
            s2_strat = identify_strategy(analyze_warrior(file2))

            streak1 = f"(Streak: {streaks[w1_id]})" if streaks[w1_id] > 0 else ""
            streak2 = f"(Streak: {streaks[w2_id]})" if streaks[w2_id] > 0 else ""

            # Use formatted strings with fixed-width columns
            print(f"  Warrior 1: {w1_name:<25} {c1}{s1:>5}{Colors.ENDC} {bar1} {Colors.CYAN}{streak1:<13} {s1_strat}{Colors.ENDC}")
            print(f"  Warrior 2: {w2_name:<25} {c2}{s2:>5}{Colors.ENDC} {bar2} {Colors.CYAN}{streak2:<13} {s2_strat}{Colors.ENDC}")
            print("-" * 75)

            if s1 == s2:
                print(f"  {Colors.BOLD}{Colors.YELLOW}RESULT: TIE{Colors.ENDC}")
            else:
                winner_name = w1_name if res_winner_id == 1 else w2_name
                diff = abs(s1 - s2)
                print(f"  {Colors.BOLD}WINNER: {Colors.GREEN}{winner_name}{Colors.ENDC} (+{diff})")
            print("-" * 75)
        else:
            # Fallback to raw output if parsing fails
            print("-" * 40)
            print(output.strip())
            print("-" * 40)
    else:
        print(f"{Colors.RED}No output received from nMars.{Colors.ENDC}")

def run_tournament(targets, arena_idx):
    """
    Runs an everyone-vs-everyone tournament between a folder of warriors or a specific list of warriors.
    """
    if isinstance(targets, str):
        targets = [targets]

    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    abs_files = []
    file_map = {}

    # Check if we are given a single folder
    if len(targets) == 1 and os.path.isdir(targets[0]):
        directory = targets[0]
        files = [f for f in os.listdir(directory) if f.endswith('.red')]
        if len(files) < 2:
            print(f"Error: A tournament requires at least two warriors (.red files) in the '{directory}' folder.")
            return
        abs_files = [os.path.join(directory, f) for f in files]
        file_map = {path: f for path, f in zip(abs_files, files)}
        print(f"Tournament: {len(files)} warriors from folder '{directory}'")
    else:
        # It's a list of selectors/files (including the case of a single selector)
        for sel in targets:
            path = _resolve_warrior_path(sel, arena_idx)
            if os.path.exists(path):
                abs_files.append(path)
                file_map[path] = sel
            else:
                if len(targets) == 1:
                    # Single target that doesn't exist as a folder or resolve as a selector
                    print(f"Error: Folder or selector '{targets[0]}' not found.")
                    return
                else:
                    print(f"Warning: Warrior '{sel}' not found. Skipping.")

        if len(abs_files) < 2:
            print("Error: A tournament requires at least two warriors to compete.")
            return
        print(f"Tournament: {len(abs_files)} selected warriors.")

    scores = {file_map[f]: 0 for f in abs_files}

    # Generate pairs
    pairs = list(itertools.combinations(abs_files, 2))
    rounds = BATTLEROUNDS_LIST[-1] if BATTLEROUNDS_LIST else 100
    total_battles = len(pairs)
    print(f"Total battles: {total_battles}")
    print(f"Arena: {arena_idx} (Size: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]}, Rounds: {rounds})")

    last_res = ""
    for i, (p1, p2) in enumerate(pairs, 1):
        # Progress
        percent = ((i - 1) / total_battles) * 100
        bar = draw_progress_bar(percent, width=15)
        status = f"Battle {i}/{total_battles}: {file_map[p1]} vs {file_map[p2]}"

        line = f"{bar} {status}"
        if last_res:
            line += f" | {last_res}"

        print_status_line(line)

        cmd = construct_battle_command(p1, p2, arena_idx)
        output = run_nmars_subprocess(cmd)

        s, warriors = parse_nmars_output(output)

        # Determine last result for next iteration
        if len(s) >= 2:
            res_winner, res_loser = determine_winner(s, warriors)
            w_name = file_map[p1] if res_winner == 1 else file_map[p2]
            l_name = file_map[p1] if res_loser == 1 else file_map[p2]
            last_res = f"Last: {Colors.GREEN}{w_name}{Colors.ENDC}>{Colors.RED}{l_name}{Colors.ENDC}"

        # Mapping back scores to filenames
        # parse_nmars_output returns [score1, score2] and [id1, id2]
        # We assume nMars preserves order: ID 1 is first arg (p1), ID 2 is second arg (p2)
        # However, parse_nmars_output's logic appends them in order of output.
        # Usually output is: "1 scores X" then "2 scores Y".
        # But we should rely on warrior ID returned in 'warriors' list.
        # ID 1 -> p1, ID 2 -> p2

        for idx, warrior_id in enumerate(warriors):
            points = s[idx]
            if warrior_id == 1:
                scores[file_map[p1]] += points
            elif warrior_id == 2:
                scores[file_map[p2]] += points

    # Final progress line
    bar = draw_progress_bar(100.0, width=15)
    line = f"{bar} Tournament Complete | {last_res}"
    print_status_line(line, end='\n')

    # Standardized Polished Results Format
    print("-" * 75)
    print(f"{Colors.BOLD}TOURNAMENT RESULTS (Arena {arena_idx}){Colors.ENDC}")
    print("-" * 75)
    print(f"{'Rank':<4} {'Warrior':<25} {'Strategy':<20} {'Score':>7}  {'Performance'}")
    print("-" * 75)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    max_possible = (len(abs_files) - 1) * rounds

    for rank, (name, score) in enumerate(sorted_scores, 1):
        color = Colors.GREEN if rank == 1 else Colors.ENDC
        # Use basename for display if it looks like a path
        display_name = os.path.basename(name)
        path = _resolve_warrior_path(name, arena_idx)
        strat = identify_strategy(analyze_warrior(path))

        # Visual bar
        bar_width = 20
        fill = int(bar_width * score / max_possible) if max_possible > 0 else 0
        bar = f"[{color}{'=' * fill}{' ' * (bar_width - fill)}{Colors.ENDC}]"

        print(f"{rank:>2}.  {display_name:<25} {strat:<20} {color}{score:>7}{Colors.ENDC}  {bar}")
    print("-" * 75)

def run_benchmark(warrior_file, directory, arena_idx):
    """
    Runs a benchmark of a specific warrior against all warriors in a folder.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    if not os.path.exists(warrior_file):
        print(f"Error: File '{warrior_file}' not found.")
        return
    if not os.path.exists(directory):
        print(f"Error: Folder '{directory}' not found.")
        return

    opponents = [f for f in os.listdir(directory) if f.endswith('.red')]
    if not opponents:
        print(f"Error: No opponents found. Please ensure the folder '{directory}' contains .red files.")
        return

    print(f"Benchmarking {warrior_file} against {len(opponents)} warriors in folder: {directory}")
    print(f"Arena: {arena_idx} (Size: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]})")

    stats = {
        'wins': 0,
        'losses': 0,
        'ties': 0,
        'score': 0,
        'total_rounds': 0
    }

    # Use absolute path for warrior_file to avoid issues if directory is different
    abs_warrior_file = os.path.abspath(warrior_file)

    last_res = ""
    for i, opp in enumerate(opponents, 1):
        opp_path = os.path.join(directory, opp)
        # Progress
        percent = ((i - 1) / len(opponents)) * 100
        bar = draw_progress_bar(percent, width=15)
        status = f"Battle {i}/{len(opponents)}: vs {opp}"

        line = f"{bar} {status}"
        if last_res:
            line += f" | {last_res}"

        print_status_line(line)

        cmd = construct_battle_command(abs_warrior_file, opp_path, arena_idx)
        output = run_nmars_subprocess(cmd)

        scores, warriors = parse_nmars_output(output)

        # Determine last result
        if len(scores) >= 2:
            res_winner, res_loser = determine_winner(scores, warriors)
            w_label = f"{Colors.GREEN}Win{Colors.ENDC}" if res_winner == 1 else f"{Colors.RED}Loss{Colors.ENDC}"
            last_res = f"Last: {w_label}"

        # Determine my score
        my_score = 0
        opp_score = 0

        # We assume warrior_file (arg 1) corresponds to ID 1 in nMars output.
        # parse_nmars_output returns [score1, score2, ...] and [id1, id2, ...]
        # Map ID to score.
        score_map = {}
        for idx, warrior_id in enumerate(warriors):
             if idx < len(scores):
                 score_map[warrior_id] = scores[idx]

        my_score = score_map.get(1, 0)
        opp_score = score_map.get(2, 0) # Assuming opponent is ID 2

        stats['score'] += my_score
        stats['total_rounds'] += 1

        if my_score > opp_score:
            stats['wins'] += 1
        elif my_score < opp_score:
            stats['losses'] += 1
        else:
            stats['ties'] += 1

    # Final progress line
    bar = draw_progress_bar(100.0, width=15)
    line = f"{bar} Benchmark Complete | {last_res}"
    print_status_line(line, end='\n')

    print(f"\n{Colors.BOLD}Benchmark Results for {warrior_file}:{Colors.ENDC}")
    print(f"  Total Battles: {len(opponents)}")
    if len(opponents) > 0:
        print(f"  {Colors.GREEN}Wins:   {stats['wins']} ({stats['wins']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  {Colors.RED}Losses: {stats['losses']} ({stats['losses']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  {Colors.YELLOW}Ties:   {stats['ties']} ({stats['ties']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  Total Score: {stats['score']}")
        print(f"  Average Score: {stats['score']/len(opponents):.2f}")

def run_gauntlet(target, arena_idx):
    """
    Tests a warrior against the champions (top1) of all existing arenas.
    Each battle uses the rules and configuration of the respective arena.
    """
    path = _resolve_warrior_path(target, arena_idx)
    if not os.path.exists(path):
        print(f"{Colors.RED}Error: Warrior '{target}' not found.{Colors.ENDC}")
        return

    # Identify target's strategy
    target_strat = identify_strategy(analyze_warrior(path))
    target_name = os.path.basename(path)

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- THE GAUNTLET: {target_name} ({target_strat}) ---{Colors.ENDC}")
    print(f"Testing against all arena champions using their home rules.")
    print("-" * 85)
    print(f"{Colors.BOLD}{'Arena':<6} {'Champion':<15} {'Strategy':<20} {'Result':<10} {'Score':<10} {'Rules'}{Colors.ENDC}")
    print("-" * 85)

    wins = 0
    ties = 0
    total = 0

    # Use absolute path for target to avoid issues
    abs_path = os.path.abspath(path)

    for i in range(LAST_ARENA + 1):
        champ_path = _resolve_warrior_path("top", i)
        if not os.path.exists(champ_path):
            continue

        total += 1
        champ_name = os.path.basename(champ_path)
        champ_strat = identify_strategy(analyze_warrior(champ_path))

        # Home rules
        rules = f"S:{CORESIZE_LIST[i]} C:{CYCLES_LIST[i]}"

        # Use final era rounds as standard for tests
        rounds = BATTLEROUNDS_LIST[-1] if BATTLEROUNDS_LIST else 100
        cmd = construct_battle_command(abs_path, champ_path, i, rounds=rounds)
        output = run_nmars_subprocess(cmd)

        res_label = f"{Colors.RED}LOSS{Colors.ENDC}"
        score_str = "0-0"

        if output:
            scores, warriors = parse_nmars_output(output)
            if len(scores) >= 2:
                # ID 1 is target, ID 2 is champ_path
                score_map = {warriors[k]: scores[k] for k in range(len(warriors))}
                s1 = score_map.get(1, 0)
                s2 = score_map.get(2, 0)
                score_str = f"{s1}-{s2}"

                if s1 > s2:
                    res_label = f"{Colors.GREEN}WIN{Colors.ENDC}"
                    wins += 1
                elif s1 == s2:
                    res_label = f"{Colors.YELLOW}TIE{Colors.ENDC}"
                    ties += 1

        print(f"{i:<6} {champ_name:<15} {champ_strat:<20} {res_label:<20} {score_str:<10} {rules}")

    print("-" * 85)
    win_rate = (wins / total * 100) if total > 0 else 0
    print(f"{Colors.BOLD}OVERALL PERFORMANCE:{Colors.ENDC} {wins} Wins, {ties} Ties, {total - wins - ties} Losses ({win_rate:.1f}% win rate)")
    print("-" * 85)

def run_normalization(filepath, arena_idx, output_path=None):
    """
    Reads a warrior file (or folder) and outputs the normalized instructions.

    If filepath is a folder, output_path must be a folder.
    If filepath is a file:
      - if output_path is set, writes to that file.
      - if output_path is None, prints to stdout.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return

    # Folder Mode
    if os.path.isdir(filepath):
        if not output_path:
            print("Error: Output folder must be specified when normalizing a folder.")
            return

        os.makedirs(output_path, exist_ok=True)

        files = [f for f in os.listdir(filepath) if f.endswith('.red')]
        if not files:
            print(f"No .red files found in {filepath}")
            return

        print(f"Normalizing {len(files)} files from {filepath} to {output_path}...")
        for i, f in enumerate(files, 1):
            percent = ((i - 1) / len(files)) * 100
            bar = draw_progress_bar(percent, width=15)
            print_status_line(f"{bar} Normalizing: {f}")

            in_f = os.path.join(filepath, f)
            out_f = os.path.join(output_path, f)
            # Recursive call for single file
            run_normalization(in_f, arena_idx, output_path=out_f)

        print_status_line(f"{draw_progress_bar(100.0, width=15)} Normalization complete.", end='\n')
        return

    # Single File Mode
    out_stream = sys.stdout
    file_handle = None

    if output_path:
        try:
            file_handle = open(output_path, 'w')
            out_stream = file_handle
        except OSError as e:
            print(f"Error opening output file {output_path}: {e}")
            return

    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(';'):
                continue
            try:
                normalized = normalize_instruction(line, CORESIZE_LIST[arena_idx], SANITIZE_LIST[arena_idx])
                if out_stream == sys.stdout:
                    print(normalized, end='')
                else:
                    out_stream.write(normalized)
            except (ValueError, IndexError):
                sys.stderr.write(f"Warning: Could not normalize line: {line.strip()}\n")

    except Exception as e:
        print(f"Error processing file: {e}")
    finally:
        if file_handle:
            file_handle.close()

def run_instruction_collection(targets, output_path, arena_idx):
    """
    Reads all instructions from one or more warriors (or directories),
    normalizes them, and aggregates them into a single library file.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    # Aggregate all files to process
    files_to_process = []
    for target in targets:
        # Resolve selector if needed
        resolved = _resolve_warrior_path(target, arena_idx)
        if os.path.isdir(resolved):
            files = [f for f in os.listdir(resolved) if f.endswith('.red')]
            for f in files:
                files_to_process.append(os.path.join(resolved, f))
        elif os.path.exists(resolved):
            files_to_process.append(resolved)
        else:
            print(f"Warning: Target '{target}' could not be resolved. Skipping.")

    if not files_to_process:
        print("No warriors found to collect instructions from.")
        return

    print(f"Collecting instructions from {len(files_to_process)} warriors into '{output_path}'...")

    count = 0
    try:
        with open(output_path, 'w') as out_f:
            for i, filepath in enumerate(files_to_process, 1):
                percent = ((i - 1) / len(files_to_process)) * 100
                bar = draw_progress_bar(percent, width=15)
                print_status_line(f"{bar} Collecting from: {os.path.basename(filepath)}")

                with open(filepath, 'r') as in_f:
                    for line in in_f:
                        stripped = line.strip()
                        if not stripped or stripped.startswith(';'):
                            continue
                        try:
                            normalized = normalize_instruction(line, CORESIZE_LIST[arena_idx], SANITIZE_LIST[arena_idx])
                            out_f.write(normalized)
                            count += 1
                        except (ValueError, IndexError):
                            # Skip invalid lines
                            pass
        print_status_line(f"{draw_progress_bar(100.0, width=15)} Successfully collected {count} instructions.", end='\n')
    except Exception as e:
        print(f"Error writing to library file {output_path}: {e}")

def run_harvest(target_dir, arena_idx=None, limit=10):
    """
    Collects the top performers from one or all arenas into a single folder.
    Renames them to include arena, rank, and win streak information.
    """
    if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
        print(f"{Colors.YELLOW}No battle log found. Run some battles first!{Colors.ENDC}")
        return

    results = get_leaderboard(arena_idx=arena_idx, limit=limit)
    if not results:
        print(f"{Colors.YELLOW}No leaderboard data available to harvest.{Colors.ENDC}")
        return

    os.makedirs(target_dir, exist_ok=True)
    count = 0

    # results is {arena_idx: [(warrior_id, streak), ...]}
    for a, top in results.items():
        for rank, (warrior_id, streak) in enumerate(top, 1):
            source = os.path.join(f"arena{a}", f"{warrior_id}.red")
            if os.path.exists(source):
                dest_name = f"arena{a}_rank{rank}_streak{streak}_id{warrior_id}.red"
                dest = os.path.join(target_dir, dest_name)
                shutil.copy2(source, dest)
                count += 1
            else:
                # Some warriors might have been deleted or renamed manually, or log is old
                pass

    if count > 0:
        print(f"{Colors.GREEN}Successfully harvested {count} warriors to '{target_dir}'.{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}Found leaderboard entries, but matching files were missing.{Colors.ENDC}")

def run_export(selector, output_path, arena_idx):
    """
    Exports a warrior with a standardized Redcode header and normalization.
    """
    path = _resolve_warrior_path(selector, arena_idx)
    if not os.path.exists(path):
        print(f"Error: Warrior '{selector}' not found.")
        return

    # Try to extract warrior ID and arena from leaderboard
    warrior_id = "unknown"
    streak = 0
    leaderboard = get_leaderboard(arena_idx=arena_idx)
    if arena_idx in leaderboard:
        for wid, s in leaderboard[arena_idx]:
            if _resolve_warrior_path(str(wid), arena_idx) == path:
                warrior_id = str(wid)
                streak = s
                break

    if warrior_id == "unknown":
        warrior_id = os.path.basename(path).replace(".red", "")

    # Normalize and read instructions
    instructions = []
    try:
        with open(path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith(';'):
                    continue
                try:
                    norm = normalize_instruction(line, CORESIZE_LIST[arena_idx], SANITIZE_LIST[arena_idx])
                    if not norm.endswith('\n'):
                        norm += '\n'
                    instructions.append(norm)
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"Error reading warrior: {e}")
        return

    # Determine output file path
    if not output_path:
        output_path = f"exported_{warrior_id}.red"
    elif os.path.isdir(output_path):
        output_path = os.path.join(output_path, f"{warrior_id}.red")

    # Header
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    header = [
        f";name {warrior_id}\n",
        f";author Python Core War Evolver\n",
        f";strategy Evolved in Arena {arena_idx}\n",
        f";strategy Coresize: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]}, Processes: {PROCESSES_LIST[arena_idx]}\n",
        f";strategy Max Warrior Length: {WARLEN_LIST[arena_idx]}, Max Distance: {WARDISTANCE_LIST[arena_idx]}\n",
        f";win-streak {streak}\n",
        f";exported {now}\n",
        ";\n"
    ]

    try:
        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w') as f:
            f.writelines(header)
            f.writelines(instructions)
        print(f"{Colors.GREEN}Successfully exported warrior to '{output_path}'{Colors.ENDC}")
    except Exception as e:
        print(f"Error writing export: {e}")

def run_seeding(targets, arena_idx=None):
    """
    Populates an arena (or all arenas) with warriors from a set of targets.
    Targets can be files, directories, or dynamic selectors (top, random).
    """
    arenas_to_seed = range(LAST_ARENA + 1) if arena_idx is None else [arena_idx]

    for a in arenas_to_seed:
        if a > LAST_ARENA:
            print(f"Error: Arena {a} does not exist.")
            continue

        # Aggregate all files to process for THIS arena
        files_to_process = []
        for target in targets:
            # Resolve selector per arena
            resolved = _resolve_warrior_path(target, a)
            if os.path.isdir(resolved):
                files = [os.path.join(resolved, f) for f in os.listdir(resolved) if f.endswith('.red')]
                files_to_process.extend(files)
            elif os.path.exists(resolved):
                files_to_process.append(resolved)
            else:
                print(f"Warning: Target '{target}' could not be resolved for Arena {a}. Skipping.")

        if not files_to_process:
            print(f"Error: No warriors found to seed Arena {a}.")
            continue

        arena_dir = f"arena{a}"
        os.makedirs(arena_dir, exist_ok=True)

        print(f"Seeding Arena {a} with {NUMWARRIORS} warriors using {len(files_to_process)} sources...")

        # target config
        target_len = WARLEN_LIST[a]
        coresize = CORESIZE_LIST[a]
        sanitize = SANITIZE_LIST[a]

        for i in range(1, NUMWARRIORS + 1):
            percent = ((i - 1) / NUMWARRIORS) * 100
            bar = draw_progress_bar(percent, width=15)
            print_status_line(f"{bar} Seeding warrior {i}/{NUMWARRIORS}")

            src = files_to_process[(i-1) % len(files_to_process)]
            dest = os.path.join(arena_dir, f"{i}.red")

            try:
                with open(src, 'r') as f_in:
                    lines = f_in.readlines()

                with open(dest, 'w') as f_out:
                    count = 0
                    for line in lines:
                        if count >= target_len:
                            break

                        stripped = line.strip()
                        if not stripped or stripped.startswith(';'):
                            continue

                        try:
                            normalized = normalize_instruction(line, coresize, sanitize)
                            f_out.write(normalized)
                            count += 1
                        except (ValueError, IndexError):
                            continue

                    # Padding
                    while count < target_len:
                        f_out.write("DAT.F $0,$0\n")
                        count += 1
            except Exception as e:
                print(f"\nError processing warrior {src} for Arena {a}: {e}")
                break
        print_status_line(f"{draw_progress_bar(100.0, width=15)} Seeding Arena {a} complete.", end='\n')

    print(f"{Colors.GREEN}Seeding process complete.{Colors.ENDC}")

def read_config(key, data_type='int', default=None):
    value = config['DEFAULT'].get(key, fallback=default)
    if not value:
        return default
    data_type_mapping = {
        'int': int,
        'int_list': lambda x: [int(i) for i in x.split(',')],
        'bool_list': lambda x: [s.strip().lower() == 'true' for s in x.split(',') if s.strip()],
        'string_list': lambda x: [i.strip() for i in x.split(',')],
        'bool': lambda x: config['DEFAULT'].getboolean(key, default),
        'float': float,
    }
    return data_type_mapping.get(data_type, lambda x: x.strip() or None)(value)

config = configparser.ConfigParser()
config.read('settings.ini')

LAST_ARENA = read_config('LAST_ARENA', data_type='int')
CORESIZE_LIST = read_config('CORESIZE_LIST', data_type='int_list')
SANITIZE_LIST = read_config('SANITIZE_LIST', data_type='int_list')
CYCLES_LIST = read_config('CYCLES_LIST', data_type='int_list')
PROCESSES_LIST = read_config('PROCESSES_LIST', data_type='int_list')
WARLEN_LIST = read_config('WARLEN_LIST', data_type='int_list')
WARDISTANCE_LIST = read_config('WARDISTANCE_LIST', data_type='int_list')
NUMWARRIORS = read_config('NUMWARRIORS', data_type='int')
ALREADYSEEDED = read_config('ALREADYSEEDED', data_type='bool')
CLOCK_TIME = read_config('CLOCK_TIME', data_type='float')
BATTLE_LOG_FILE = read_config('BATTLE_LOG_FILE', data_type='string')
FINAL_ERA_ONLY = read_config('FINAL_ERA_ONLY', data_type='bool')
NOTHING_LIST = read_config('NOTHING_LIST', data_type='int_list')
RANDOM_LIST = read_config('RANDOM_LIST', data_type='int_list')
NAB_LIST = read_config('NAB_LIST', data_type='int_list')
MINI_MUT_LIST = read_config('MINI_MUT_LIST', data_type='int_list')
MICRO_MUT_LIST = read_config('MICRO_MUT_LIST', data_type='int_list')
LIBRARY_LIST = read_config('LIBRARY_LIST', data_type='int_list')
MAGIC_NUMBER_LIST = read_config('MAGIC_NUMBER_LIST', data_type='int_list')
ARCHIVE_LIST = read_config('ARCHIVE_LIST', data_type='int_list')
UNARCHIVE_LIST = read_config('UNARCHIVE_LIST', data_type='int_list')
LIBRARY_PATH = read_config('LIBRARY_PATH', data_type='string')
CROSSOVERRATE_LIST = read_config('CROSSOVERRATE_LIST', data_type='int_list')
TRANSPOSITIONRATE_LIST = read_config('TRANSPOSITIONRATE_LIST', data_type='int_list')
BATTLEROUNDS_LIST = read_config('BATTLEROUNDS_LIST', data_type='int_list')
PREFER_WINNER_LIST = read_config('PREFER_WINNER_LIST', data_type='bool_list')
INSTR_SET = read_config('INSTR_SET', data_type='string_list')
INSTR_MODES = read_config('INSTR_MODES', data_type='string_list')
INSTR_MODIF = read_config('INSTR_MODIF', data_type='string_list')
VERBOSE = read_config('VERBOSE', data_type='bool', default=False)

def weighted_random_number(size, length):
    """
    Returns a random number for an instruction's A or B field.

    It biases the result: 75% of the time, it picks a small number (local to the warrior code),
    which is good for loops and self-modification. 25% of the time, it picks a large number
    to attack distant parts of the core memory.
    """
    if random.randint(1,4)==1:
        return random.randint(-size, size)
    else:
        return random.randint(-length, length)

def construct_marble_bag(era):
    """
    Constructs the probability bag for mutations based on the current era.
    Uses the global configuration lists to determine the count of each marble type.
    """
    return [Marble.DO_NOTHING]*NOTHING_LIST[era] + \
           [Marble.MAJOR_MUTATION]*RANDOM_LIST[era] + \
           [Marble.NAB_INSTRUCTION]*NAB_LIST[era] + \
           [Marble.MINOR_MUTATION]*MINI_MUT_LIST[era] + \
           [Marble.MICRO_MUTATION]*MICRO_MUT_LIST[era] + \
           [Marble.INSTRUCTION_LIBRARY]*LIBRARY_LIST[era] + \
           [Marble.MAGIC_NUMBER_MUTATION]*MAGIC_NUMBER_LIST[era]

def apply_mutation(templine, marble, arena_idx, magic_number):
    """
    Applies a specific mutation (marble) to an instruction string.
    """
    if marble == Marble.MAJOR_MUTATION:
        if VERBOSE:
            print("Major mutation")
        # Major Mutation: Replace the instruction with a completely random one to explore new possibilities.
        num1 = weighted_random_number(CORESIZE_LIST[arena_idx], WARLEN_LIST[arena_idx])
        num2 = weighted_random_number(CORESIZE_LIST[arena_idx], WARLEN_LIST[arena_idx])
        return random.choice(INSTR_SET) + "." + random.choice(INSTR_MODIF) + " " + \
               random.choice(INSTR_MODES) + str(num1) + "," + random.choice(INSTR_MODES) + str(num2) + "\n"

    elif marble == Marble.NAB_INSTRUCTION and (LAST_ARENA != 0):
        # Borrow an instruction from a warrior in a different arena to introduce new ideas.
        donor_arena = random.randint(0, LAST_ARENA)
        while (donor_arena == arena_idx):
            donor_arena = random.randint(0, LAST_ARENA)
        if VERBOSE:
            print(f"Nab instruction from arena {donor_arena}")
        donor_file = os.path.join(f"arena{donor_arena}", f"{random.randint(1, NUMWARRIORS)}.red")
        try:
            with open(donor_file, 'r') as f:
                return random.choice(f.readlines())
        except Exception:
            return templine

    elif marble == Marble.INSTRUCTION_LIBRARY and LIBRARY_PATH and os.path.exists(LIBRARY_PATH):
        if VERBOSE:
            print("Instruction library")
        try:
            with open(LIBRARY_PATH, 'r') as f:
                return random.choice(f.readlines())
        except Exception:
            return templine

    elif marble in [Marble.MINOR_MUTATION, Marble.MICRO_MUTATION, Marble.MAGIC_NUMBER_MUTATION]:
        splitline = re.split(r'[\s\.,]+', templine.strip())
        if len(splitline) < 4:
            return templine

        if marble == Marble.MINOR_MUTATION:
            if VERBOSE:
                print("Minor mutation")
            # Slightly change one part of the instruction (opcode, mode, or value) to fine-tune it.
            r = random.randint(1, 6)
            if r == 1:
                splitline[0] = random.choice(INSTR_SET)
            elif r == 2:
                splitline[1] = random.choice(INSTR_MODIF)
            elif r == 3:
                splitline[2] = random.choice(INSTR_MODES) + splitline[2][1:]
            elif r == 4:
                num1 = weighted_random_number(CORESIZE_LIST[arena_idx], WARLEN_LIST[arena_idx])
                splitline[2] = splitline[2][0:1] + str(num1)
            elif r == 5:
                splitline[3] = random.choice(INSTR_MODES) + splitline[3][1:]
            elif r == 6:
                num1 = weighted_random_number(CORESIZE_LIST[arena_idx], WARLEN_LIST[arena_idx])
                splitline[3] = splitline[3][0:1] + str(num1)
        elif marble == Marble.MICRO_MUTATION:
            if VERBOSE:
                print("Micro mutation")
            # Adjust a single address value by 1 to test very small changes.
            r = random.randint(1, 2)
            try:
                if r == 1:
                    num1 = int(splitline[2][1:])
                    num1 = num1 + 1 if random.randint(1, 2) == 1 else num1 - 1
                    splitline[2] = splitline[2][0:1] + str(num1)
                else:
                    num1 = int(splitline[3][1:])
                    num1 = num1 + 1 if random.randint(1, 2) == 1 else num1 - 1
                    splitline[3] = splitline[3][0:1] + str(num1)
            except (ValueError, IndexError):
                pass
        elif marble == Marble.MAGIC_NUMBER_MUTATION:
            if VERBOSE:
                print("Magic number mutation")
            r = random.randint(1, 2)
            if r == 1:
                splitline[2] = splitline[2][0:1] + str(magic_number)
            else:
                splitline[3] = splitline[3][0:1] + str(magic_number)
        return splitline[0] + "." + splitline[1] + " " + splitline[2] + "," + splitline[3] + "\n"

    return templine

def breed_warriors(winlines, ranlines, era, arena_idx, bag):
    """
    Creates a new warrior by combining and mutating two parents.
    Returns a list of normalized instructions.
    """
    # Use copies to avoid modifying parents
    winlines = list(winlines)
    ranlines = list(ranlines)

    # Transposition
    if random.randint(1, TRANSPOSITIONRATE_LIST[era]) == 1:
        if VERBOSE:
            print("Transposition")
        # Randomly swap instructions to discover new tactical sequences.
        for i in range(1, random.randint(1, int((WARLEN_LIST[arena_idx] + 1) / 2))):
            fromline = random.randint(0, WARLEN_LIST[arena_idx] - 1)
            toline = random.randint(0, WARLEN_LIST[arena_idx] - 1)
            if random.randint(1, 2) == 1:
                winlines[toline], winlines[fromline] = winlines[fromline], winlines[toline]
            else:
                ranlines[toline], ranlines[fromline] = ranlines[fromline], ranlines[toline]

    if PREFER_WINNER_LIST[era]:
        pickingfrom = 1  # if start picking from the winning warrior, more chance of winning genes passed on.
    else:
        pickingfrom = random.randint(1, 2)

    # The 'magic number' helps create a sequence of related memory offsets if the mutation below is chosen.
    magic_number = weighted_random_number(CORESIZE_LIST[arena_idx], WARLEN_LIST[arena_idx])
    offspring_lines = []

    for i in range(0, WARLEN_LIST[arena_idx]):
        # Combine instructions from both parents (crossover) to pass on winning traits.
        if random.randint(1, CROSSOVERRATE_LIST[era]) == 1:
            pickingfrom = 2 if pickingfrom == 1 else 1

        templine = winlines[i] if pickingfrom == 1 else ranlines[i]

        chosen_marble = random.choice(bag)
        templine = apply_mutation(templine, chosen_marble, arena_idx, magic_number)

        # Final normalization to ensure the instruction follows the arena's rules.
        templine = normalize_instruction(templine, CORESIZE_LIST[arena_idx], SANITIZE_LIST[arena_idx])
        offspring_lines.append(templine)
        magic_number -= 1

    return offspring_lines

#custom function, Python modulo doesn't work how we want with negative numbers
def coremod(x, y):
    """
    Calculates the remainder of division, keeping the sign of the number.

    Standard Python modulo always returns a result with the same sign as the divisor.
    In Core War, we often want -5 % 10 to be -5, not 5.
    """
    numsign = -1 if x < 0 else 1
    return (abs(x) % y) * numsign

def corenorm(x, y):
    """
    Normalizes an address to be the shortest distance in the core.

    In a circular memory, an address can be represented as a positive
    or negative offset. This function returns the value with the
    smallest absolute value (e.g., in a core of size 80, 70 becomes -10).
    """
    return -(y - x) if x > y // 2 else (y + x) if x <= -(y // 2) else x

def normalize_instruction(instruction, coresize, sanitize_limit):
    """
    Standardizes a Redcode instruction into a consistent format.
    Handles missing modifiers, missing addressing modes, and varied whitespace.
    """
    # Strip trailing comments and whitespace
    clean_instr = instruction.split(';')[0]
    # Centralized tolerant cleanup
    clean_instr = clean_instr.replace('START', '').strip()
    if not clean_instr:
        raise ValueError("Empty instruction")

    # This robust version handles operand-less instructions (e.g. DAT or END).
    match = RE_INSTRUCTION.match(clean_instr)
    if not match:
        raise ValueError(f"Invalid instruction format: {clean_instr}")

    opcode, modifier, op_a, op_b = match.groups()
    opcode = opcode.upper()
    modifier = modifier.upper() if modifier else "I"

    def parse_op(op):
        if not op:
            return "$", 0
        op = op.strip()
        # Check for mode prefix
        if op[0] in '#$@<>{}*':
            mode = op[0]
            val_part = op[1:]
        else:
            mode = "$"
            val_part = op

        if not val_part: # Handle cases like "$" or "#" without a number
            return mode, 0

        return mode, int(val_part)

    mode_a, val_a = parse_op(op_a)
    mode_b, val_b = parse_op(op_b)

    norm_a = corenorm(coremod(val_a, sanitize_limit), coresize)
    norm_b = corenorm(coremod(val_b, sanitize_limit), coresize)

    return f"{opcode}.{modifier} {mode_a}{norm_a},{mode_b}{norm_b}\n"

def parse_nmars_output(raw_output):
    """
    Reads the text output from nMars to extract scores and warrior IDs.
    It handles standard output formats where scores are listed after the battle.
    """
    if raw_output is None:
        return [], []
    scores = []
    warriors = []
    # note nMars will sort by score regardless of the order in the command-line,
    # so we must match up the score with the warrior ID from each line.
    output = raw_output.splitlines()
    for line in output:
        if "scores" in line:
            if VERBOSE:
                print(line.strip())
            parts = line.split()
            try:
                # Robustly find 'scores' and extract the preceding ID and succeeding score.
                # Format: [ID] [Name...] scores [Score]
                idx = parts.index('scores')
                if idx > 0 and idx + 1 < len(parts):
                    scores.append(int(parts[idx + 1]))
                    warriors.append(int(parts[0]))
            except (ValueError, IndexError):
                continue
    return scores, warriors

def determine_winner(scores, warriors):
    """
    Decides the winner based on battle scores.

    In the event of a tie (draw), a winner is chosen randomly.
    Intent: This forces turnover in the population, preventing stagnant pools of
    identical warriors that just tie with each other endlessly.
    """
    if scores[1] == scores[0]:
        if VERBOSE:
            print("draw")
        if random.randint(1, 2) == 1:
            return warriors[1], warriors[0]
        return warriors[0], warriors[1]

    if scores[1] > scores[0]:
        return warriors[1], warriors[0]
    return warriors[0], warriors[1]

def get_recent_log_entries(n=5, arena_idx=None):
    """
    Retrieves and parses the last n entries from the battle log file.
    Optionally filters by arena index.
    """
    if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
        return []
    try:
        with open(BATTLE_LOG_FILE, 'r') as f:
            # If filtering by arena, scan a deeper buffer to ensure we find matches
            scan_depth = n * 20 if arena_idx is not None else n
            lines = deque(f, maxlen=scan_depth)
            results = []
            for line in lines:
                line = line.strip()
                if not line or "winner,loser" in line:
                    continue
                # Manually parse the CSV line
                # era,arena,winner,loser,score1,score2,bred_with
                parts = line.split(',')
                if len(parts) >= 6:
                    try:
                        this_arena = int(parts[1])
                        if arena_idx is not None and this_arena != arena_idx:
                            continue
                    except ValueError:
                        continue

                    results.append({
                        'era': parts[0],
                        'arena': parts[1],
                        'winner': parts[2],
                        'loser': parts[3],
                        'score1': parts[4],
                        'score2': parts[5]
                    })
            return results[-n:] if n > 0 else results
    except Exception:
        return []

def get_evolution_status(arena_idx=None):
    """
    Gathers the current status of the evolution system into a dictionary.
    Optionally filters the arena and log list by arena index.
    """
    champions = get_leaderboard(limit=1)

    # Count total battles from log
    total_battles = 0
    if BATTLE_LOG_FILE and os.path.exists(BATTLE_LOG_FILE):
        try:
            with open(BATTLE_LOG_FILE, 'r') as f:
                total_battles = max(0, sum(1 for _ in f) - 1) # Subtract header
        except Exception:
            pass

    latest_entries = get_recent_log_entries(n=1)
    status = {
        "latest_log": latest_entries[0] if latest_entries else None,
        "recent_log": get_recent_log_entries(5, arena_idx=arena_idx),
        "total_battles": total_battles,
        "arenas": [],
        "archive": None
    }

    arenas_to_scan = [arena_idx] if arena_idx is not None else range(LAST_ARENA + 1)
    for i in arenas_to_scan:
        arena_info = {
            "id": i,
            "config": {
                "size": CORESIZE_LIST[i],
                "cycles": CYCLES_LIST[i],
                "processes": PROCESSES_LIST[i]
            },
            "directory": f"arena{i}",
            "exists": False,
            "population": 0,
            "avg_length": 0.0
        }

        dir_name = f"arena{i}"
        if os.path.exists(dir_name):
            arena_info["exists"] = True
            files = [f for f in os.listdir(dir_name) if f.endswith('.red')]
            count = len(files)
            arena_info["population"] = count

            # Add champion info and strategy if available
            if i in champions and champions[i]:
                champ_id = champions[i][0][0]
                arena_info["champion"] = champ_id
                arena_info["champion_wins"] = champions[i][0][1]

                # Identify champion strategy
                champ_path = os.path.join(dir_name, f"{champ_id}.red")
                champ_stats = analyze_warrior(champ_path)
                arena_info["champion_strategy"] = identify_strategy(champ_stats)
            else:
                arena_info["champion"] = None
                arena_info["champion_wins"] = 0
                arena_info["champion_strategy"] = "-"

            if count > 0:
                total_lines = 0
                sample_files = files[:50]
                for f in sample_files:
                    try:
                        with open(os.path.join(dir_name, f), 'r') as fh:
                            total_lines += sum(1 for line in fh if line.strip())
                    except:
                        pass
                arena_info["avg_length"] = total_lines / len(sample_files)

        status["arenas"].append(arena_info)

    if os.path.exists("archive"):
        afiles = [f for f in os.listdir("archive") if f.endswith('.red')]
        status["archive"] = {"exists": True, "count": len(afiles)}
    else:
        status["archive"] = {"exists": False, "count": 0}

    return status

def get_leaderboard(arena_idx=None, limit=10):
    """
    Parses the battle log to find the top performing warriors.
    Tracks consecutive wins for each warrior ID, resetting when they lose.
    """
    if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
        return {}

    # arena -> warrior_id -> wins_since_last_loss
    stats = {}

    try:
        with open(BATTLE_LOG_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    a = int(row['arena'])
                    if arena_idx is not None and a != arena_idx:
                        continue

                    if a not in stats:
                        stats[a] = {}

                    winner = row['winner']
                    loser = row['loser']

                    # Increment winner
                    stats[a][winner] = stats[a].get(winner, 0) + 1
                    # Reset loser
                    stats[a][loser] = 0
                except (ValueError, KeyError):
                    continue

        # Sort and filter
        results = {}
        for a in sorted(stats.keys()):
            # filter out those with 0 wins (they just lost or never won)
            ranked = [(w, c) for w, c in stats[a].items() if c > 0]
            ranked.sort(key=lambda x: x[1], reverse=True)
            if ranked:
                results[a] = ranked[:limit]

        return results
    except Exception as e:
        sys.stderr.write(f"Error generating leaderboard: {e}\n")
        return {}

def analyze_warrior(filepath):
    """
    Parses a warrior file and extracts statistical information.
    """
    stats = {
        'instructions': 0,
        'opcodes': {},
        'modifiers': {},
        'modes': {},
        'unique_instructions': set(),
        'file': filepath
    }

    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Strip comments and whitespace
                line = line.split(';')[0].strip()
                if not line:
                    continue

                stats['instructions'] += 1
                stats['unique_instructions'].add(line.upper())

                # Regex to extract components robustly
                match = RE_INSTRUCTION.match(line)
                if match:
                    opcode, modifier, operand_a, operand_b = match.groups()
                    opcode = opcode.upper()
                    stats['opcodes'][opcode] = stats['opcodes'].get(opcode, 0) + 1

                    if modifier:
                        modifier = modifier.upper()
                        stats['modifiers'][modifier] = stats['modifiers'].get(modifier, 0) + 1

                    for op in [operand_a, operand_b]:
                        if op:
                            mode = op.strip()[0]
                            if mode in '#$@<>{}*': # Standard Redcode modes
                                stats['modes'][mode] = stats['modes'].get(mode, 0) + 1
                            else:
                                stats['modes']['$'] = stats['modes'].get('$', 0) + 1
                else:
                    # Fallback for simple lines
                    parts = re.split(r'[ \t\.]', line)
                    if parts:
                        opcode = parts[0].upper()
                        stats['opcodes'][opcode] = stats['opcodes'].get(opcode, 0) + 1
    except Exception as e:
        sys.stderr.write(f"Error analyzing {filepath}: {e}\n")
        return None

    stats['vocabulary_size'] = len(stats['unique_instructions'])
    del stats['unique_instructions']
    return stats

def identify_strategy(stats):
    """
    Identifies a warrior's strategy type based on its opcode distribution.
    """
    if not stats or stats.get('instructions', 0) == 0:
        return "Unknown"

    opcodes = stats['opcodes']
    total = stats['instructions']

    mov_pct = (opcodes.get('MOV', 0) / total) * 100
    spl_pct = (opcodes.get('SPL', 0) / total) * 100
    djn_pct = (opcodes.get('DJN', 0) / total) * 100
    add_pct = (opcodes.get('ADD', 0) / total) * 100
    jmp_pct = (opcodes.get('JMP', 0) / total) * 100
    dat_pct = (opcodes.get('DAT', 0) / total) * 100

    if spl_pct > 20 and mov_pct > 30:
        return "Paper (Replicator)"
    elif djn_pct > 10 and mov_pct > 30:
        return "Stone (Bomb-thrower)"
    elif add_pct > 20 and mov_pct > 40:
        return "Imp (Pulse)"
    elif jmp_pct > 15 and (mov_pct > 20 or add_pct > 20):
        return "Vampire / Pittrap"
    elif mov_pct > 70:
        return "Mover / Runner"
    elif dat_pct > 50:
        return "Wait / Shield"

    return "Experimental"

def analyze_files(files, label):
    """
    Aggregates statistics for a list of warrior files.
    """
    if not files:
        return None

    stats = {
        'count': len(files),
        'total_instructions': 0,
        'opcodes': {},
        'modifiers': {},
        'modes': {},
        'total_vocabulary': 0,
        'directory': label
    }

    for f in files:
        s = analyze_warrior(f)
        if s:
            stats['total_instructions'] += s['instructions']
            stats['total_vocabulary'] += s['vocabulary_size']
            for k, v in s['opcodes'].items():
                stats['opcodes'][k] = stats['opcodes'].get(k, 0) + v
            for k, v in s['modifiers'].items():
                stats['modifiers'][k] = stats['modifiers'].get(k, 0) + v
            for k, v in s['modes'].items():
                stats['modes'][k] = stats['modes'].get(k, 0) + v

    return stats

def analyze_population(directory):
    """
    Aggregates statistics for all warriors in a folder.
    """
    if not os.path.exists(directory):
        return None

    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.red')]
    return analyze_files(files, directory)

def run_comparison(target1, target2, arena_idx, json_output=False):
    """
    Provides a side-by-side statistical comparison between two targets.
    Targets can be files, directories, or dynamic selectors.
    """
    path1 = _resolve_warrior_path(target1, arena_idx)
    path2 = _resolve_warrior_path(target2, arena_idx)

    if os.path.isdir(path1):
        stats1 = analyze_population(path1)
    else:
        stats1 = analyze_warrior(path1)

    if os.path.isdir(path2):
        stats2 = analyze_population(path2)
    else:
        stats2 = analyze_warrior(path2)

    if not stats1 or not stats2:
        print(f"{Colors.RED}Could not analyze one or both targets.{Colors.ENDC}")
        return

    if json_output:
        print(json.dumps([stats1, stats2], indent=2))
    else:
        print_comparison(stats1, stats2)

def run_diff(target1, target2, arena_idx):
    """
    Performs a line-by-line code comparison between two warriors or selectors.
    """
    path1 = _resolve_warrior_path(target1, arena_idx)
    path2 = _resolve_warrior_path(target2, arena_idx)

    if not os.path.exists(path1):
        print(f"{Colors.RED}Error: Target A '{target1}' not found at {path1}{Colors.ENDC}")
        return
    if not os.path.exists(path2):
        print(f"{Colors.RED}Error: Target B '{target2}' not found at {path2}{Colors.ENDC}")
        return

    try:
        with open(path1, 'r') as f1, open(path2, 'r') as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()

        diff = difflib.unified_diff(
            lines1, lines2,
            fromfile=os.path.basename(path1),
            tofile=os.path.basename(path2)
        )

        has_diff = False
        print(f"\n{Colors.BOLD}{Colors.HEADER}--- Code Diff: {os.path.basename(path1)} vs {os.path.basename(path2)} ---{Colors.ENDC}")

        for line in diff:
            has_diff = True
            line = line.rstrip()
            if line.startswith('+') and not line.startswith('+++'):
                print(f"{Colors.GREEN}{line}{Colors.ENDC}")
            elif line.startswith('-') and not line.startswith('---'):
                print(f"{Colors.RED}{line}{Colors.ENDC}")
            elif line.startswith('@@'):
                print(f"{Colors.CYAN}{line}{Colors.ENDC}")
            else:
                print(line)

        if not has_diff:
            print(f"{Colors.YELLOW}Warriors are identical.{Colors.ENDC}")
        print("")

    except Exception as e:
        print(f"{Colors.RED}Error performing diff: {e}{Colors.ENDC}")

def run_trend_analysis(arena_idx):
    """
    Compares the distribution of instructions in the entire arena population
    vs the top-performing warriors (the Meta).
    """
    arena_dir = f"arena{arena_idx}"
    if not os.path.exists(arena_dir):
        print(f"{Colors.RED}Arena folder {arena_dir} not found.{Colors.ENDC}")
        return

    # 1. Analyze Population
    pop_stats = analyze_population(arena_dir)
    if not pop_stats:
        print(f"{Colors.YELLOW}No warriors found in {arena_dir} to analyze.{Colors.ENDC}")
        return

    # 2. Get Top Performers
    results = get_leaderboard(arena_idx=arena_idx, limit=10)
    meta_warriors = []
    if arena_idx in results:
        for warrior_id, streak in results[arena_idx]:
            path = os.path.join(arena_dir, f"{warrior_id}.red")
            if os.path.exists(path):
                meta_warriors.append(path)

    if not meta_warriors:
        print(f"{Colors.YELLOW}No leaderboard data found for Arena {arena_idx}. Run more battles!{Colors.ENDC}")
        return

    # 3. Analyze Meta
    meta_stats = analyze_files(meta_warriors, f"Meta (Top {len(meta_warriors)})")

    # 4. Print Trends
    print_comparison(pop_stats, meta_stats, title=f"Trend Analysis: Arena {arena_idx}")

def run_meta_analysis(target, arena_idx, json_output=False):
    """
    Analyzes the distribution of strategies in a target (folder, arena, or selector).
    If an arena is targeted, it compares the whole population vs the leaderboard.
    """
    path = _resolve_warrior_path(target, arena_idx)

    # 1. Gather Strategy Distribution for the Target
    files_to_scan = []

    if os.path.isdir(path):
        files_to_scan = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.red')]
        label = f"Folder: {os.path.basename(os.path.normpath(path))}"
    elif os.path.exists(path):
        files_to_scan = [path]
        label = f"Target: {target}"
    else:
        print(f"{Colors.RED}Error: Target '{target}' not found.{Colors.ENDC}")
        return

    def get_distribution(files):
        dist = {}
        for f in files:
            s = analyze_warrior(f)
            strat = identify_strategy(s)
            dist[strat] = dist.get(strat, 0) + 1
        return dist

    target_dist = get_distribution(files_to_scan)

    # 2. If it's an arena, get the Meta (Leaderboard) for comparison
    meta_dist = None
    # Check if target represents an arena population
    is_arena = "arena" in target.lower() or target == "" or target is None
    if is_arena:
        results = get_leaderboard(arena_idx=arena_idx, limit=10)
        if arena_idx in results:
            meta_files = []
            for wid, streak in results[arena_idx]:
                p = os.path.join(f"arena{arena_idx}", f"{wid}.red")
                if os.path.exists(p):
                    meta_files.append(p)
            if meta_files:
                meta_dist = get_distribution(meta_files)
                if not label or label == "Target: " or label.startswith("Folder: "):
                    label = f"Arena {arena_idx}"

    # 3. Output
    if json_output:
        res = {"target": target_dist}
        if meta_dist: res["meta"] = meta_dist
        print(json.dumps(res, indent=2))
        return

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Strategy Meta-Analysis: {label} ---{Colors.ENDC}")

    # Combined set of strategies
    all_strats = sorted(set(target_dist.keys()) | set(meta_dist.keys() if meta_dist else []))

    header = f"  {'Strategy':<20} | {'Target %':>10}"
    if meta_dist:
        header += f" | {'Meta %':>10} | {'Delta':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    target_total = sum(target_dist.values())
    meta_total = sum(meta_dist.values()) if meta_dist else 0

    for strat in all_strats:
        t_count = target_dist.get(strat, 0)
        t_pct = (t_count / target_total * 100) if target_total > 0 else 0

        line = f"  {strat:<20} | {t_pct:>9.1f}%"

        if meta_dist:
            m_count = meta_dist.get(strat, 0)
            m_pct = (m_count / meta_total * 100) if meta_total > 0 else 0
            delta = m_pct - t_pct

            delta_val_str = f"{delta:+.1f}%"
            if delta > 10:
                delta_str = f"{Colors.GREEN}{delta_val_str:>8}{Colors.ENDC}"
            elif delta < -10:
                delta_str = f"{Colors.RED}{delta_val_str:>8}{Colors.ENDC}"
            else:
                delta_str = f"{delta_val_str:>8}"

            line += f" | {m_pct:>9.1f}% | {delta_str}"

        print(line)
    print("")

def get_population_diversity(arena_idx):
    """
    Calculates the percentage of unique warrior strategies in an arena.
    """
    arena_dir = f"arena{arena_idx}"
    if not os.path.exists(arena_dir):
        return 0.0

    files = [f for f in os.listdir(arena_dir) if f.endswith('.red')]
    if not files:
        return 0.0

    unique_hashes = set()
    processed_count = 0
    for f in files:
        try:
            with open(os.path.join(arena_dir, f), 'r') as fh:
                # Strip comments and normalize whitespace to focus on the logic
                logical_lines = []
                for line in fh:
                    # Strip trailing comments
                    clean = line.split(';')[0].strip()
                    if clean:
                        # Normalize internal whitespace
                        normalized = " ".join(clean.split())
                        logical_lines.append(normalized)

                content = "".join(logical_lines)
                strategy_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                unique_hashes.add(strategy_hash)
                processed_count += 1
        except Exception:
            continue

    if processed_count == 0:
        return 0.0

    return (len(unique_hashes) / processed_count) * 100

def get_lifetime_rankings(arena_idx=None, limit=10, min_battles=5):
    """
    Parses the battle log to find the top performing warriors by win rate.
    """
    if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
        return {}

    # arena -> warrior_id -> {wins, battles}
    stats = {}

    try:
        with open(BATTLE_LOG_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    a = int(row['arena'])
                    if arena_idx is not None and a != arena_idx:
                        continue

                    if a not in stats:
                        stats[a] = {}

                    winner = row['winner']
                    loser = row['loser']

                    if winner not in stats[a]:
                        stats[a][winner] = {'wins': 0, 'battles': 0}
                    if loser not in stats[a]:
                        stats[a][loser] = {'wins': 0, 'battles': 0}

                    stats[a][winner]['wins'] += 1
                    stats[a][winner]['battles'] += 1
                    stats[a][loser]['battles'] += 1
                except (ValueError, KeyError):
                    continue

        # Calculate win rates and sort
        results = {}
        for a in sorted(stats.keys()):
            ranked = []
            for warrior_id, data in stats[a].items():
                if data['battles'] >= min_battles:
                    win_rate = (data['wins'] / data['battles']) * 100
                    ranked.append((warrior_id, win_rate, data['wins'], data['battles']))

            # Sort by win rate, then total wins as tiebreaker
            ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
            if ranked:
                results[a] = ranked[:limit]

        return results
    except Exception as e:
        sys.stderr.write(f"Error generating lifetime rankings: {e}\n")
        return {}

def run_report(arena_idx):
    """
    Generates and displays a comprehensive health and performance report for an arena.
    """
    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Arena {arena_idx} Health & Performance Report ---{Colors.ENDC}")

    # 1. Arena Config
    print(f"\n{Colors.BOLD}Arena Configuration:{Colors.ENDC}")
    print(f"  Coresize:  {CORESIZE_LIST[arena_idx]}")
    print(f"  Cycles:    {CYCLES_LIST[arena_idx]}")
    print(f"  Processes: {PROCESSES_LIST[arena_idx]}")
    print(f"  Length:    {WARLEN_LIST[arena_idx]}")

    # 2. Population & Diversity
    diversity = get_population_diversity(arena_idx)
    status_data = get_evolution_status()
    arena_data = next((a for a in status_data['arenas'] if a['id'] == arena_idx), None)

    print(f"\n{Colors.BOLD}Population & Diversity:{Colors.ENDC}")
    if arena_data:
        print(f"  Total Population: {arena_data['population']} warriors")
        print(f"  Avg Code Length:  {arena_data['avg_length']:.1f} instructions")

    div_color = Colors.GREEN if diversity > 50 else Colors.YELLOW if diversity > 10 else Colors.RED
    print(f"  Diversity Index:  {div_color}{diversity:.1f}%{Colors.ENDC} unique strategies")

    # 3. Current Champion (Streak)
    print(f"\n{Colors.BOLD}Current Top Performers (Recent Streak):{Colors.ENDC}")
    streaks = get_leaderboard(arena_idx=arena_idx, limit=5)
    if arena_idx in streaks:
        for i, (wid, streak) in enumerate(streaks[arena_idx], 1):
            path = _resolve_warrior_path(str(wid), arena_idx)
            strat = identify_strategy(analyze_warrior(path))
            print(f"  {i}. Warrior {wid:3} ({Colors.CYAN}{strat}{Colors.ENDC}): {Colors.GREEN}{streak} consecutive wins{Colors.ENDC}")
    else:
        print("  No streak data available.")

    # 4. Lifetime Rankings
    print(f"\n{Colors.BOLD}Lifetime Rankings (Win Rate):{Colors.ENDC}")
    rankings = get_lifetime_rankings(arena_idx=arena_idx, limit=5)
    if arena_idx in rankings:
        print(f"  {'Rank':<4} | {'Warrior':<7} | {'Strategy':<20} | {'Win Rate':>8} | {'Wins':>5} | {'Battles':>8}")
        print("  " + "-" * 73)
        for i, (wid, rate, wins, battles) in enumerate(rankings[arena_idx], 1):
            path = _resolve_warrior_path(str(wid), arena_idx)
            strat = identify_strategy(analyze_warrior(path))
            print(f"  {i:<4} | {wid:7} | {strat:<20} | {rate:>7.1f}% | {wins:5} | {battles:8}")
    else:
        print("  No lifetime ranking data available (requires min. 5 battles per warrior).")

    print(f"\n{Colors.BOLD}System Summary:{Colors.ENDC}")
    print(f"  Total Battles: {status_data['total_battles']:,}")
    print(f"  Archive Size:  {status_data['archive']['count']} warriors")
    print("")

def run_inspection(target, arena_idx):
    """
    Provides a comprehensive profile of a warrior, combining metadata,
    performance statistics, and code analysis.
    """
    path = _resolve_warrior_path(target, arena_idx)
    if not os.path.exists(path):
        print(f"{Colors.RED}Error: Warrior '{target}' not found.{Colors.ENDC}")
        return

    # 1. Basic Analysis
    stats = analyze_warrior(path)
    if not stats:
        print(f"{Colors.RED}Error: Could not analyze warrior.{Colors.ENDC}")
        return

    # 2. Performance Data (Log Parsing)
    leaderboard = get_leaderboard(arena_idx=arena_idx)
    streak = 0
    if arena_idx in leaderboard:
        for wid, s in leaderboard[arena_idx]:
            # Use realpath for robust comparison
            if os.path.realpath(_resolve_warrior_path(str(wid), arena_idx)) == os.path.realpath(path):
                streak = s
                break

    # Get lifetime rankings (set min_battles=0 to capture any data)
    rankings = get_lifetime_rankings(arena_idx=arena_idx, limit=NUMWARRIORS, min_battles=0)
    win_rate = 0.0
    total_battles = 0
    wins = 0
    # Extract filename as ID for matching
    warrior_id = os.path.basename(path).replace(".red", "")
    if arena_idx in rankings:
        for wid, rate, w, b in rankings[arena_idx]:
            if str(wid) == warrior_id:
                win_rate = rate
                total_battles = b
                wins = w
                break

    # 3. Strategy Identification
    opcodes = stats['opcodes']
    total = stats['instructions']
    strategy = identify_strategy(stats)

    # 4. Display Results
    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Warrior Profile: {os.path.basename(path)} ---{Colors.ENDC}")

    print(f"\n{Colors.BOLD}General Information:{Colors.ENDC}")
    print(f"  Path:      {path}")
    print(f"  Arena:     {arena_idx} (Size: {CORESIZE_LIST[arena_idx]})")
    print(f"  Strategy:  {Colors.CYAN}{strategy}{Colors.ENDC}")

    print(f"\n{Colors.BOLD}Performance Statistics:{Colors.ENDC}")
    streak_color = Colors.GREEN if streak > 10 else Colors.ENDC
    print(f"  Current Win Streak: {streak_color}{streak}{Colors.ENDC}")
    print(f"  Lifetime Win Rate:  {win_rate:.1f}%")
    print(f"  Total Battles:      {total_battles} ({wins} wins)")

    print(f"\n{Colors.BOLD}Code Characteristics:{Colors.ENDC}")
    print(f"  Instruction Count: {stats['instructions']}")
    print(f"  Vocabulary Size:   {stats['vocabulary_size']} unique instructions")

    # Top 3 Opcodes
    if total > 0:
        sorted_ops = sorted(opcodes.items(), key=lambda x: x[1], reverse=True)[:3]
        op_str = ", ".join([f"{k} ({v/total*100:.0f}%)" for k, v in sorted_ops])
        print(f"  Primary Opcodes:   {op_str}")

    print(f"\n{Colors.BOLD}Source Code Preview:{Colors.ENDC}")
    print("-" * 30)
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
            # Show first 10 non-comment lines
            count = 0
            for line in lines:
                if line.strip() and not line.strip().startswith(';'):
                    print(f"  {line.strip()}")
                    count += 1
                if count >= 10:
                    break
            if len(lines) > count + 5: # Small buffer before showing ellipsis
                print(f"  ...")
    except Exception as e:
        print(f"  {Colors.RED}Error reading file: {e}{Colors.ENDC}")
    print("-" * 30 + "\n")

def get_lineage(warrior_id, arena_idx, max_depth=3, _current_depth=0, _log_cache=None, _start_idx=0):
    """
    Parses the battle log backwards to find the parentage of a warrior.
    """
    if _current_depth >= max_depth:
        return None

    if _log_cache is None:
        if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
            return None
        try:
            with open(BATTLE_LOG_FILE, 'r') as f:
                # Read all lines and reverse to search backwards
                _log_cache = list(csv.DictReader(f))
                _log_cache.reverse()
        except Exception:
            return None

    # Find the most recent birth of this warrior (when it was a loser)
    # We search backwards from the beginning of the list (which is the end of the log)
    birth_record = None
    next_start_idx = _start_idx
    for i in range(_start_idx, len(_log_cache)):
        row = _log_cache[i]
        try:
            if int(row['arena']) == arena_idx and row['loser'] == str(warrior_id):
                birth_record = row
                # We need to continue searching for parents from entries BEFORE this one
                # in chronological order, which means AFTER this one in our reversed list.
                next_start_idx = i + 1
                break
        except (ValueError, KeyError):
            continue

    if birth_record:
        parent1 = birth_record['winner']
        parent2 = birth_record['bred_with']
        era = int(birth_record['era']) + 1

        return {
            'warrior': warrior_id,
            'era': era,
            'parents': [
                get_lineage(parent1, arena_idx, max_depth, _current_depth + 1, _log_cache, next_start_idx),
                get_lineage(parent2, arena_idx, max_depth, _current_depth + 1, _log_cache, next_start_idx)
            ]
        }

    return {'warrior': warrior_id, 'initial': True}

def run_lineage(target, arena_idx, depth=3):
    """
    Displays the genealogy tree of a warrior.
    """
    path = _resolve_warrior_path(target, arena_idx)
    warrior_id = os.path.basename(path).replace(".red", "")

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Lineage Tracer: Warrior {warrior_id} (Arena {arena_idx}) ---{Colors.ENDC}")

    lineage = get_lineage(warrior_id, arena_idx, max_depth=depth)

    if not lineage:
        print(f"{Colors.YELLOW}No lineage data found in logs.{Colors.ENDC}")
        return

    def print_tree(node, prefix="", is_last=True, label=""):
        if not node:
            return

        connector = "└── " if is_last else "├── "

        info = f"Warrior {node['warrior']}"
        if node.get('initial'):
            info += f" {Colors.CYAN}(Initial Population / Unarchived){Colors.ENDC}"
        else:
            info += f" {Colors.GREEN}(Born in Era {node['era']}){Colors.ENDC}"

        print(f"{prefix}{label}{connector}{info}")

        if node.get('parents'):
            new_prefix = prefix + ("    " if is_last else "│   ")
            parents = node['parents']
            print_tree(parents[0], new_prefix, False, "P1: ")
            print_tree(parents[1], new_prefix, True, "P2: ")

    print_tree(lineage, is_last=True)
    print("")

def print_comparison(stats1, stats2, title="Comparison"):
    """
    Prints a side-by-side comparison of statistics for two targets.
    """
    label1 = stats1.get('directory', stats1.get('file', 'Target A'))
    if 'count' in stats1:
        label1 += f" ({stats1['count']} warriors)"

    label2 = stats2.get('directory', stats2.get('file', 'Target B'))
    if 'count' in stats2:
        label2 += f" ({stats2['count']} warriors)"

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- {title} ---{Colors.ENDC}")
    print(f"Target A: {label1}")
    print(f"Target B: {label2}")
    print("-" * 60)

    def print_section(trait_title, data1, data2, total1, total2):
        print(f"\n{Colors.BOLD}Trait: {trait_title}{Colors.ENDC}")
        header = f"  {'Value':<10} | {'A %':>8} | {'B %':>8} | {'Delta':>8}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        # Get all unique keys
        all_keys = sorted(set(data1.keys()) | set(data2.keys()))

        for key in all_keys:
            val1 = data1.get(key, 0)
            val2 = data2.get(key, 0)

            pct1 = (val1 / total1 * 100) if total1 > 0 else 0
            pct2 = (val2 / total2 * 100) if total2 > 0 else 0
            delta = pct2 - pct1

            delta_val_str = f"{delta:+.1f}%"
            if delta > 5:
                delta_str = f"{Colors.GREEN}{delta_val_str:>8}{Colors.ENDC}"
            elif delta < -5:
                delta_str = f"{Colors.RED}{delta_val_str:>8}{Colors.ENDC}"
            else:
                delta_str = f"{delta_val_str:>8}"

            print(f"  {key:<10} | {pct1:>7.1f}% | {pct2:>7.1f}% | {delta_str}")

    total_instr1 = stats1.get('total_instructions', stats1.get('instructions', 0))
    total_instr2 = stats2.get('total_instructions', stats2.get('instructions', 0))

    print_section("Opcodes", stats1['opcodes'], stats2['opcodes'],
                  total_instr1, total_instr2)

    total_mods1 = sum(stats1['modifiers'].values())
    total_mods2 = sum(stats2['modifiers'].values())
    if total_mods1 or total_mods2:
        print_section("Modifiers", stats1['modifiers'], stats2['modifiers'],
                      total_mods1, total_mods2)

    total_modes1 = sum(stats1['modes'].values())
    total_modes2 = sum(stats2['modes'].values())
    if total_modes1 or total_modes2:
        print_section("Addressing Modes", stats1['modes'], stats2['modes'],
                      total_modes1, total_modes2)
    print("")

def print_analysis(stats):
    """
    Prints the analysis results in a human-readable format.
    """
    if not stats:
        print(f"{Colors.RED}No data to analyze.{Colors.ENDC}")
        return

    is_pop = 'count' in stats
    target = stats['directory'] if is_pop else stats['file']

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Analysis Report: {target} ---{Colors.ENDC}")

    if is_pop:
        print(f"Warriors Analyzed: {stats['count']}")
        print(f"Avg Instructions:  {stats['total_instructions'] / stats['count']:.1f}")
        print(f"Avg Vocabulary:    {stats['total_vocabulary'] / stats['count']:.1f}")
        total_instr = stats['total_instructions']
        total_modes = sum(stats['modes'].values())
    else:
        print(f"Instructions:      {stats['instructions']}")
        print(f"Vocabulary Size:   {stats['vocabulary_size']}")
        total_instr = stats['instructions']
        total_modes = sum(stats['modes'].values())

    print(f"\n{Colors.BOLD}Opcode Distribution:{Colors.ENDC}")
    sorted_opcodes = sorted(stats['opcodes'].items(), key=lambda x: x[1], reverse=True)
    for op, count in sorted_opcodes:
        pct = (count / total_instr) * 100
        print(f"  {op:4}: {count:4} ({pct:5.1f}%) " + "#" * int(pct/2))

    if stats['modifiers']:
        print(f"\n{Colors.BOLD}Modifier Distribution:{Colors.ENDC}")
        total_mods = sum(stats['modifiers'].values())
        sorted_mods = sorted(stats['modifiers'].items(), key=lambda x: x[1], reverse=True)
        for mod, count in sorted_mods:
            pct = (count / total_mods) * 100
            print(f"  .{mod:2}: {count:4} ({pct:5.1f}%)")

    if stats['modes']:
        print(f"\n{Colors.BOLD}Addressing Modes:{Colors.ENDC}")
        sorted_modes = sorted(stats['modes'].items(), key=lambda x: x[1], reverse=True)
        for mode, count in sorted_modes:
            pct = (count / total_modes) * 100
            print(f"  {mode:1} : {count:4} ({pct:5.1f}%)")

def print_status(data=None, recent_bps=None, arena_idx=None):
    """
    Prints the current status of all arenas and the archive in a human-readable format.
    If arena_idx is provided, it shows focused information for that specific arena.
    """
    if data is None:
        data = get_evolution_status(arena_idx=arena_idx)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cols, _ = shutil.get_terminal_size()

    # Use terminal width for separators
    sep_double = "=" * min(cols, 100)
    sep_single = "-" * min(cols, 100)

    title = "Evolver Status Dashboard"
    if arena_idx is not None:
        title += f" (Arena {arena_idx})"

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- {title} ---{Colors.ENDC}")
    print(f"Captured: {now}")
    print(sep_double)

    # Focused information for single arena
    if arena_idx is not None:
        diversity = get_population_diversity(arena_idx)
        div_color = Colors.GREEN if diversity > 50 else Colors.YELLOW if diversity > 10 else Colors.RED
        print(f"{Colors.BOLD}Strategy Diversity:{Colors.ENDC} {div_color}{diversity:.1f}%{Colors.ENDC} unique strategies")
        print(sep_single)

    # Latest Activity
    recent = data.get('recent_log', [])
    if recent:
        act_header = f"Recent Activity (Last {len(recent)} matches):"
        if arena_idx is not None:
            act_header = f"Recent Activity for Arena {arena_idx} (Last {len(recent)} matches):"
        print(f"{Colors.BOLD}{act_header}{Colors.ENDC}")
        for log in reversed(recent):
            try:
                summary = f"  - Era {int(log['era'])+1}, Arena {log['arena']}: {Colors.GREEN}Warrior {log['winner']}{Colors.ENDC} beat {Colors.RED}Warrior {log['loser']}{Colors.ENDC} ({log['score1']}-{log['score2']})"
                print(summary)
            except (ValueError, KeyError):
                print(f"  - {log}")
    else:
        print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} No battles recorded yet.")
    print(sep_single)

    # Two-tier Table Header
    group1_title = "      ARENA CONFIGURATION      "
    group2_title = "          POPULATION, PERFORMANCE & STRATEGY          "

    # Align the group divider with the column divider (index 30)
    header_groups = f"{Colors.BOLD}{group1_title:<30} | {group2_title}{Colors.ENDC}"
    print(header_groups)

    header_cols = f"{'Arena':<5} {'Size':>7} {'Cycles':>8} {'Procs':>6} | {'Pop':>5} {'Len':>5} {'Champ':>6} {'Wins':>4} {'Strategy':<20} {'Status':<8}"
    print(f"{Colors.BOLD}{header_cols}{Colors.ENDC}")
    print(sep_single)

    total_warriors = 0
    for arena in data['arenas']:
        i = arena['id']
        size = arena['config']['size']
        cycles = arena['config']['cycles']
        procs = arena['config']['processes']

        champ_str = "-"
        wins_str = "-"
        strat_str = "-"

        if arena['exists']:
            pop = str(arena['population'])
            total_warriors += arena['population']
            avg_len = f"{arena['avg_length']:.1f}"
            status = f"{Colors.GREEN}OK{Colors.ENDC}"

            if arena.get('champion'):
                champ_id = arena['champion']
                champ_str = f"#{champ_id}"
                wins_str = str(arena['champion_wins'])
                strat_str = arena.get('champion_strategy', '-')

                if arena['champion_wins'] > 0:
                    champ_str = f"{Colors.CYAN}{champ_str}{Colors.ENDC}"
                    wins_str = f"{Colors.BOLD}{Colors.GREEN}{wins_str}{Colors.ENDC}"
                    strat_str = f"{Colors.CYAN}{strat_str}{Colors.ENDC}"
        else:
            pop = "-"
            avg_len = "-"
            status = f"{Colors.YELLOW}Unseeded{Colors.ENDC}"

        champ_plain = strip_ansi(champ_str)
        wins_plain = strip_ansi(wins_str)
        strat_plain = strip_ansi(strat_str)

        row = (
            f"{i:<5} {size:>7} {cycles:>8} {procs:>6} | {pop:>5} {avg_len:>5} "
            f"{champ_str:>{6 + (len(champ_str) - len(champ_plain))}} "
            f"{wins_str:>{4 + (len(wins_str) - len(wins_plain))}} "
            f"{strat_str:<{20 + (len(strat_str) - len(strat_plain))}} "
            f"{status}"
        )
        print(row)

    print(sep_single)

    # Archive and Summary
    archive_count = data['archive']['count']
    archive_info = f"{Colors.GREEN}{archive_count}{Colors.ENDC}" if data['archive']['exists'] else f"{Colors.YELLOW}None{Colors.ENDC}"
    total_battles = f"{data['total_battles']:,}"

    summary_line = f"Total Battles: {Colors.BOLD}{total_battles}{Colors.ENDC} | Total Population: {Colors.BOLD}{total_warriors}{Colors.ENDC} | Archive: {archive_info}"
    if recent_bps is not None:
        summary_line += f" | Performance: {Colors.CYAN}{recent_bps:.1f} bps{Colors.ENDC}"
    print(summary_line)
    print(sep_double + "\n")

def _resolve_warrior_path(selector, arena_idx):
    """
    Resolves a warrior selector (filename, 'top', 'topN', or 'random') to a file path.
    Supports an @N suffix to override the default arena index (e.g., top@0, random@2).
    """
    # Check for arena override suffix (e.g., top@0)
    if "@" in selector:
        parts = selector.rsplit("@", 1)
        if parts[1].isdigit():
            selector = parts[0]
            arena_idx = int(parts[1])

    if os.path.exists(selector):
        return selector

    sel = selector.lower()

    # Random selector
    if sel == "random":
        arena_dir = f"arena{arena_idx}"
        if os.path.exists(arena_dir):
            files = [f for f in os.listdir(arena_dir) if f.endswith('.red')]
            if files:
                chosen = random.choice(files)
                return os.path.join(arena_dir, chosen)
        return selector

    # Top/Champion selector
    if sel.startswith("top"):
        try:
            # Extract N from topN, default to 1
            n = 1
            if len(sel) > 3:
                n = int(sel[3:])

            # Use get_leaderboard to find the ID
            results = get_leaderboard(arena_idx=arena_idx, limit=n)
            if arena_idx in results and len(results[arena_idx]) >= n:
                warrior_id, wins = results[arena_idx][n-1]
                path = os.path.join(f"arena{arena_idx}", f"{warrior_id}.red")
                if os.path.exists(path):
                    return path
        except (ValueError, IndexError):
            pass

    # If it's a number, try to resolve it as a warrior ID in the arena directory
    if selector.isdigit():
        path = os.path.join(f"arena{arena_idx}", f"{selector}.red")
        if os.path.exists(path):
            return path

    return selector

def _get_arena_idx(default=0):
    """
    Helper to extract arena index from command line arguments.
    """
    for flag in ["--arena", "-a"]:
        if flag in sys.argv:
            idx = sys.argv.index(flag)
            if len(sys.argv) > idx + 1:
                return int(sys.argv[idx + 1])
            return default

    # Smart Arena Inference: look for arenaN/ or arenaN\ or selector@N in any argument
    for arg in sys.argv[1:]:
        match = re.search(r'arena(\d+)[/\\]', arg)
        if match:
            return int(match.group(1))
        # Support @N suffix (e.g., top@5, random@2)
        match = re.search(r'@(\d+)$', arg)
        if match:
            return int(match.group(1))

    return default

def validate_configuration():
    """
    Checks if the project is ready to run.

    Verifies:
    1. Configuration lists (in settings.ini) match the number of arenas.
    2. Configuration lists have enough entries for all 3 eras.
    3. The nMars executable is installed and available.
    4. Required file paths exist.

    Returns True if everything looks good, False if there are critical errors.
    """
    errors = []
    warnings = []

    # Check Arena Lists
    expected_length = LAST_ARENA + 1
    arena_lists = {
        "CORESIZE_LIST": CORESIZE_LIST,
        "SANITIZE_LIST": SANITIZE_LIST,
        "CYCLES_LIST": CYCLES_LIST,
        "PROCESSES_LIST": PROCESSES_LIST,
        "WARLEN_LIST": WARLEN_LIST,
        "WARDISTANCE_LIST": WARDISTANCE_LIST
    }

    for name, lst in arena_lists.items():
        if len(lst) < expected_length:
            errors.append(f"The setting '{name}' in settings.ini is too short. It has {len(lst)} values, but needs at least {expected_length} (because LAST_ARENA is {LAST_ARENA}).")

    # Check Era Lists (Expect 3 eras: 0, 1, 2)
    era_lists = {
        "NOTHING_LIST": NOTHING_LIST,
        "RANDOM_LIST": RANDOM_LIST,
        "NAB_LIST": NAB_LIST,
        "MINI_MUT_LIST": MINI_MUT_LIST,
        "MICRO_MUT_LIST": MICRO_MUT_LIST,
        "LIBRARY_LIST": LIBRARY_LIST,
        "MAGIC_NUMBER_LIST": MAGIC_NUMBER_LIST,
        "ARCHIVE_LIST": ARCHIVE_LIST,
        "UNARCHIVE_LIST": UNARCHIVE_LIST,
        "CROSSOVERRATE_LIST": CROSSOVERRATE_LIST,
        "TRANSPOSITIONRATE_LIST": TRANSPOSITIONRATE_LIST,
        "BATTLEROUNDS_LIST": BATTLEROUNDS_LIST,
    }

    # PREFER_WINNER_LIST might be bool_list, handled differently? No, it's a list.
    era_lists["PREFER_WINNER_LIST"] = PREFER_WINNER_LIST

    for name, lst in era_lists.items():
        if len(lst) < 3:
            errors.append(f"The setting '{name}' in settings.ini must have at least 3 values (one for each evolution era).")

    # Check Executables
    nmars_cmd = _get_nmars_cmd()
    if not shutil.which(nmars_cmd) and not os.path.exists(nmars_cmd):
        errors.append(f"Executable '{nmars_cmd}' not found in PATH or current directory.")

    # Check Library
    if LIBRARY_PATH and not os.path.exists(LIBRARY_PATH):
        # Check if any era actually uses the library
        if any(x > 0 for x in LIBRARY_LIST):
            warnings.append(f"LIBRARY_PATH '{LIBRARY_PATH}' does not exist, but LIBRARY_LIST has non-zero values.")

    # Check Seeding
    if not ALREADYSEEDED:
        # Check if arenas already exist
        if any(os.path.exists(f"arena{i}") for i in range(LAST_ARENA + 1)):
            warnings.append("ALREADYSEEDED is False, but arena directories exist. They will be overwritten.")

    # Print results
    if warnings:
        print(f"{Colors.YELLOW}Warnings:{Colors.ENDC}")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print(f"{Colors.RED}Errors:{Colors.ENDC}")
        for e in errors:
            print(f"  - {e}")
        return False

    print(f"{Colors.GREEN}Configuration and environment are valid.{Colors.ENDC}")
    return True

if __name__ == "__main__":
  if "--help" in sys.argv or "-h" in sys.argv:
    help_text = __doc__
    # Section Headers
    help_text = re.sub(r'^([A-Z].*:)$', rf'{Colors.BOLD}{Colors.HEADER}\1{Colors.ENDC}', help_text, flags=re.MULTILINE)
    # Flags
    help_text = re.sub(r'(--[a-z-]+|-[a-z](?!\w))', rf'{Colors.CYAN}\1{Colors.ENDC}', help_text)
    # Examples
    help_text = re.sub(r'(python evolverstage\.py .*)', rf'{Colors.YELLOW}\1{Colors.ENDC}', help_text)
    # Keywords
    help_text = re.sub(r'\b(top|topN|random)\b', rf'{Colors.GREEN}\1{Colors.ENDC}', help_text)
    print(help_text)
    sys.exit(0)

  if "--restart" in sys.argv:
    ALREADYSEEDED = False
  elif "--resume" in sys.argv:
    ALREADYSEEDED = True

  if "--version" in sys.argv:
    print(f"Python Core War Evolver v{VERSION}")
    sys.exit(0)

  if "--check" in sys.argv or "-c" in sys.argv:
    if validate_configuration():
        sys.exit(0)
    else:
        sys.exit(1)

  if "--status" in sys.argv or "-s" in sys.argv:
    watch = "--watch" in sys.argv or "-w" in sys.argv
    arena_idx = _get_arena_idx(default=None)
    interval = 2.0
    if "--interval" in sys.argv:
        try:
            idx = sys.argv.index("--interval")
            if len(sys.argv) > idx + 1:
                interval = float(sys.argv[idx+1])
        except (ValueError, IndexError):
            pass

    if "--json" in sys.argv:
        if watch:
            try:
                while True:
                    print(json.dumps(get_evolution_status(arena_idx=arena_idx), indent=2))
                    time.sleep(interval)
            except KeyboardInterrupt:
                print("")
                sys.exit(0)
        else:
            print(json.dumps(get_evolution_status(arena_idx=arena_idx), indent=2))
    else:
        if watch:
            last_time = None
            last_battles = None
            try:
                while True:
                    # Clear terminal
                    print("\033[H\033[J", end="")

                    status_data = get_evolution_status(arena_idx=arena_idx)
                    current_time = time.time()
                    current_battles = status_data['total_battles']

                    recent_bps = None
                    if last_time is not None and last_battles is not None:
                        time_delta = current_time - last_time
                        battle_delta = current_battles - last_battles
                        if time_delta > 0:
                            recent_bps = battle_delta / time_delta

                    print_status(data=status_data, recent_bps=recent_bps, arena_idx=arena_idx)

                    last_time = current_time
                    last_battles = current_battles

                    time.sleep(interval)
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}Stopped monitoring.{Colors.ENDC}")
                sys.exit(0)
        else:
            print_status(arena_idx=arena_idx)
    sys.exit(0)

  if "--leaderboard" in sys.argv or "-l" in sys.argv:
    arena_idx = _get_arena_idx(default=None)

    # Determine limit (default 10)
    limit = 10
    if "--top" in sys.argv:
        try:
            t_idx = sys.argv.index("--top")
            if len(sys.argv) > t_idx + 1:
                limit = int(sys.argv[t_idx+1])
        except ValueError:
            pass

    results = get_leaderboard(arena_idx=arena_idx, limit=limit)

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"{Colors.YELLOW}No leaderboard data available.{Colors.ENDC}")
        else:
            # If no arena specified and multiple arenas have data, show a summary table
            if arena_idx is None and len(results) > 1:
                print(f"\n{Colors.BOLD}{Colors.HEADER}--- GLOBAL CHAMPIONS (Rank 1 from all arenas) ---{Colors.ENDC}")
                print("-" * 85)
                print(f"{'Arena':<6} {'Warrior':<12} {'Strategy':<20} {'Streak':>8}   {'Performance'}")
                print("-" * 85)

                # Find max streak for scaling the bars
                all_streaks = [top[0][1] for top in results.values() if top]
                max_streak = max(all_streaks) if all_streaks else 1

                for a in sorted(results.keys()):
                    if results[a]:
                        warrior_id, streak = results[a][0]
                        path = _resolve_warrior_path(str(warrior_id), a)
                        strat = identify_strategy(analyze_warrior(path))
                        strat_str = f"{Colors.CYAN}{strat}{Colors.ENDC}"
                        strat_plain = strip_ansi(strat_str)

                        # Visual bar
                        bar_width = 20
                        fill = int(bar_width * streak / max_streak) if max_streak > 0 else 0
                        color = Colors.GREEN
                        bar = f"[{color}{'=' * fill}{Colors.ENDC}{' ' * (bar_width - fill)}]"
                        print(f"{a:<6} {warrior_id:<12} {strat_str:<{20 + (len(strat_str) - len(strat_plain))}} {streak:>8}   {bar}")
                print("-" * 85)
            else:
                # Show detailed leaderboard for one or more arenas
                for a, top in results.items():
                    print(f"\n{Colors.BOLD}{Colors.HEADER}--- LEADERBOARD: Arena {a} ---{Colors.ENDC}")
                    print("-" * 85)
                    print(f"{'Rank':<4} {'Warrior':<12} {'Strategy':<20} {'Streak':>8}   {'Performance'}")
                    print("-" * 85)

                    max_streak = top[0][1] if top else 1
                    for i, (warrior_id, streak) in enumerate(top, 1):
                        path = _resolve_warrior_path(str(warrior_id), a)
                        strat = identify_strategy(analyze_warrior(path))
                        strat_str = f"{Colors.CYAN}{strat}{Colors.ENDC}"
                        strat_plain = strip_ansi(strat_str)

                        color = Colors.GREEN if i == 1 else Colors.ENDC
                        # Visual bar
                        bar_width = 20
                        fill = int(bar_width * streak / max_streak) if max_streak > 0 else 0
                        bar = f"[{color}{'=' * fill}{Colors.ENDC}{' ' * (bar_width - fill)}]"
                        streak_str = f"{color}{streak:>8}{Colors.ENDC}"
                        streak_plain = strip_ansi(streak_str)

                        print(f"{i:>2}.  {warrior_id:<12} {strat_str:<{20 + (len(strat_str) - len(strat_plain))}} {streak_str:>{8 + (len(streak_str) - len(streak_plain))}}   {bar}")
                    print("-" * 85)
    sys.exit(0)

  if "--trends" in sys.argv or "-r" in sys.argv:
    arena_idx = _get_arena_idx()
    run_trend_analysis(arena_idx)
    sys.exit(0)

  if "--report" in sys.argv or "-g" in sys.argv:
    arena_idx = _get_arena_idx()
    run_report(arena_idx)
    sys.exit(0)

  if "--view" in sys.argv or "-v" in sys.argv:
    try:
        idx = sys.argv.index("--view") if "--view" in sys.argv else sys.argv.index("-v")
        arena_idx = _get_arena_idx()

        target = None
        if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
            target = _resolve_warrior_path(sys.argv[idx+1], arena_idx)
        else:
            target = _resolve_warrior_path("top", arena_idx)

        if not os.path.exists(target):
            print(f"Error: File '{target}' not found.")
            sys.exit(1)

        print(f"{Colors.BOLD}{Colors.HEADER}--- Viewing: {target} ---{Colors.ENDC}")
        with open(target, 'r') as f:
            print(f.read())
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

  if "--harvest" in sys.argv or "-p" in sys.argv:
    try:
        idx = sys.argv.index("--harvest") if "--harvest" in sys.argv else sys.argv.index("-p")
        if len(sys.argv) < idx + 2:
            print("Usage: --harvest|-p <folder> [--top <N>] [--arena|-a <N>]")
            sys.exit(1)

        target_dir = sys.argv[idx+1]

        # Determine arena index (default all)
        arena_idx = None
        if "--arena" in sys.argv or "-a" in sys.argv:
            try:
                a_idx = sys.argv.index("--arena") if "--arena" in sys.argv else sys.argv.index("-a")
                if len(sys.argv) > a_idx + 1:
                    arena_idx = int(sys.argv[a_idx+1])
            except ValueError:
                pass

        # Determine limit (default 10)
        limit = 10
        if "--top" in sys.argv:
            try:
                t_idx = sys.argv.index("--top")
                if len(sys.argv) > t_idx + 1:
                    limit = int(sys.argv[t_idx+1])
            except ValueError:
                pass

        run_harvest(target_dir, arena_idx=arena_idx, limit=limit)
        sys.exit(0)
    except Exception as e:
        print(f"Error during harvest: {e}")
        sys.exit(1)

  if "--collect" in sys.argv or "-k" in sys.argv:
    try:
        idx = sys.argv.index("--collect") if "--collect" in sys.argv else sys.argv.index("-k")

        targets = []
        for i in range(idx + 1, len(sys.argv)):
            if sys.argv[i].startswith('-'):
                break
            targets.append(sys.argv[i])

        if not targets:
            print("Usage: --collect|-k <warrior_file|dir|selector...> [-o <output_path>] [--arena|-a <N>]")
            sys.exit(1)

        arena_idx = _get_arena_idx()

        output_path = LIBRARY_PATH
        if "--output" in sys.argv or "-o" in sys.argv:
            o_idx = sys.argv.index("--output") if "--output" in sys.argv else sys.argv.index("-o")
            if len(sys.argv) > o_idx + 1:
                output_path = sys.argv[o_idx+1]

        run_instruction_collection(targets, output_path, arena_idx)
        sys.exit(0)
    except Exception as e:
        print(f"Error during instruction collection: {e}")
        sys.exit(1)

  if "--seed" in sys.argv:
    try:
        idx = sys.argv.index("--seed")
        targets = []
        for i in range(idx + 1, len(sys.argv)):
            if sys.argv[i].startswith('-'):
                break
            targets.append(sys.argv[i])

        if not targets:
            print("Usage: --seed <targets...> [--arena|-a <N>]")
            sys.exit(1)

        arena_idx = None
        if "--arena" in sys.argv or "-a" in sys.argv:
            arena_idx = _get_arena_idx()

        run_seeding(targets, arena_idx)
        sys.exit(0)
    except Exception as e:
        print(f"Error during seeding: {e}")
        sys.exit(1)

  if "--export" in sys.argv or "-e" in sys.argv:
    try:
        idx = sys.argv.index("--export") if "--export" in sys.argv else sys.argv.index("-e")
        arena_idx = _get_arena_idx()

        target = None
        if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
            target = sys.argv[idx+1]
        else:
            target = "top"

        output_path = None
        if "--output" in sys.argv or "-o" in sys.argv:
            o_idx = sys.argv.index("--output") if "--output" in sys.argv else sys.argv.index("-o")
            if len(sys.argv) > o_idx + 1:
                output_path = sys.argv[o_idx+1]

        run_export(target, output_path, arena_idx)
        sys.exit(0)
    except Exception as e:
        print(f"Error during export: {e}")
        sys.exit(1)

  if "--battle" in sys.argv or "-b" in sys.argv:
    try:
        idx = sys.argv.index("--battle") if "--battle" in sys.argv else sys.argv.index("-b")
        arena_idx = _get_arena_idx()

        # Extract up to 2 warrior arguments that are not flags
        targets = []
        for i in range(idx + 1, len(sys.argv)):
            if sys.argv[i].startswith('-'):
                break
            targets.append(sys.argv[i])

        if len(targets) == 0:
            # Default: Top vs Top2
            w1_path = "top1"
            w2_path = "top2"
        elif len(targets) == 1:
            # Default: Target vs Top (or Top2 if Target is Top)
            w1_path = targets[0]
            w2_path = "top2" if w1_path.lower() in ["top", "top1"] else "top1"
        else:
            w1_path = targets[0]
            w2_path = targets[1]

        w1 = _resolve_warrior_path(w1_path, arena_idx)
        w2 = _resolve_warrior_path(w2_path, arena_idx)

        run_custom_battle(w1, w2, arena_idx)
        sys.exit(0)
    except Exception as e:
        print(f"Error during battle: {e}")
        sys.exit(1)

  if "--tournament" in sys.argv or "-t" in sys.argv:
      try:
          idx = sys.argv.index("--tournament") if "--tournament" in sys.argv else sys.argv.index("-t")
          arena_idx = _get_arena_idx()

          targets = []
          if "--champions" in sys.argv:
              # Auto-populate with champions from all arenas
              for i in range(LAST_ARENA + 1):
                  targets.append(f"top@{i}")
          else:
              # Collect all arguments until the next flag
              for i in range(idx + 1, len(sys.argv)):
                  if sys.argv[i].startswith('-'):
                      break
                  targets.append(sys.argv[i])

          if not targets:
              # Default: Top 10 warriors of the current arena
              for i in range(1, 11):
                  targets.append(f"top{i}")
              print(f"{Colors.CYAN}No targets specified. Running tournament for the top 10 warriors of Arena {arena_idx}.{Colors.ENDC}")

          run_tournament(targets, arena_idx)
          sys.exit(0)
      except ValueError:
          print("Invalid arguments.")
          sys.exit(1)

  if "--benchmark" in sys.argv or "-m" in sys.argv:
      try:
          if "--benchmark" in sys.argv:
              idx = sys.argv.index("--benchmark")
          else:
              idx = sys.argv.index("-m")

          if len(sys.argv) < idx + 3:
              print("Usage: --benchmark|-m <warrior_file> <folder> [--arena|-a <N>]")
              sys.exit(1)

          arena_idx = _get_arena_idx()
          warrior_file = _resolve_warrior_path(sys.argv[idx+1], arena_idx)
          directory = sys.argv[idx+2]

          run_benchmark(warrior_file, directory, arena_idx)
          sys.exit(0)
      except ValueError:
          print("Invalid arguments.")
          sys.exit(1)

  if "--normalize" in sys.argv or "-n" in sys.argv:
      try:
          if "--normalize" in sys.argv:
              idx = sys.argv.index("--normalize")
          else:
              idx = sys.argv.index("-n")

          if len(sys.argv) < idx + 2:
              print("Usage: --normalize|-n <warrior_file|dir> [-o <output_path>] [--arena|-a <N>]")
              sys.exit(1)

          arena_idx = _get_arena_idx()
          warrior_file = _resolve_warrior_path(sys.argv[idx+1], arena_idx)

          output_path = None
          if "--output" in sys.argv or "-o" in sys.argv:
              if "--output" in sys.argv:
                  o_idx = sys.argv.index("--output")
              else:
                  o_idx = sys.argv.index("-o")

              if len(sys.argv) > o_idx + 1:
                  output_path = sys.argv[o_idx+1]

          run_normalization(warrior_file, arena_idx, output_path=output_path)
          sys.exit(0)
      except ValueError:
          print("Invalid arguments.")
          sys.exit(1)

  if "--inspect" in sys.argv or "-x" in sys.argv:
      try:
          idx = sys.argv.index("--inspect") if "--inspect" in sys.argv else sys.argv.index("-x")
          arena_idx = _get_arena_idx()

          targets = []
          for i in range(idx + 1, len(sys.argv)):
              if sys.argv[i].startswith('-'):
                  break
              targets.append(sys.argv[i])

          if not targets:
              # Default to champion if no target provided
              targets = ["top"]

          for target in targets:
              run_inspection(target, arena_idx)
          sys.exit(0)
      except Exception as e:
          print(f"Error during inspection: {e}")
          sys.exit(1)

  if "--lineage" in sys.argv or "-j" in sys.argv:
      try:
          idx = sys.argv.index("--lineage") if "--lineage" in sys.argv else sys.argv.index("-j")
          arena_idx = _get_arena_idx()
          target = None

          if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
              target = sys.argv[idx+1]
          else:
              target = "top"

          depth = 3
          if "--depth" in sys.argv:
              d_idx = sys.argv.index("--depth")
              if len(sys.argv) > d_idx + 1:
                  depth = int(sys.argv[d_idx+1])

          run_lineage(target, arena_idx, depth=depth)
          sys.exit(0)
      except Exception as e:
          print(f"Error during lineage tracing: {e}")
          sys.exit(1)

  if "--analyze" in sys.argv or "-i" in sys.argv:
      try:
          idx = sys.argv.index("--analyze") if "--analyze" in sys.argv else sys.argv.index("-i")
          arena_idx = _get_arena_idx()
          target = None

          if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
              target = _resolve_warrior_path(sys.argv[idx+1], arena_idx)
          else:
              # Default to champion if no target provided
              target = _resolve_warrior_path("top", arena_idx)
              if not os.path.exists(target):
                  print(f"{Colors.YELLOW}No champion found for Arena {arena_idx} to analyze.{Colors.ENDC}")
                  sys.exit(1)

          if not target:
              print("Usage: --analyze|-i [file|dir|selector] [--arena <N>] [--json]")
              sys.exit(1)

          if os.path.isdir(target):
              stats = analyze_population(target)
          else:
              stats = analyze_warrior(target)

          if "--json" in sys.argv:
              print(json.dumps(stats, indent=2))
          else:
              print_analysis(stats)
          sys.exit(0)
      except Exception as e:
          print(f"Error during analysis: {e}")
          sys.exit(1)

  if "--meta" in sys.argv or "-u" in sys.argv:
      try:
          idx = sys.argv.index("--meta") if "--meta" in sys.argv else sys.argv.index("-u")
          arena_idx = _get_arena_idx()
          target = ""

          if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
              target = sys.argv[idx+1]
          else:
              # Default to arena population if no target provided
              target = f"arena{arena_idx}"

          json_output = "--json" in sys.argv
          run_meta_analysis(target, arena_idx, json_output=json_output)
          sys.exit(0)
      except Exception as e:
          print(f"Error during meta-analysis: {e}")
          sys.exit(1)

  if "--gauntlet" in sys.argv or "-G" in sys.argv:
      try:
          idx = sys.argv.index("--gauntlet") if "--gauntlet" in sys.argv else sys.argv.index("-G")
          arena_idx = _get_arena_idx()
          target = None

          if len(sys.argv) > idx + 1 and not sys.argv[idx+1].startswith('-'):
              target = sys.argv[idx+1]
          else:
              target = "top"

          run_gauntlet(target, arena_idx)
          sys.exit(0)
      except Exception as e:
          print(f"Error during gauntlet run: {e}")
          sys.exit(1)

  if "--compare" in sys.argv or "-y" in sys.argv:
      try:
          idx = sys.argv.index("--compare") if "--compare" in sys.argv else sys.argv.index("-y")
          arena_idx = _get_arena_idx()

          # Extract up to 2 warrior arguments that are not flags
          targets = []
          for i in range(idx + 1, len(sys.argv)):
              if sys.argv[i].startswith('-'):
                  break
              targets.append(sys.argv[i])

          if len(targets) == 0:
              t1 = "top1"
              t2 = "top2"
          elif len(targets) == 1:
              t1 = targets[0]
              t2 = "top2" if t1.lower() in ["top", "top1"] else "top1"
          else:
              t1 = targets[0]
              t2 = targets[1]

          json_output = "--json" in sys.argv

          run_comparison(t1, t2, arena_idx, json_output=json_output)
          sys.exit(0)
      except Exception as e:
          print(f"Error during comparison: {e}")
          sys.exit(1)

  if "--diff" in sys.argv or "-f" in sys.argv:
      try:
          idx = sys.argv.index("--diff") if "--diff" in sys.argv else sys.argv.index("-f")
          arena_idx = _get_arena_idx()

          # Extract up to 2 warrior arguments that are not flags
          targets = []
          for i in range(idx + 1, len(sys.argv)):
              if sys.argv[i].startswith('-'):
                  break
              targets.append(sys.argv[i])

          if len(targets) == 0:
              t1 = "top1"
              t2 = "top2"
          elif len(targets) == 1:
              t1 = targets[0]
              t2 = "top2" if t1.lower() in ["top", "top1"] else "top1"
          else:
              t1 = targets[0]
              t2 = targets[1]

          run_diff(t1, t2, arena_idx)
          sys.exit(0)
      except Exception as e:
          print(f"Error during diff: {e}")
          sys.exit(1)

  if "--dump-config" in sys.argv or "-d" in sys.argv:
    print("Current Configuration:")
    # Retrieve all global variables that look like configuration settings (UPPERCASE)
    # and were likely populated from settings.ini
    config_keys = [
        "LAST_ARENA", "CORESIZE_LIST", "SANITIZE_LIST", "CYCLES_LIST",
        "PROCESSES_LIST", "WARLEN_LIST", "WARDISTANCE_LIST", "NUMWARRIORS",
        "ALREADYSEEDED", "CLOCK_TIME", "BATTLE_LOG_FILE", "FINAL_ERA_ONLY",
        "NOTHING_LIST", "RANDOM_LIST", "NAB_LIST", "MINI_MUT_LIST",
        "MICRO_MUT_LIST", "LIBRARY_LIST", "MAGIC_NUMBER_LIST", "ARCHIVE_LIST",
        "UNARCHIVE_LIST", "LIBRARY_PATH", "CROSSOVERRATE_LIST",
        "TRANSPOSITIONRATE_LIST", "BATTLEROUNDS_LIST", "PREFER_WINNER_LIST",
        "INSTR_SET", "INSTR_MODES", "INSTR_MODIF"
    ]

    for key in config_keys:
        if key in globals():
            print(f"{key}={globals()[key]}")
    sys.exit(0)

  if ALREADYSEEDED == False:
    print("Seeding")
    os.makedirs("archive", exist_ok=True)
    for arena in range(0, LAST_ARENA + 1):
      os.makedirs(f"arena{arena}", exist_ok=True)
      for i in range(1, NUMWARRIORS+1):
        with open(os.path.join(f"arena{arena}", f"{i}.red"), "w") as f:
            for j in range(1, WARLEN_LIST[arena]+1):
              #Biasing toward more viable warriors: 3 in 4 chance of choosing an address within the warrior.
              #Same bias in mutation.
              num1 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
              num2 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
              f.write(random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+ \
                      str(corenorm(coremod(num1,SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+","+ \
                      random.choice(INSTR_MODES)+str(corenorm(coremod(num2,SANITIZE_LIST[arena]), \
                      CORESIZE_LIST[arena]))+"\n")

  starttime=time.time() #time in seconds
  era=-1
  data_logger = DataLogger(filename=BATTLE_LOG_FILE)
  battle_count = 0
  last_result = ""

  try:
    while(True):
      # Update the evolution era based on how much time has passed.
      prevera=era
      curtime=time.time()
      runtime_in_hours=(curtime-starttime)/60/60
      era=0
      if runtime_in_hours>CLOCK_TIME*(1/3):
        era=1
      if runtime_in_hours>CLOCK_TIME*(2/3):
        era=2
      if runtime_in_hours>CLOCK_TIME:
        print(f"\n{Colors.GREEN}Time limit reached. Evolution complete.{Colors.ENDC}")
        break
      if FINAL_ERA_ONLY==True:
        era=2
      if era!=prevera:
        print(f"\n{Colors.YELLOW}************** Switching from era {prevera + 1} to {era + 1} *******************{Colors.ENDC}")
        bag = construct_marble_bag(era)

      runtime_in_seconds = time.time() - starttime
      bps = battle_count / runtime_in_seconds if runtime_in_seconds > 0 else 0
      remaining_seconds = (CLOCK_TIME - runtime_in_hours) * 3600
      remaining_str = format_time_remaining(remaining_seconds)
      progress_percent = (runtime_in_hours / CLOCK_TIME) * 100
      bar_str = draw_progress_bar(progress_percent, width=10)

      status_line = f"{remaining_str} | {bar_str} | Era {era+1} | {battle_count:,} ({bps:.1f}/s)"

      # Add last battle result if available and fits in terminal
      cols, _ = shutil.get_terminal_size()
      if last_result and len(strip_ansi(status_line + last_result)) < cols:
          status_line += last_result

      # Clear line and print status
      print_status_line(status_line)

      # Select a random arena and two different warriors to compete.
      arena=random.randint(0, LAST_ARENA)
      cont1 = random.randint(1, NUMWARRIORS)
      cont2 = cont1
      while cont2 == cont1:
        cont2 = random.randint(1, NUMWARRIORS)
      file1 = os.path.join(f"arena{arena}", f"{cont1}.red")
      file2 = os.path.join(f"arena{arena}", f"{cont2}.red")
      cmd = construct_battle_command(file1, file2, arena, rounds=BATTLEROUNDS_LIST[era])
      raw_output = run_nmars_subprocess(cmd)

      scores, warriors = parse_nmars_output(raw_output)

      if len(scores) < 2:
        continue
      battle_count += 1

      res_winner, res_loser = determine_winner(scores, warriors)
      winner = cont1 if res_winner == 1 else cont2
      loser = cont1 if res_loser == 1 else cont2

      if ARCHIVE_LIST[era]!=0 and random.randint(1,ARCHIVE_LIST[era])==1:
        # Occasionally save winners to an archive to preserve successful genes long-term.
        if VERBOSE:
            print("storing in archive")
        with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
          winlines = fw.readlines()
        with open(os.path.join("archive", f"{random.randint(1,9999)}.red"), "w") as fd:
          for line in winlines:
            fd.write(line)

      if UNARCHIVE_LIST[era]!=0 and random.randint(1,UNARCHIVE_LIST[era])==1:
        if os.path.exists("archive") and os.listdir("archive"):
          if VERBOSE:
              print("unarchiving")
          with open(os.path.join("archive", random.choice(os.listdir("archive")))) as fs:
            sourcelines = fs.readlines()
          # Reintroduce a warrior from the archive to increase the variety of strategies.
          # We clean the instructions to ensure they follow the current arena's rules.
          fl = open(os.path.join(f"arena{arena}", f"{loser}.red"), "w")
          countoflines=0
          for line in sourcelines:
            stripped = line.strip()
            if not stripped or stripped.startswith(';'):
                continue
            countoflines=countoflines+1
            if countoflines>WARLEN_LIST[arena]:
              break
            try:
                line = normalize_instruction(line, CORESIZE_LIST[arena], SANITIZE_LIST[arena])
                fl.write(line)
            except (ValueError, IndexError):
                countoflines -= 1
                continue
          while countoflines<WARLEN_LIST[arena]:
            countoflines=countoflines+1
            fl.write('DAT.F $0,$0\n')
          fl.close()
          continue #out of while (loser replaced by archive, no point breeding)

      # The loser is replaced by a new warrior created from the winner and another random parent.
      with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
        winlines = fw.readlines()
      randomwarrior=str(random.randint(1, NUMWARRIORS))
      if VERBOSE:
          print("winner will breed with "+randomwarrior)
      with open(os.path.join(f"arena{arena}", f"{randomwarrior}.red"), "r") as fr:
        ranlines = fr.readlines()

      offspring = breed_warriors(winlines, ranlines, era, arena, bag)

      with open(os.path.join(f"arena{arena}", f"{loser}.red"), "w") as fl:
        fl.writelines(offspring)
      data_logger.log_row(era=era, arena=arena, winner=winner, loser=loser, score1=scores[0], score2=scores[1], \
                          bred_with=randomwarrior)

      # Update last_result for next status line refresh
      last_result = f" | {Colors.CYAN}A{arena}{Colors.ENDC}: {Colors.GREEN}#{winner}{Colors.ENDC}>{Colors.RED}#{loser}{Colors.ENDC}"

  except KeyboardInterrupt:
    print(f"\n\n{Colors.YELLOW}Evolution stopped by user.{Colors.ENDC}")
    print_status()
    sys.exit(0)

  # Final status on natural completion
  print_status()

#  time.sleep(3) #uncomment this for simple proportion of sleep if you're using computer for something else

#experimental. detect if computer being used and yield to other processes.
#  while psutil.cpu_percent()>30: #I'm not sure what percentage of CPU usage to watch for. Probably depends
                                  # from computer to computer and personal taste.
#    print("High CPU Usage. Pausing for 3 seconds.")
#    time.sleep(3)
