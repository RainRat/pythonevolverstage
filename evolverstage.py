# A Python-based Genetic Evolver for Core War
# This script manages the evolution, breeding, and battling of warriors across multiple arenas.

'''
Core War Evolver

Evolve and test Redcode warriors using a genetic algorithm.
For license information, see LICENSE.md.

Usage:
  python evolverstage.py [COMMAND] [OPTIONS]

General Commands:
  --check, -c          Check your configuration and simulator setup.
  --status, -s         Display the current status of all arenas and population.
                       Add --json for machine-readable output.
  --leaderboard, -l    Show the top-performing warriors based on recent win streaks.
                       Usage: --leaderboard [--arena <N>] [--json]
  --trends, -r         Analyze evolution trends by comparing the population to the top performers.
                       Usage: --trends [--arena <N>]
  --dump-config, -d    Show the active configuration from settings.ini and exit.

Evolution:
  --restart            Start a new evolution from scratch (overwrites existing files).
  --resume             Continue evolution using existing warriors and logs.
  --seed               Populate an arena with a set of specific warriors.
                       Usage: --seed <targets...> [--arena <N>]
  (Run with no command to start/continue evolution based on settings.ini)

Battle Tools:
  --battle, -b         Run a match between two specific warriors.
                       Usage: --battle <warrior1> <warrior2> [--arena <N>]
  --tournament, -t     Run a round-robin competition between a group of warriors.
                       Use --champions to automatically include winners from every arena.
                       Usage: --tournament <directory|selectors...> [--champions] [--arena <N>]
  --benchmark, -m      Test one warrior against every opponent in a directory.
                       Usage: --benchmark <warrior> <directory> [--arena <N>]

Analysis & Utilities:
  --analyze, -i        Get statistics on instructions, opcodes, and addressing modes.
                       Usage: --analyze <file|dir|selector> [--arena <N>] [--json]
  --view, -v           Display the source code of a warrior.
                       Usage: --view <warrior|selector> [--arena <N>]
  --normalize, -n      Clean and standardize a warrior's Redcode format.
                       Usage: --normalize <warrior|selector> [--arena <N>]
  --harvest, -p        Collect the best warriors from the leaderboard into a folder.
                       Usage: --harvest <directory> [--top <N>] [--arena <N>]
  --collect, -k        Extract and normalize instructions from warriors into a library file.
                       Usage: --collect <targets...> [-o <output>] [--arena <N>]

Dynamic Selectors:
  Instead of a filename, you can use these keywords in most commands:
  top, topN            Select the #1 (or #N) warrior from the leaderboard.
  random               Select a random warrior from the current population.
  selector@N           Target a specific arena (e.g., top@0, random@2).

Examples:
  python evolverstage.py --status
  python evolverstage.py --battle top@0 top@1
  python evolverstage.py --tournament --champions
  python evolverstage.py --benchmark top archive/
  python evolverstage.py --view random@2
  python evolverstage.py --seed best_warriors/ --arena 0
'''

import random
import itertools
import os
import re
import time
import sys
import shutil
import json
#import psutil #Not currently active. See bottom of code for how it could be used.
import configparser
import subprocess
from enum import Enum
import csv
from collections import deque

from evolver.logger import DataLogger

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

def run_nmars_command(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
  """
  Runs the nMars simulator to battle two warriors.

  It builds the command string with all the rules for the specific arena (size, cycles, etc.)
  and returns the raw output from nMars, which contains the scores.
  """
  file1 = os.path.join(f"arena{arena}", f"{cont1}.red")
  file2 = os.path.join(f"arena{arena}", f"{cont2}.red")
  cmd = construct_battle_command(file1, file2, arena, coresize=coresize, cycles=cycles, processes=processes, warlen=warlen, wardistance=wardistance, rounds=battlerounds)
  return run_nmars_subprocess(cmd)

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

    cmd = construct_battle_command(file1, file2, arena_idx)

    print(f"{Colors.BOLD}Starting battle: {file1} vs {file2}{Colors.ENDC}")
    print(f"Arena: {arena_idx} (Size: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]})")

    output = run_nmars_subprocess(cmd)

    if output:
        print("-" * 40)
        print(output.strip())
        print("-" * 40)
    else:
        print(f"{Colors.RED}No output received from nMars.{Colors.ENDC}")

def run_tournament(targets, arena_idx):
    """
    Runs a round-robin tournament between a directory of warriors or a specific list of warriors.
    """
    if isinstance(targets, str):
        targets = [targets]

    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    abs_files = []
    file_map = {}

    # Check if we are given a single directory or a list of files/selectors
    if len(targets) == 1 and os.path.isdir(targets[0]):
        directory = targets[0]
        files = [f for f in os.listdir(directory) if f.endswith('.red')]
        if len(files) < 2:
            print(f"Error: A tournament requires at least two warriors (.red files) in the '{directory}' folder.")
            return
        abs_files = [os.path.join(directory, f) for f in files]
        file_map = {path: f for path, f in zip(abs_files, files)}
        print(f"Tournament: {len(files)} warriors from directory '{directory}'")
    elif len(targets) == 1 and not os.path.exists(targets[0]):
        # Maintain backward compatibility for single directory not found error message
        print(f"Error: Directory '{targets[0]}' not found.")
        return
    else:
        # It's a list of selectors/files
        for sel in targets:
            path = _resolve_warrior_path(sel, arena_idx)
            if os.path.exists(path):
                abs_files.append(path)
                file_map[path] = sel
            else:
                print(f"Warning: Warrior '{sel}' not found. Skipping.")

        if len(abs_files) < 2:
            print("Error: A tournament requires at least two warriors to compete.")
            return
        print(f"Tournament: {len(abs_files)} specific warriors.")

    scores = {file_map[f]: 0 for f in abs_files}

    # Generate pairs
    pairs = list(itertools.combinations(abs_files, 2))
    total_battles = len(pairs)
    print(f"Total battles: {total_battles}")
    print(f"Arena: {arena_idx} (Size: {CORESIZE_LIST[arena_idx]}, Cycles: {CYCLES_LIST[arena_idx]})")

    for i, (p1, p2) in enumerate(pairs, 1):
        # Progress
        print(f"Battle {i}/{total_battles}: {file_map[p1]} vs {file_map[p2]}", end='\r')

        cmd = construct_battle_command(p1, p2, arena_idx)
        output = run_nmars_subprocess(cmd)

        s, warriors = parse_nmars_output(output)

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

    print(f"\n\n{Colors.BOLD}Tournament Results:{Colors.ENDC}")
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, score) in enumerate(sorted_scores, 1):
        color = Colors.GREEN if rank == 1 else Colors.ENDC
        print(f"{color}{rank}. {name}: {score}{Colors.ENDC}")

def run_benchmark(warrior_file, directory, arena_idx):
    """
    Runs a benchmark of a specific warrior against all warriors in a directory.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    if not os.path.exists(warrior_file):
        print(f"Error: File '{warrior_file}' not found.")
        return
    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' not found.")
        return

    opponents = [f for f in os.listdir(directory) if f.endswith('.red')]
    if not opponents:
        print(f"Error: No opponents found. Please ensure the folder '{directory}' contains .red files.")
        return

    print(f"Benchmarking {warrior_file} against {len(opponents)} warriors in {directory}")
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

    for i, opp in enumerate(opponents, 1):
        opp_path = os.path.join(directory, opp)
        # Progress
        print(f"Battle {i}/{len(opponents)}: vs {opp}", end='\r')

        cmd = construct_battle_command(abs_warrior_file, opp_path, arena_idx)
        output = run_nmars_subprocess(cmd)

        scores, warriors = parse_nmars_output(output)

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

    print(f"\n\n{Colors.BOLD}Benchmark Results for {warrior_file}:{Colors.ENDC}")
    print(f"  Total Battles: {len(opponents)}")
    if len(opponents) > 0:
        print(f"  {Colors.GREEN}Wins:   {stats['wins']} ({stats['wins']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  {Colors.RED}Losses: {stats['losses']} ({stats['losses']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  {Colors.YELLOW}Ties:   {stats['ties']} ({stats['ties']/len(opponents)*100:.1f}%){Colors.ENDC}")
        print(f"  Total Score: {stats['score']}")
        print(f"  Average Score: {stats['score']/len(opponents):.2f}")

def run_normalization(filepath, arena_idx, output_path=None):
    """
    Reads a warrior file (or directory) and outputs the normalized instructions.

    If filepath is a directory, output_path must be a directory.
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

    # Directory Mode
    if os.path.isdir(filepath):
        if not output_path:
            print("Error: Output directory must be specified when normalizing a directory.")
            return

        os.makedirs(output_path, exist_ok=True)

        files = [f for f in os.listdir(filepath) if f.endswith('.red')]
        if not files:
            print(f"No .red files found in {filepath}")
            return

        print(f"Normalizing {len(files)} files from {filepath} to {output_path}...")
        for f in files:
            in_f = os.path.join(filepath, f)
            out_f = os.path.join(output_path, f)
            # Recursive call for single file
            run_normalization(in_f, arena_idx, output_path=out_f)
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
            for filepath in files_to_process:
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
        print(f"Successfully collected {count} instructions.")
    except Exception as e:
        print(f"Error writing to library file {output_path}: {e}")

def run_harvest(target_dir, arena_idx=None, limit=10):
    """
    Collects the top performers from one or all arenas into a single directory.
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
                print(f"Error processing warrior {src} for Arena {a}: {e}")
                break

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

    # Regex to extract components robustly: OPCODE[.MODIFIER] <MODE>A-VAL[,<MODE>B-VAL]
    match = re.match(r'^([A-Z]+)(?:\.([A-Z]+))?\s+([^,]+)(?:,\s*(.+))?$', clean_instr, re.I)
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
    #note nMars will sort by score regardless of the order in the command-line, so match up score with warrior
    output = raw_output.splitlines()
    numline=0
    for line in output:
        numline=numline+1
        if "scores" in line:
            if VERBOSE:
                print(line.strip())
            splittedline=line.split()
            # Ensure line has enough parts to avoid IndexError
            if len(splittedline) > 4:
                scores.append(int(splittedline[4]))
                warriors.append(int(splittedline[0]))
    if VERBOSE:
        print(numline)
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

def get_latest_log_entry():
    """
    Retrieves and parses the last entry from the battle log file.
    """
    if not BATTLE_LOG_FILE or not os.path.exists(BATTLE_LOG_FILE):
        return None
    try:
        with open(BATTLE_LOG_FILE, 'r') as f:
            lines = deque(f, maxlen=1)
            if not lines:
                return None

            last_line = lines[0].strip()
            if not last_line or "winner,loser" in last_line:
                return None

            # Manually parse the CSV line to avoid reading the whole file
            # era,arena,winner,loser,score1,score2,bred_with
            parts = last_line.split(',')
            if len(parts) >= 6:
                return {
                    'era': parts[0],
                    'arena': parts[1],
                    'winner': parts[2],
                    'loser': parts[3],
                    'score1': parts[4],
                    'score2': parts[5]
                }
            return None
    except Exception:
        return None

def get_evolution_status():
    """
    Gathers the current status of the evolution system into a dictionary.
    """
    champions = get_leaderboard(limit=1)

    status = {
        "latest_log": get_latest_log_entry(),
        "arenas": [],
        "archive": None
    }

    for i in range(LAST_ARENA + 1):
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

            # Add champion info if available
            if i in champions and champions[i]:
                arena_info["champion"] = champions[i][0][0]
                arena_info["champion_wins"] = champions[i][0][1]
            else:
                arena_info["champion"] = None
                arena_info["champion_wins"] = 0

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
                # Handles: OPCODE[.MODIFIER] [<MODE>A[,<MODE>B]]
                match = re.match(r'^([A-Z]+)(?:\.([A-Z]+))?(?:\s+([^,]+)(?:,\s*(.+))?)?$', line, re.I)
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
    Aggregates statistics for all warriors in a directory.
    """
    if not os.path.exists(directory):
        return None

    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.red')]
    return analyze_files(files, directory)

def run_trend_analysis(arena_idx):
    """
    Compares the distribution of instructions in the entire arena population
    vs the top-performing warriors (the Meta).
    """
    arena_dir = f"arena{arena_idx}"
    if not os.path.exists(arena_dir):
        print(f"{Colors.RED}Arena directory {arena_dir} not found.{Colors.ENDC}")
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
    print_trends(pop_stats, meta_stats, arena_idx)

def print_trends(pop_stats, meta_stats, arena_idx):
    """
    Prints a side-by-side comparison of population vs meta statistics.
    """
    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Trend Analysis: Arena {arena_idx} ---{Colors.ENDC}")
    print(f"Population: {pop_stats['count']:4} warriors")
    print(f"Meta:       {meta_stats['count']:4} warriors (Top performers)")
    print("-" * 60)

    def print_section(title, pop_data, meta_data, total_pop, total_meta):
        print(f"\n{Colors.BOLD}Trait: {title}{Colors.ENDC}")
        header = f"  {'Value':<10} | {'Pop %':>8} | {'Meta %':>8} | {'Delta':>8}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        # Get all unique keys
        all_keys = sorted(set(pop_data.keys()) | set(meta_data.keys()))

        for key in all_keys:
            pop_count = pop_data.get(key, 0)
            meta_count = meta_data.get(key, 0)

            pop_pct = (pop_count / total_pop * 100) if total_pop > 0 else 0
            meta_pct = (meta_count / total_meta * 100) if total_meta > 0 else 0
            delta = meta_pct - pop_pct

            delta_val_str = f"{delta:+.1f}%"
            if delta > 5:
                delta_str = f"{Colors.GREEN}{delta_val_str:>8}{Colors.ENDC}"
            elif delta < -5:
                delta_str = f"{Colors.RED}{delta_val_str:>8}{Colors.ENDC}"
            else:
                delta_str = f"{delta_val_str:>8}"

            print(f"  {key:<10} | {pop_pct:>7.1f}% | {meta_pct:>7.1f}% | {delta_str}")

    print_section("Opcodes", pop_stats['opcodes'], meta_stats['opcodes'],
                  pop_stats['total_instructions'], meta_stats['total_instructions'])

    if pop_stats['modifiers'] or meta_stats['modifiers']:
        pop_total_mods = sum(pop_stats['modifiers'].values())
        meta_total_mods = sum(meta_stats['modifiers'].values())
        print_section("Modifiers", pop_stats['modifiers'], meta_stats['modifiers'],
                      pop_total_mods, meta_total_mods)

    if pop_stats['modes'] or meta_stats['modes']:
        pop_total_modes = sum(pop_stats['modes'].values())
        meta_total_modes = sum(meta_stats['modes'].values())
        print_section("Addressing Modes", pop_stats['modes'], meta_stats['modes'],
                      pop_total_modes, meta_total_modes)
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

def print_status_json(status_data):
    """
    Prints the status data as a JSON object.
    """
    print(json.dumps(status_data, indent=2))

def print_status():
    """
    Prints the current status of all arenas and the archive in a human-readable format.
    """
    data = get_evolution_status()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{Colors.BOLD}{Colors.HEADER}--- Evolver Status Dashboard ---{Colors.ENDC}")
    print(f"Captured: {now}")
    print("="*78)

    # Latest Activity
    log = data['latest_log']
    if log:
        try:
            summary = f"Era {int(log['era'])+1}, Arena {log['arena']}: {Colors.GREEN}Warrior {log['winner']}{Colors.ENDC} beat {Colors.RED}Warrior {log['loser']}{Colors.ENDC} ({log['score1']}-{log['score2']})"
            print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} {summary}")
        except (ValueError, KeyError):
            print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} {log}")
    else:
        print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} No battles recorded yet.")
    print("-" * 78)

    # Table Header
    header = f"{'Arena':<5} {'Size':>7} {'Cycles':>8} {'Procs':>6} {'Pop':>5} {'Len':>5} {'Champion':<12} {'Wins':>4} {'Status':<8}"
    print(f"{Colors.BOLD}{header}{Colors.ENDC}")
    print("-" * 78)

    total_warriors = 0
    for arena in data['arenas']:
        i = arena['id']
        size = arena['config']['size']
        cycles = arena['config']['cycles']
        procs = arena['config']['processes']

        champ_str = "-"
        wins_str = "-"

        if arena['exists']:
            pop = str(arena['population'])
            total_warriors += arena['population']
            avg_len = f"{arena['avg_length']:.1f}"
            status = f"{Colors.GREEN}OK{Colors.ENDC}"

            if arena.get('champion'):
                champ_str = f"#{arena['champion']}"
                wins_str = str(arena['champion_wins'])
                if arena['champion_wins'] > 0:
                    champ_str = f"{Colors.CYAN}{champ_str}{Colors.ENDC}"
                    wins_str = f"{Colors.BOLD}{Colors.GREEN}{wins_str}{Colors.ENDC}"
        else:
            pop = "-"
            avg_len = "-"
            status = f"{Colors.YELLOW}Unseeded{Colors.ENDC}"

        champ_plain = strip_ansi(champ_str)
        wins_plain = strip_ansi(wins_str)

        row = (
            f"{i:<5} {size:>7} {cycles:>8} {procs:>6} {pop:>5} {avg_len:>5} "
            f"{champ_str}{' ' * (12 - len(champ_plain))} "
            f"{' ' * (4 - len(wins_plain))}{wins_str} "
            f"{status}"
        )
        print(row)

    print("-" * 78)

    # Archive and Summary
    archive_count = data['archive']['count']
    archive_info = f"{Colors.GREEN}{archive_count}{Colors.ENDC}" if data['archive']['exists'] else f"{Colors.YELLOW}None{Colors.ENDC}"

    print(f"Total Population: {Colors.BOLD}{total_warriors}{Colors.ENDC} | Archive: {archive_info}")
    print("="*78 + "\n")

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

    return selector

def _get_arena_idx(default=0):
    """
    Helper to extract arena index from command line arguments.
    """
    arena_idx = default
    if "--arena" in sys.argv or "-a" in sys.argv:
        if "--arena" in sys.argv:
            a_idx = sys.argv.index("--arena")
        else:
            a_idx = sys.argv.index("-a")

        if len(sys.argv) > a_idx + 1:
            arena_idx = int(sys.argv[a_idx+1])
    else:
        # Smart Arena Inference: look for arenaN/ or arenaN\ in any argument
        for arg in sys.argv[1:]:
            match = re.search(r'arena(\d+)[/\\]', arg)
            if match:
                return int(match.group(1))

    return arena_idx

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

  if "--check" in sys.argv or "-c" in sys.argv:
    if validate_configuration():
        sys.exit(0)
    else:
        sys.exit(1)

  if "--status" in sys.argv or "-s" in sys.argv:
    if "--json" in sys.argv:
        print_status_json(get_evolution_status())
    else:
        print_status()
    sys.exit(0)

  if "--leaderboard" in sys.argv or "-l" in sys.argv:
    arena_idx = _get_arena_idx(default=None)

    results = get_leaderboard(arena_idx=arena_idx)

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"{Colors.YELLOW}No leaderboard data available.{Colors.ENDC}")
        else:
            print(f"\n{Colors.BOLD}{Colors.HEADER}--- Current Champions (Wins since last loss) ---{Colors.ENDC}")
            for arena, top in results.items():
                print(f"{Colors.BOLD}Arena {arena}:{Colors.ENDC}")
                for i, (warrior, wins) in enumerate(top, 1):
                    color = Colors.GREEN if i == 1 else Colors.ENDC
                    print(f"  {i}. Warrior {warrior:3}: {color}{wins} wins{Colors.ENDC}")
                print("-" * 30)
    sys.exit(0)

  if "--trends" in sys.argv or "-r" in sys.argv:
    arena_idx = _get_arena_idx()
    run_trend_analysis(arena_idx)
    sys.exit(0)

  if "--view" in sys.argv or "-v" in sys.argv:
    try:
        idx = sys.argv.index("--view") if "--view" in sys.argv else sys.argv.index("-v")
        if len(sys.argv) < idx + 2:
            print("Usage: --view|-v <warrior_file|selector> [--arena|-a <N>]")
            sys.exit(1)

        arena_idx = _get_arena_idx()
        target = _resolve_warrior_path(sys.argv[idx+1], arena_idx)

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
            print("Usage: --harvest|-p <directory> [--top <N>] [--arena|-a <N>]")
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

  if "--battle" in sys.argv or "-b" in sys.argv:
    try:
        if "--battle" in sys.argv:
            idx = sys.argv.index("--battle")
        else:
            idx = sys.argv.index("-b")

        if len(sys.argv) < idx + 3:
            print("Usage: --battle|-b <warrior1> <warrior2> [--arena|-a <N>]")
            sys.exit(1)

        arena_idx = _get_arena_idx()
        w1 = _resolve_warrior_path(sys.argv[idx+1], arena_idx)
        w2 = _resolve_warrior_path(sys.argv[idx+2], arena_idx)

        run_custom_battle(w1, w2, arena_idx)
        sys.exit(0)
    except ValueError:
        print("Invalid arguments.")
        sys.exit(1)

  if "--tournament" in sys.argv or "-t" in sys.argv:
      try:
          idx = sys.argv.index("--tournament") if "--tournament" in sys.argv else sys.argv.index("-t")

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
              print("Usage: --tournament|-t <directory|selectors...> [--champions] [--arena|-a <N>]")
              sys.exit(1)

          arena_idx = _get_arena_idx()
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
              print("Usage: --benchmark|-m <warrior_file> <directory> [--arena|-a <N>]")
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

  if "--analyze" in sys.argv or "-i" in sys.argv:
      try:
          if "--analyze" in sys.argv:
              idx = sys.argv.index("--analyze")
          else:
              idx = sys.argv.index("-i")

          target = None
          arena_idx = _get_arena_idx()

          if "--top" in sys.argv:
              # Find leader
              results = get_leaderboard(arena_idx=arena_idx, limit=1)
              if arena_idx in results and results[arena_idx]:
                  warrior_id, wins = results[arena_idx][0]
                  target = os.path.join(f"arena{arena_idx}", f"{warrior_id}.red")
                  print(f"Targeting Arena {arena_idx} champion: Warrior {warrior_id} ({wins} wins)")
              else:
                  print(f"{Colors.YELLOW}No champion found for Arena {arena_idx}.{Colors.ENDC}")
                  sys.exit(1)
          elif len(sys.argv) > idx + 1:
              target = sys.argv[idx+1]
              # check if target is an option
              if target.startswith('-'):
                  target = None
              else:
                  target = _resolve_warrior_path(target, arena_idx)

          if not target:
              print("Usage: --analyze|-i <file|dir> [--top] [--arena <N>] [--json]")
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
      #before we do anything, determine which era we are in.
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
      visible_len = len(strip_ansi(status_line))
      padding = " " * max(0, cols - visible_len - 1)
      print(f"\r{status_line}{padding}", end='', flush=True)

      #in a random arena
      arena=random.randint(0, LAST_ARENA)
      #two random warriors
      cont1 = random.randint(1, NUMWARRIORS)
      cont2 = cont1
      while cont2 == cont1: #no self fights
        cont2 = random.randint(1, NUMWARRIORS)
      raw_output = run_nmars_command(arena, cont1, cont2, CORESIZE_LIST[arena], CYCLES_LIST[arena], \
                                     PROCESSES_LIST[arena], WARLEN_LIST[arena], \
                                     WARDISTANCE_LIST[arena], BATTLEROUNDS_LIST[era])

      scores, warriors = parse_nmars_output(raw_output)

      if len(scores) < 2:
        continue
      battle_count += 1

      res_winner, res_loser = determine_winner(scores, warriors)
      winner = cont1 if res_winner == 1 else cont2
      loser = cont1 if res_loser == 1 else cont2

      if ARCHIVE_LIST[era]!=0 and random.randint(1,ARCHIVE_LIST[era])==1:
        #archive winner
        if VERBOSE:
            print("storing in archive")
        with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
          winlines = fw.readlines()
        with open(os.path.join("archive", f"{random.randint(1,9999)}.red"), "w") as fd:
          for line in winlines:
            fd.write(line)

      if UNARCHIVE_LIST[era]!=0 and random.randint(1,UNARCHIVE_LIST[era])==1:
        if VERBOSE:
            print("unarchiving")
        #replace loser with something from archive
        with open(os.path.join("archive", random.choice(os.listdir("archive")))) as fs:
          sourcelines = fs.readlines()
        #this is more involved. the archive is going to contain warriors from different arenas. which isn't
        #necessarily bad to get some crossover. A nano warrior would be workable, if inefficient in a normal core.
        #These are the tasks:
        #1. Truncate any too long
        #2. Pad any too short with DATs
        #3. Sanitize values
        #4. Try to be tolerant of working with other evolvers that may not space things exactly the same.
        fl = open(os.path.join(f"arena{arena}", f"{loser}.red"), "w")  # unarchived warrior destroys loser
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

      #the loser is destroyed and the winner can breed with any warrior in the arena
      with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
        winlines = fw.readlines()
      randomwarrior=str(random.randint(1, NUMWARRIORS))
      if VERBOSE:
          print("winner will breed with "+randomwarrior)
      fr = open(os.path.join(f"arena{arena}", f"{randomwarrior}.red"), "r")  # winner mates with random warrior
      ranlines = fr.readlines()
      fr.close()
      fl = open(os.path.join(f"arena{arena}", f"{loser}.red"), "w")  # winner destroys loser
      if random.randint(1, TRANSPOSITIONRATE_LIST[era])==1: #shuffle a warrior
        if VERBOSE:
            print("Transposition")
        for i in range(1, random.randint(1, int((WARLEN_LIST[arena]+1)/2))):
          fromline=random.randint(0,WARLEN_LIST[arena]-1)
          toline=random.randint(0,WARLEN_LIST[arena]-1)
          if random.randint(1,2)==1: #either shuffle the winner with itself or shuffle loser with itself
            templine=winlines[toline]
            winlines[toline]=winlines[fromline]
            winlines[fromline]=templine
          else:
            templine=ranlines[toline]
            ranlines[toline]=ranlines[fromline]
            ranlines[fromline]=templine
      if PREFER_WINNER_LIST[era]==True:
        pickingfrom=1 #if start picking from the winning warrior, more chance of winning genes passed on.
      else:
        pickingfrom=random.randint(1,2)

      magic_number = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
      for i in range(0, WARLEN_LIST[arena]):
        #first, pick an instruction from either parent, even if
        #it will get overwritten by a nabbed or random instruction
        if random.randint(1,CROSSOVERRATE_LIST[era])==1:
          if pickingfrom==1:
            pickingfrom=2
          else:
            pickingfrom=1

        if pickingfrom==1:
          templine=(winlines[i])
        else:
          templine=(ranlines[i])

        chosen_marble=random.choice(bag)
        if chosen_marble==Marble.MAJOR_MUTATION: #completely random
          if VERBOSE:
              print("Major mutation")
          num1 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
          num2 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
          templine=random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+ \
                   str(num1)+","+random.choice(INSTR_MODES)+str(num2)+"\n"
        elif chosen_marble==Marble.NAB_INSTRUCTION and (LAST_ARENA!=0):
          #nab instruction from another arena. Doesn't make sense if not multiple arenas
          donor_arena=random.randint(0, LAST_ARENA)
          while (donor_arena==arena):
            donor_arena=random.randint(0, LAST_ARENA)
          if VERBOSE:
              print("Nab instruction from arena " + str(donor_arena))
          donor_file = os.path.join(f"arena{donor_arena}", f"{random.randint(1, NUMWARRIORS)}.red")
          with open(donor_file, 'r') as f:
              templine = random.choice(f.readlines())
        elif chosen_marble==Marble.MINOR_MUTATION: #modifies one aspect of instruction
          if VERBOSE:
              print("Minor mutation")
          splitline=re.split(r'[ \.,\n]', templine)
          r=random.randint(1,6)
          if r==1:
            splitline[0]=random.choice(INSTR_SET)
          elif r==2:
            splitline[1]=random.choice(INSTR_MODIF)
          elif r==3:
            splitline[2]=random.choice(INSTR_MODES)+splitline[2][1:]
          elif r==4:
            num1 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
            splitline[2]=splitline[2][0:1]+str(num1)
          elif r==5:
            splitline[3]=random.choice(INSTR_MODES)+splitline[3][1:]
          elif r==6:
            num1 = weighted_random_number(CORESIZE_LIST[arena], WARLEN_LIST[arena])
            splitline[3]=splitline[3][0:1]+str(num1)
          templine=splitline[0]+"."+splitline[1]+" "+splitline[2]+","+splitline[3]+"\n"
        elif chosen_marble==Marble.MICRO_MUTATION: #modifies one number by +1 or -1
          if VERBOSE:
              print ("Micro mutation")
          splitline=re.split(r'[ \.,\n]', templine)
          r=random.randint(1,2)
          if r==1:
            num1=int(splitline[2][1:])
            if random.randint(1,2)==1:
              num1=num1+1
            else:
              num1=num1-1
            splitline[2]=splitline[2][0:1]+str(num1)
          else:
            num1=int(splitline[3][1:])
            if random.randint(1,2)==1:
              num1=num1+1
            else:
              num1=num1-1
            splitline[3]=splitline[3][0:1]+str(num1)
          templine=splitline[0]+"."+splitline[1]+" "+splitline[2]+","+splitline[3]+"\n"
        elif chosen_marble==Marble.INSTRUCTION_LIBRARY and LIBRARY_PATH and os.path.exists(LIBRARY_PATH):
          if VERBOSE:
              print("Instruction library")
          with open(LIBRARY_PATH, 'r') as f:
              templine = random.choice(f.readlines())
        elif chosen_marble==Marble.MAGIC_NUMBER_MUTATION:
          if VERBOSE:
              print ("Magic number mutation")
          splitline=re.split(r'[ \.,\n]', templine)
          r=random.randint(1,2)
          if r==1:
            splitline[2]=splitline[2][0:1]+str(magic_number)
          else:
            splitline[3]=splitline[3][0:1]+str(magic_number)
          templine=splitline[0]+"."+splitline[1]+" "+splitline[2]+","+splitline[3]+"\n"

        templine = normalize_instruction(templine, CORESIZE_LIST[arena], SANITIZE_LIST[arena])
        fl.write(templine)
        magic_number=magic_number-1

      fl.close()
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
