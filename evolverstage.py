# A Python-based Genetic Evolver for Core War
# This script manages the evolution, breeding, and battling of warriors across multiple arenas.

'''
Core War Evolver

A tool to evolve Redcode warriors using a genetic algorithm.
For license information, see LICENSE.md.

Usage:
  python evolverstage.py [COMMAND] [OPTIONS]

General Commands:
  --check, -c              Check if your setup and settings.ini are correct.
  --status, -s             Show progress, population sizes, and recent activity.
  --leaderboard, -l        Show top warriors based on their win streaks.
  --dump-config, -d        Show all current settings and exit.

Evolution:
  (no flags)               Start or continue evolution based on settings.ini.
  --restart                Force a fresh start (overwrites current warriors).
  --resume                 Force evolution to continue from existing warriors.

Battle Tools:
  --battle, -b W1 W2       Run one fight between two warriors (W1 and W2).
  --tournament, -t DIR     Run a tournament where every warrior in DIR fights everyone else.
  --benchmark, -m W DIR    Test warrior W against everyone in DIR to see how it ranks.

Utilities:
  --normalize, -n SRC      Clean and standardize a warrior's code or a whole folder (SRC).

Common Options:
  --arena, -a N            Use the rules (size, cycles, etc.) of arena N (default is 0).
  --output, -o DEST        Specify where to save results (for --normalize).
  --json                   Output status or leaderboard data in JSON format.
  --help, -h               Show this help message.

Examples:
  python evolverstage.py --check
  python evolverstage.py --battle warrior1.red warrior2.red --arena 1
  python evolverstage.py --benchmark my_warrior.red arena0/
  python evolverstage.py --normalize messy.red -o clean.red
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

def draw_progress_bar(percent, width=30):
    """Returns a string representing a progress bar."""
    if percent < 0: percent = 0
    if percent > 100: percent = 100
    filled_length = int(width * percent // 100)
    bar = '=' * filled_length + '-' * (width - filled_length)
    return f"[{Colors.GREEN}{bar}{Colors.ENDC}] {percent:6.2f}%"

def run_nmars_subprocess(cmd):
    """
    Executes the nmars command with the given arguments.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    except FileNotFoundError as e:
        print(f"Unable to run {cmd[0]}: {e}")
    except subprocess.SubprocessError as e:
        print(f"An error occurred: {e}")
    return None

def run_nmars_command(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
  """
  Runs the nMars simulator to battle two warriors.

  It builds the command string with all the rules for the specific arena (size, cycles, etc.)
  and returns the raw output from nMars, which contains the scores.
  """
  nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
  cmd = [
      nmars_cmd,
      os.path.join(f"arena{arena}", f"{cont1}.red"),
      os.path.join(f"arena{arena}", f"{cont2}.red"),
      "-s", str(coresize),
      "-c", str(cycles),
      "-p", str(processes),
      "-l", str(warlen),
      "-d", str(wardistance),
      "-r", str(battlerounds)
    ]
  return run_nmars_subprocess(cmd)

def construct_battle_command(file1, file2, arena_idx):
    """
    Constructs the nMars command for battling two specific files.
    """
    nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
    # Use the battlerounds from the last era (Optimization) as default for manual battles
    rounds = BATTLEROUNDS_LIST[-1] if BATTLEROUNDS_LIST else 100

    return [
        nmars_cmd,
        file1,
        file2,
        "-s", str(CORESIZE_LIST[arena_idx]),
        "-c", str(CYCLES_LIST[arena_idx]),
        "-p", str(PROCESSES_LIST[arena_idx]),
        "-l", str(WARLEN_LIST[arena_idx]),
        "-d", str(WARDISTANCE_LIST[arena_idx]),
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

def run_tournament(directory, arena_idx):
    """
    Runs a round-robin tournament between all .red files in the specified directory.
    """
    if arena_idx > LAST_ARENA:
        print(f"Error: Arena {arena_idx} does not exist (LAST_ARENA={LAST_ARENA})")
        return

    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' not found.")
        return

    files = [f for f in os.listdir(directory) if f.endswith('.red')]
    if len(files) < 2:
        print("Error: Need at least 2 .red files for a tournament.")
        return

    scores = {f: 0 for f in files}
    # Create absolute paths
    abs_files = [os.path.join(directory, f) for f in files]
    file_map = {os.path.join(directory, f): f for f in files}

    # Generate pairs
    pairs = list(itertools.combinations(abs_files, 2))
    total_battles = len(pairs)
    print(f"Tournament: {len(files)} warriors, {total_battles} battles.")
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
        print(f"Error: No .red files found in '{directory}'.")
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
            # Cleanup logic mirrored from unarchiving logic
            clean_line = line.replace('  ',' ').replace('START','').replace(', ',',').strip()
            # Basic check to skip empty lines or comments
            if not clean_line or clean_line.startswith(';'):
                continue

            try:
                normalized = normalize_instruction(clean_line, CORESIZE_LIST[arena_idx], SANITIZE_LIST[arena_idx])
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
    splitline = re.split(r'[ \.,\n]', instruction.strip())
    return splitline[0]+"."+splitline[1]+" "+splitline[2][0:1]+ \
           str(corenorm(coremod(int(splitline[2][1:]),sanitize_limit),coresize))+","+ \
           splitline[3][0:1]+str(corenorm(coremod(int(splitline[3][1:]),sanitize_limit), \
           coresize))+"\n"

def create_directory_if_not_exists(directory):
    """
    Creates a folder if it does not already exist.
    """
    if not os.path.exists(directory):
        os.mkdir(directory)

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
    winner = None
    loser = None
    if scores[1] == scores[0]:
        if VERBOSE:
            print("draw") #in case of a draw, destroy one at random. we want attacking.
        if random.randint(1, 2) == 1:
            winner = warriors[1]
            loser = warriors[0]
        else:
            winner = warriors[0]
            loser = warriors[1]
    elif scores[1] > scores[0]:
        winner = warriors[1]
        loser = warriors[0]
    else:
        winner = warriors[0]
        loser = warriors[1]
    return winner, loser

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

    print(f"{Colors.BOLD}{Colors.HEADER}Evolver Status Report{Colors.ENDC}")
    print("="*60)

    # Latest Activity
    log = data['latest_log']
    if log:
        try:
            summary = f"Era {int(log['era'])+1}, Arena {log['arena']}: Warrior {log['winner']} beat {log['loser']} ({log['score1']}-{log['score2']})"
            print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} {summary}")
        except (ValueError, KeyError):
            print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} {log}")
    else:
        print(f"{Colors.BOLD}Latest Activity:{Colors.ENDC} No battles recorded yet.")
    print("-" * 60)

    total_warriors = 0

    for arena in data['arenas']:
        i = arena['id']
        print(f"{Colors.BOLD}Arena {i}:{Colors.ENDC}")
        print(f"  Configuration: Size={arena['config']['size']}, Cycles={arena['config']['cycles']}, Processes={arena['config']['processes']}")

        if not arena['exists']:
            print(f"  {Colors.YELLOW}Status: Directory '{arena['directory']}' not found (Unseeded?){Colors.ENDC}")
            print("-" * 40)
            continue

        count = arena['population']
        total_warriors += count

        print(f"  Population:    {Colors.GREEN}{count} warriors{Colors.ENDC}")
        if count > 0:
            print(f"  Avg Length:    {arena['avg_length']:.1f} instructions (sampled)")
        print("-" * 40)

    # Archive
    print(f"{Colors.BOLD}Archive:{Colors.ENDC}")
    if data['archive']['exists']:
        print(f"  Contains {Colors.GREEN}{data['archive']['count']} warriors{Colors.ENDC}.")
    else:
        print(f"  {Colors.YELLOW}Directory 'archive' not found.{Colors.ENDC}")

    print("="*60)

def _get_arena_idx():
    """
    Helper to extract arena index from command line arguments.
    """
    arena_idx = 0
    if "--arena" in sys.argv or "-a" in sys.argv:
        if "--arena" in sys.argv:
            a_idx = sys.argv.index("--arena")
        else:
            a_idx = sys.argv.index("-a")

        if len(sys.argv) > a_idx + 1:
            arena_idx = int(sys.argv[a_idx+1])
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
            errors.append(f"{name} has {len(lst)} elements, expected at least {expected_length} (LAST_ARENA={LAST_ARENA})")

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
            errors.append(f"{name} has {len(lst)} elements, expected at least 3 (for eras 0, 1, 2)")

    # Check Executables
    nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
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
    print(__doc__)
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
    arena_idx = None
    if "--arena" in sys.argv or "-a" in sys.argv:
        try:
            a_idx = sys.argv.index("--arena") if "--arena" in sys.argv else sys.argv.index("-a")
            if len(sys.argv) > a_idx + 1:
                arena_idx = int(sys.argv[a_idx+1])
        except ValueError:
            pass

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

  if "--battle" in sys.argv or "-b" in sys.argv:
    try:
        if "--battle" in sys.argv:
            idx = sys.argv.index("--battle")
        else:
            idx = sys.argv.index("-b")

        if len(sys.argv) < idx + 3:
            print("Usage: --battle|-b <warrior1> <warrior2> [--arena|-a <N>]")
            sys.exit(1)

        w1 = sys.argv[idx+1]
        w2 = sys.argv[idx+2]

        arena_idx = _get_arena_idx()
        run_custom_battle(w1, w2, arena_idx)
        sys.exit(0)
    except ValueError:
        print("Invalid arguments.")
        sys.exit(1)

  if "--tournament" in sys.argv or "-t" in sys.argv:
      try:
          if "--tournament" in sys.argv:
              idx = sys.argv.index("--tournament")
          else:
              idx = sys.argv.index("-t")

          if len(sys.argv) < idx + 2:
              print("Usage: --tournament|-t <directory> [--arena|-a <N>]")
              sys.exit(1)

          directory = sys.argv[idx+1]

          arena_idx = _get_arena_idx()
          run_tournament(directory, arena_idx)
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

          warrior_file = sys.argv[idx+1]
          directory = sys.argv[idx+2]

          arena_idx = _get_arena_idx()
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

          warrior_file = sys.argv[idx+1]

          arena_idx = _get_arena_idx()
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

  if ALREADYSEEDED==False:
    print("Seeding")
    create_directory_if_not_exists("archive")
    for arena in range (0,LAST_ARENA+1):
      create_directory_if_not_exists(f"arena{arena}")
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
      quit()
    if FINAL_ERA_ONLY==True:
      era=2
    if era!=prevera:
      print(f"\n{Colors.YELLOW}************** Switching from era {prevera + 1} to {era + 1} *******************{Colors.ENDC}")
      bag = construct_marble_bag(era)

    remaining_seconds = (CLOCK_TIME - runtime_in_hours) * 3600
    remaining_str = format_time_remaining(remaining_seconds)
    progress_percent = (runtime_in_hours / CLOCK_TIME) * 100
    bar_str = draw_progress_bar(progress_percent)
    status_line = f"{remaining_str} remaining {bar_str} Era: {era+1}"
    print(f"{status_line:<80}", end='\r')

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
        countoflines=countoflines+1
        if countoflines>WARLEN_LIST[arena]:
          break
        line=line.replace('  ',' ').replace('START','').replace(', ',',').strip()
        line = normalize_instruction(line, CORESIZE_LIST[arena], SANITIZE_LIST[arena])
        fl.write(line)
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
        templine = random.choice(list(open(donor_file)))
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
        templine=random.choice(list(open(LIBRARY_PATH)))
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
  data_logger.log_data(era=era, arena=arena, winner=winner, loser=loser, score1=scores[0], score2=scores[1], \
                       bred_with=randomwarrior)

#  time.sleep(3) #uncomment this for simple proportion of sleep if you're using computer for something else

#experimental. detect if computer being used and yield to other processes.
#  while psutil.cpu_percent()>30: #I'm not sure what percentage of CPU usage to watch for. Probably depends
                                  # from computer to computer and personal taste.
#    print("High CPU Usage. Pausing for 3 seconds.")
#    time.sleep(3)
