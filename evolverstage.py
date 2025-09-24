import random
import os
import time
#import psutil #Not currently active. See bottom of code for how it could be used.
import configparser
import subprocess
from enum import Enum
import csv
import ctypes
import platform
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class EvolverConfig:
    battle_engine: str
    last_arena: int
    coresize_list: list[int]
    sanitize_list: list[int]
    cycles_list: list[int]
    processes_list: list[int]
    warlen_list: list[int]
    wardistance_list: list[int]
    numwarriors: int
    alreadyseeded: bool
    clock_time: float
    battle_log_file: Optional[str]
    final_era_only: bool
    nothing_list: list[int]
    random_list: list[int]
    nab_list: list[int]
    mini_mut_list: list[int]
    micro_mut_list: list[int]
    library_list: list[int]
    magic_number_list: list[int]
    archive_list: list[int]
    unarchive_list: list[int]
    library_path: Optional[str]
    crossoverrate_list: list[int]
    transpositionrate_list: list[int]
    battlerounds_list: list[int]
    prefer_winner_list: list[bool]
    instr_set: list[str]
    instr_modes: list[str]
    instr_modif: list[str]


def load_configuration(path: str) -> EvolverConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file '{path}' not found")

    def _read_config(key: str, data_type: str = 'int', default=None):
        value = parser['DEFAULT'].get(key, fallback=default)
        if value in (None, ''):
            return default

        data_type_mapping = {
            'int': int,
            'int_list': lambda x: [int(i) for i in x.split(',')],
            'bool_list': lambda x: [s.strip().lower() == 'true' for s in x.split(',') if s.strip()],
            'string_list': lambda x: [i.strip() for i in x.split(',') if i.strip()],
            'bool': lambda x: parser['DEFAULT'].getboolean(key, fallback=default),
            'float': float,
        }
        return data_type_mapping.get(data_type, lambda x: x.strip() or None)(value)

    return EvolverConfig(
        battle_engine=_read_config('BATTLE_ENGINE', data_type='string', default='external') or 'external',
        last_arena=_read_config('LAST_ARENA', data_type='int'),
        coresize_list=_read_config('CORESIZE_LIST', data_type='int_list') or [],
        sanitize_list=_read_config('SANITIZE_LIST', data_type='int_list') or [],
        cycles_list=_read_config('CYCLES_LIST', data_type='int_list') or [],
        processes_list=_read_config('PROCESSES_LIST', data_type='int_list') or [],
        warlen_list=_read_config('WARLEN_LIST', data_type='int_list') or [],
        wardistance_list=_read_config('WARDISTANCE_LIST', data_type='int_list') or [],
        numwarriors=_read_config('NUMWARRIORS', data_type='int'),
        alreadyseeded=_read_config('ALREADYSEEDED', data_type='bool'),
        clock_time=_read_config('CLOCK_TIME', data_type='float'),
        battle_log_file=_read_config('BATTLE_LOG_FILE', data_type='string'),
        final_era_only=_read_config('FINAL_ERA_ONLY', data_type='bool'),
        nothing_list=_read_config('NOTHING_LIST', data_type='int_list') or [],
        random_list=_read_config('RANDOM_LIST', data_type='int_list') or [],
        nab_list=_read_config('NAB_LIST', data_type='int_list') or [],
        mini_mut_list=_read_config('MINI_MUT_LIST', data_type='int_list') or [],
        micro_mut_list=_read_config('MICRO_MUT_LIST', data_type='int_list') or [],
        library_list=_read_config('LIBRARY_LIST', data_type='int_list') or [],
        magic_number_list=_read_config('MAGIC_NUMBER_LIST', data_type='int_list') or [],
        archive_list=_read_config('ARCHIVE_LIST', data_type='int_list') or [],
        unarchive_list=_read_config('UNARCHIVE_LIST', data_type='int_list') or [],
        library_path=_read_config('LIBRARY_PATH', data_type='string'),
        crossoverrate_list=_read_config('CROSSOVERRATE_LIST', data_type='int_list') or [],
        transpositionrate_list=_read_config('TRANSPOSITIONRATE_LIST', data_type='int_list') or [],
        battlerounds_list=_read_config('BATTLEROUNDS_LIST', data_type='int_list') or [],
        prefer_winner_list=_read_config('PREFER_WINNER_LIST', data_type='bool_list') or [],
        instr_set=_read_config('INSTR_SET', data_type='string_list') or [],
        instr_modes=_read_config('INSTR_MODES', data_type='string_list') or [],
        instr_modif=_read_config('INSTR_MODIF', data_type='string_list') or [],
    )

class DataLogger:
    def __init__(self, filename):
        self.filename = filename
        self.fieldnames = ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']
    def log_data(self, **kwargs):
        if self.filename:
            with open(self.filename, 'a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames)
                if file.tell() == 0:
                    writer.writeheader()
                writer.writerow(kwargs)

class Marble(Enum):
  DO_NOTHING = 0
  MAJOR_MUTATION = 1
  NAB_INSTRUCTION = 2
  MINOR_MUTATION = 3
  MICRO_MUTATION = 4
  INSTRUCTION_LIBRARY = 5
  MAGIC_NUMBER_MUTATION = 6

# --- C++ Worker Library Loading ---
CPP_WORKER_LIB = None
try:
    lib_name = "redcode_worker.so"
    if platform.system() == "Windows":
        lib_name = "redcode_worker.dll"
    elif platform.system() == "Darwin":
        lib_name = "redcode_worker.dylib"

    lib_path = os.path.abspath(lib_name)
    CPP_WORKER_LIB = ctypes.CDLL(lib_path)

    CPP_WORKER_LIB.run_battle.argtypes = [
        ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int
    ]
    CPP_WORKER_LIB.run_battle.restype = ctypes.c_char_p
    print("Successfully loaded C++ Redcode worker.")
except Exception as e:
    print(f"Could not load C++ Redcode worker: {e}")
    print("Internal battle engine will not be available.")

def run_nmars_command(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
  try:
    '''
nMars reference
Rules:
  -r #      Rounds to play [1]
  -s #      Size of core [8000]
  -c #      Cycle until tie [80000]
  -p #      Max. processes [8000]
  -l #      Max. warrior length [100]
  -d #      Min. warriors distance
  -S #      Size of P-space [500]
  -f #      Fixed position series
  -xp       Disable P-space
    '''
    nmars_cmd = "nmars.exe" if os.name == "nt" else "nmars"
    args = {
        "-s": coresize,
        "-c": cycles,
        "-p": processes,
        "-l": warlen,
        "-d": wardistance,
        "-r": battlerounds,
    }
    cmd = [
        nmars_cmd,
        os.path.join(f"arena{arena}", f"{cont1}.red"),
        os.path.join(f"arena{arena}", f"{cont2}.red"),
    ]
    for flag, value in args.items():
        cmd.extend([flag, str(value)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
  except FileNotFoundError as e:
    print(f"Unable to run {nmars_cmd}: {e}")
  except subprocess.SubprocessError as e:
    print(f"An error occurred: {e}")
  return None

def run_internal_battle(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
    if not CPP_WORKER_LIB:
        print("C++ worker not available. Cannot run internal battle. Returning a draw.")
        return f"{cont1} 0 0 0 0 scores\n{cont2} 0 0 0 0 scores"

    try:
        # 1. Read warrior files
        w1_path = os.path.join(f"arena{arena}", f"{cont1}.red")
        w2_path = os.path.join(f"arena{arena}", f"{cont2}.red")
        with open(w1_path, 'r') as f:
            w1_code = f.read()
        with open(w2_path, 'r') as f:
            w2_code = f.read()

        # 2. Call the C++ function
        result_ptr = CPP_WORKER_LIB.run_battle(
            w1_code.encode('utf-8'),
            cont1,
            w2_code.encode('utf-8'),
            cont2,
            coresize,
            cycles,
            processes,
            wardistance,
            battlerounds
        )

        if not result_ptr:
            raise RuntimeError("C++ worker returned no result")

        # 3. Decode the result
        result_str = result_ptr.decode('utf-8')
        if result_str.strip().startswith("ERROR:"):
            raise RuntimeError(
                f"C++ worker reported an error: {result_str.strip()}"
            )
        return result_str

    except Exception as e:
        raise RuntimeError(
            f"An error occurred while running the internal battle: {e}"
        ) from e

config = load_configuration('settings.ini')

DEFAULT_MODE = '$'
DEFAULT_MODIFIER = 'F'
ADDRESSING_MODES = set(config.instr_modes) if config.instr_modes else set()
ADDRESSING_MODES.update({'$', '#', '@', '<', '>', '*', '{', '}'})

CANONICAL_SUPPORTED_OPCODES = {
    'DAT', 'MOV', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD',
    'JMP', 'JMZ', 'JMN', 'DJN', 'CMP', 'SNE', 'SLT', 'SPL', 'NOP',
}
OPCODE_ALIASES = {
    'SEQ': 'CMP',
}
SUPPORTED_OPCODES = CANONICAL_SUPPORTED_OPCODES | set(OPCODE_ALIASES)
UNSUPPORTED_OPCODES = {'LDP', 'STP'}


def canonicalize_opcode(opcode: str) -> str:
    return OPCODE_ALIASES.get(opcode, opcode)

GENERATION_OPCODE_POOL = []
_invalid_generation_opcodes = set()
if config.instr_set:
    for instr in config.instr_set:
        normalized = instr.strip().upper()
        if not normalized:
            continue
        canonical_opcode = OPCODE_ALIASES.get(normalized, normalized)
        if canonical_opcode in UNSUPPORTED_OPCODES or canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
            _invalid_generation_opcodes.add(normalized)
            continue
        GENERATION_OPCODE_POOL.append(canonical_opcode)
if _invalid_generation_opcodes:
    raise ValueError(
        "Unsupported opcodes specified in INSTR_SET: "
        + ', '.join(sorted(_invalid_generation_opcodes))
    )
del _invalid_generation_opcodes

def weighted_random_number(size, length):
    if random.randint(1,4)==1:
        return random.randint(-size, size)
    else:
        return random.randint(-length, length)

#custom function, Python modulo doesn't work how we want with negative numbers
def coremod(x, y):
    numsign = -1 if x < 0 else 1
    return (abs(x) % y) * numsign

def corenorm(x, y):
    return -(y - x) if x > y // 2 else (y + x) if x <= -(y // 2) else x


@dataclass
class RedcodeInstruction:
    opcode: str
    modifier: str = DEFAULT_MODIFIER
    a_mode: str = DEFAULT_MODE
    a_field: int = 0
    b_mode: str = DEFAULT_MODE
    b_field: int = 0
    label: Optional[str] = None

    def copy(self) -> "RedcodeInstruction":
        return RedcodeInstruction(
            opcode=self.opcode,
            modifier=self.modifier,
            a_mode=self.a_mode,
            a_field=self.a_field,
            b_mode=self.b_mode,
            b_field=self.b_field,
            label=self.label,
        )


def _tokenize_instruction(line: str):
    tokens = []
    current = []
    for ch in line:
        if ch.isspace():
            if current:
                tokens.append(''.join(current))
                current = []
        elif ch == ',':
            if current:
                tokens.append(''.join(current))
                current = []
            tokens.append(',')
        else:
            current.append(ch)
    if current:
        tokens.append(''.join(current))
    return tokens


def _split_opcode_token(token: str):
    parts = token.split('.', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return token, None


def _is_opcode_token(token: str) -> bool:
    opcode, _ = _split_opcode_token(token)
    opcode = opcode.upper()
    canonical_opcode = canonicalize_opcode(opcode)
    return (
        canonical_opcode in CANONICAL_SUPPORTED_OPCODES
        or canonical_opcode in UNSUPPORTED_OPCODES
    )


_INT_LITERAL_RE = re.compile(r'^[+-]?\d+$')


def _safe_int(value: str) -> int:
    value = value.strip()
    if not value:
        raise ValueError("Empty integer literal")
    if not _INT_LITERAL_RE.fullmatch(value):
        raise ValueError(f"Invalid integer literal: '{value}'")
    return int(value, 10)


def _ensure_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _safe_int(str(value))


def _parse_operand(operand: str, operand_name: str):
    operand = operand.strip()
    if not operand:
        raise ValueError(f"Missing {operand_name}-field operand")
    mode = operand[0]
    if mode in ADDRESSING_MODES:
        value_part = operand[1:]
    else:
        mode = DEFAULT_MODE
        value_part = operand
    if not value_part.strip():
        raise ValueError(f"Missing value for {operand_name}-field operand")
    try:
        value = _safe_int(value_part)
    except ValueError as exc:
        raise ValueError(
            f"Invalid {operand_name}-field operand '{operand}': {exc}"
        ) from exc
    return mode if mode else DEFAULT_MODE, value


def parse_redcode_instruction(line: str) -> Optional[RedcodeInstruction]:
    if not line:
        return None
    code_part = line.split(';', 1)[0].strip()
    if not code_part:
        return None
    tokens = _tokenize_instruction(code_part)
    if not tokens:
        return None

    label: Optional[str] = None
    idx = 0
    if len(tokens) >= 2 and not _is_opcode_token(tokens[0]) and _is_opcode_token(tokens[1]):
        label = tokens[0]
        idx = 1

    if idx >= len(tokens):
        return None

    opcode_token = tokens[idx]
    opcode_part, modifier_part = _split_opcode_token(opcode_token)
    opcode = opcode_part.upper()
    canonical_opcode = canonicalize_opcode(opcode)
    modifier = modifier_part.upper() if modifier_part else DEFAULT_MODIFIER
    idx += 1

    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{opcode}'")

    operands = []
    current_operand = ''
    while idx < len(tokens):
        tok = tokens[idx]
        idx += 1
        if tok == ',':
            operands.append(current_operand)
            current_operand = ''
        else:
            current_operand += tok
    if current_operand or (tokens and tokens[-1] == ','):
        operands.append(current_operand)

    if len(operands) < 2:
        raise ValueError(
            f"Instruction '{code_part}' is missing operands; expected two operands"
        )
    if len(operands) > 2:
        raise ValueError(
            f"Instruction '{code_part}' has too many operands; expected exactly two"
        )

    a_mode, a_field = _parse_operand(operands[0], 'A')
    b_mode, b_field = _parse_operand(operands[1], 'B')

    return RedcodeInstruction(
        opcode=canonical_opcode,
        modifier=modifier or DEFAULT_MODIFIER,
        a_mode=a_mode or DEFAULT_MODE,
        a_field=a_field,
        b_mode=b_mode or DEFAULT_MODE,
        b_field=b_field,
        label=label,
    )


def default_instruction() -> RedcodeInstruction:
    return RedcodeInstruction(
        opcode='DAT',
        modifier=DEFAULT_MODIFIER,
        a_mode=DEFAULT_MODE,
        a_field=0,
        b_mode=DEFAULT_MODE,
        b_field=0,
    )


def sanitize_instruction(instr: RedcodeInstruction, arena: int) -> RedcodeInstruction:
    sanitized = instr.copy()
    original_opcode = (sanitized.opcode or '').upper()
    canonical_opcode = canonicalize_opcode(original_opcode)
    sanitized.opcode = canonical_opcode
    sanitized.modifier = (sanitized.modifier or DEFAULT_MODIFIER).upper()
    if canonical_opcode in UNSUPPORTED_OPCODES:
        raise ValueError(f"Opcode '{original_opcode}' is not supported")
    if canonical_opcode not in CANONICAL_SUPPORTED_OPCODES:
        raise ValueError(f"Unknown opcode '{original_opcode}'")
    sanitized.a_mode = sanitized.a_mode if sanitized.a_mode in ADDRESSING_MODES else DEFAULT_MODE
    sanitized.b_mode = sanitized.b_mode if sanitized.b_mode in ADDRESSING_MODES else DEFAULT_MODE
    sanitized.a_field = corenorm(
        coremod(_ensure_int(sanitized.a_field), config.sanitize_list[arena]),
        config.coresize_list[arena],
    )
    sanitized.b_field = corenorm(
        coremod(_ensure_int(sanitized.b_field), config.sanitize_list[arena]),
        config.coresize_list[arena],
    )
    sanitized.label = None
    return sanitized


def format_redcode_instruction(instr: RedcodeInstruction) -> str:
    return (
        f"{instr.opcode}.{instr.modifier} "
        f"{instr.a_mode}{_ensure_int(instr.a_field)},"
        f"{instr.b_mode}{_ensure_int(instr.b_field)}\n"
    )


def instruction_to_line(instr: RedcodeInstruction, arena: int) -> str:
    return format_redcode_instruction(sanitize_instruction(instr, arena))


def parse_instruction_or_default(line: str) -> RedcodeInstruction:
    parsed = parse_redcode_instruction(line)
    return parsed if parsed else default_instruction()


def choose_random_opcode() -> str:
    if GENERATION_OPCODE_POOL:
        return random.choice(GENERATION_OPCODE_POOL)
    return 'DAT'


def choose_random_modifier() -> str:
    if config.instr_modif:
        return random.choice(config.instr_modif).upper()
    return DEFAULT_MODIFIER


def choose_random_mode() -> str:
    if config.instr_modes:
        return random.choice(config.instr_modes)
    return DEFAULT_MODE


def generate_random_instruction(arena: int) -> RedcodeInstruction:
    num1 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    num2 = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    return RedcodeInstruction(
        opcode=choose_random_opcode(),
        modifier=choose_random_modifier(),
        a_mode=choose_random_mode(),
        a_field=num1,
        b_mode=choose_random_mode(),
        b_field=num2,
    )

def create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.mkdir(directory)

if not config.alreadyseeded:
  print("Seeding")
  create_directory_if_not_exists("archive")
  for arena in range (0,config.last_arena+1):
    create_directory_if_not_exists(f"arena{arena}")
    for i in range(1, config.numwarriors+1):
      with open(os.path.join(f"arena{arena}", f"{i}.red"), "w") as f:
          for j in range(1, config.warlen_list[arena]+1):
            #Biasing toward more viable warriors: 3 in 4 chance of choosing an address within the warrior.
            #Same bias in mutation.
            instruction = generate_random_instruction(arena)
            f.write(instruction_to_line(instruction, arena))

starttime=time.time() #time in seconds
era=-1
data_logger = DataLogger(filename=config.battle_log_file)

while(True):
  #before we do anything, determine which era we are in.
  prevera=era
  curtime=time.time()
  runtime_in_hours=(curtime-starttime)/60/60
  era=0
  if runtime_in_hours>config.clock_time*(1/3):
    era=1
  if runtime_in_hours>config.clock_time*(2/3):
    era=2
  if runtime_in_hours>config.clock_time:
    quit()
  if config.final_era_only==True:
    era=2
  if era!=prevera:
    print(f"************** Switching from era {prevera + 1} to {era + 1} *******************")
    bag = [Marble.DO_NOTHING]*config.nothing_list[era] + [Marble.MAJOR_MUTATION]*config.random_list[era] + \
          [Marble.NAB_INSTRUCTION]*config.nab_list[era] + [Marble.MINOR_MUTATION]*config.mini_mut_list[era] + \
          [Marble.MICRO_MUTATION]*config.micro_mut_list[era] + [Marble.INSTRUCTION_LIBRARY]*config.library_list[era] + \
          [Marble.MAGIC_NUMBER_MUTATION]*config.magic_number_list[era]

  print ("{0:.2f}".format(config.clock_time-runtime_in_hours) + \
         " hours remaining ({0:.2f}%".format(runtime_in_hours/config.clock_time*100)+" complete) Era: "+str(era+1))

  #in a random arena
  arena=random.randint(0, config.last_arena)
  #two random warriors
  cont1 = random.randint(1, config.numwarriors)
  cont2 = cont1
  while cont2 == cont1: #no self fights
    cont2 = random.randint(1, config.numwarriors)
  if config.battle_engine == 'internal':
    raw_output = run_internal_battle(
      arena,
      cont1,
      cont2,
      config.coresize_list[arena],
      config.cycles_list[arena],
      config.processes_list[arena],
      config.warlen_list[arena],
      config.wardistance_list[arena],
      config.battlerounds_list[era],
    )
  else:
    raw_output = run_nmars_command(
      arena,
      cont1,
      cont2,
      config.coresize_list[arena],
      config.cycles_list[arena],
      config.processes_list[arena],
      config.warlen_list[arena],
      config.wardistance_list[arena],
      config.battlerounds_list[era],
    )
  if raw_output is None:
    raise RuntimeError("Battle engine returned no output")
  if isinstance(raw_output, bytes):
    raw_output = raw_output.decode('utf-8')
  raw_output_stripped = raw_output.strip()
  if raw_output_stripped.startswith("ERROR:"):
    raise RuntimeError(f"Battle engine reported an error: {raw_output_stripped}")
  scores=[]
  warriors=[]
  #note nMars will sort by score regardless of the order in the command-line, so match up score with warrior
  numline=0
  output = raw_output.splitlines()
  if not output:
    raise RuntimeError("Battle engine produced no output to parse")

  for line in output:
    numline=numline+1
    if "scores" in line:
      print(line.strip())
      splittedline=line.split()
      if len(splittedline) < 5:
        raise RuntimeError(f"Unexpected score line format: {line.strip()}")
      scores.append( int(splittedline [4]))
      warriors.append( int(splittedline [0]))
  if len(scores) < 2:
    raise RuntimeError("Battle engine output did not include scores for both warriors")
  print(numline)

  if scores[1]==scores[0]:
    print("draw") #in case of a draw, destroy one at random. we want attacking.
    if random.randint(1,2)==1:
      winner=warriors[1]
      loser=warriors[0]
    else:
      winner=warriors[0]
      loser=warriors[1]
  elif scores[1]>scores[0]:
    winner=warriors[1]
    loser=warriors[0]
  else:
    winner=warriors[0]
    loser=warriors[1]

  if config.archive_list[era]!=0 and random.randint(1,config.archive_list[era])==1:
    #archive winner
    print("storing in archive")
    with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
      winlines = fw.readlines()
    with open(os.path.join("archive", f"{random.randint(1,9999)}.red"), "w") as fd:
      for line in winlines:
        fd.write(line)

  if config.unarchive_list[era]!=0 and random.randint(1,config.unarchive_list[era])==1:
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
    instructions_written=0
    for line in sourcelines:
      instruction=parse_redcode_instruction(line)
      if instruction is None:
        continue
      fl.write(instruction_to_line(instruction, arena))
      instructions_written=instructions_written+1
      if instructions_written>=config.warlen_list[arena]:
        break
    while instructions_written<config.warlen_list[arena]:
      fl.write(instruction_to_line(default_instruction(), arena))
      instructions_written=instructions_written+1
    fl.close()
    continue #out of while (loser replaced by archive, no point breeding)
    
  #the loser is destroyed and the winner can breed with any warrior in the arena  
  with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
    winlines = fw.readlines()
  randomwarrior=str(random.randint(1, config.numwarriors))
  print("winner will breed with "+randomwarrior)
  fr = open(os.path.join(f"arena{arena}", f"{randomwarrior}.red"), "r")  # winner mates with random warrior
  ranlines = fr.readlines()
  fr.close()
  fl = open(os.path.join(f"arena{arena}", f"{loser}.red"), "w")  # winner destroys loser
  if random.randint(1, config.transpositionrate_list[era])==1: #shuffle a warrior
    print("Transposition")
    for i in range(1, random.randint(1, int((config.warlen_list[arena]+1)/2))):
      fromline=random.randint(0,config.warlen_list[arena]-1)
      toline=random.randint(0,config.warlen_list[arena]-1)
      if random.randint(1,2)==1: #either shuffle the winner with itself or shuffle loser with itself
        templine=winlines[toline]
        winlines[toline]=winlines[fromline]
        winlines[fromline]=templine
      else:
        templine=ranlines[toline]
        ranlines[toline]=ranlines[fromline]
        ranlines[fromline]=templine
  if config.prefer_winner_list[era]==True:
    pickingfrom=1 #if start picking from the winning warrior, more chance of winning genes passed on.
  else:
    pickingfrom=random.randint(1,2)

  magic_number = weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
  for i in range(0, config.warlen_list[arena]):
    #first, pick an instruction from either parent, even if
    #it will get overwritten by a nabbed or random instruction
    if random.randint(1,config.crossoverrate_list[era])==1:
      if pickingfrom==1:
        pickingfrom=2
      else:
        pickingfrom=1

    if pickingfrom==1:
      source_line=winlines[i] if i < len(winlines) else ''
    else:
      source_line=ranlines[i] if i < len(ranlines) else ''

    instruction=parse_instruction_or_default(source_line)
    chosen_marble=random.choice(bag)
    if chosen_marble==Marble.MAJOR_MUTATION: #completely random
      print("Major mutation")
      instruction=generate_random_instruction(arena)
    elif chosen_marble==Marble.NAB_INSTRUCTION and (config.last_arena!=0):
      #nab instruction from another arena. Doesn't make sense if not multiple arenas
      donor_arena=random.randint(0, config.last_arena)
      while (donor_arena==arena):
        donor_arena=random.randint(0, config.last_arena)
      print("Nab instruction from arena " + str(donor_arena))
      donor_file=os.path.join(f"arena{donor_arena}", f"{random.randint(1, config.numwarriors)}.red")
      with open(donor_file, "r") as donor_handle:
        donor_lines=donor_handle.readlines()
      if donor_lines:
        instruction=parse_instruction_or_default(random.choice(donor_lines))
      else:
        instruction=default_instruction()
    elif chosen_marble==Marble.MINOR_MUTATION: #modifies one aspect of instruction
      print("Minor mutation")
      r=random.randint(1,6)
      if r==1:
        instruction.opcode=choose_random_opcode()
      elif r==2:
        instruction.modifier=choose_random_modifier()
      elif r==3:
        instruction.a_mode=choose_random_mode()
      elif r==4:
        instruction.a_field=weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
      elif r==5:
        instruction.b_mode=choose_random_mode()
      elif r==6:
        instruction.b_field=weighted_random_number(config.coresize_list[arena], config.warlen_list[arena])
    elif chosen_marble==Marble.MICRO_MUTATION: #modifies one number by +1 or -1
      print ("Micro mutation")
      if random.randint(1,2)==1:
        current_value=_ensure_int(instruction.a_field)
        if random.randint(1,2)==1:
          current_value=current_value+1
        else:
          current_value=current_value-1
        instruction.a_field=current_value
      else:
        current_value=_ensure_int(instruction.b_field)
        if random.randint(1,2)==1:
          current_value=current_value+1
        else:
          current_value=current_value-1
        instruction.b_field=current_value
    elif chosen_marble==Marble.INSTRUCTION_LIBRARY and config.library_path and os.path.exists(config.library_path):
      print("Instruction library")
      with open(config.library_path, "r") as library_handle:
        library_lines=library_handle.readlines()
      if library_lines:
        instruction=parse_instruction_or_default(random.choice(library_lines))
      else:
        instruction=default_instruction()
    elif chosen_marble==Marble.MAGIC_NUMBER_MUTATION:
      print ("Magic number mutation")
      if random.randint(1,2)==1:
        instruction.a_field=magic_number
      else:
        instruction.b_field=magic_number

    fl.write(instruction_to_line(instruction, arena))
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
