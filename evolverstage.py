#For programmers familiar with Core War and Python. You will probably have to modify the code to do what you want.

'''
This program is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
'''

import random
import os
import re
import time
#import psutil #Not currently active. See bottom of code for how it could be used.
import argparse
import configparser
import subprocess
from enum import Enum
import csv

class DataLogger:
    """
    Logs battle results to a CSV file.
    """
    def __init__(self, filename):
        self.filename = filename
        self.fieldnames = ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']
    def log_data(self, **kwargs):
        """
        Writes a single row of data to the CSV file.
        Creates the file with a header row if it doesn't exist.
        """
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

def run_nmars_command(arena, cont1, cont2, coresize, cycles, processes, warlen, wardistance, battlerounds):
  """
  Runs the nMars simulator to battle two warriors.

  Constructs the command line arguments for nMars based on the arena settings
  and returns the output from the simulator.
  """
  try:
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
  except FileNotFoundError as e:
    print(f"Unable to run {nmars_cmd}: {e}")
  except subprocess.SubprocessError as e:
    print(f"An error occurred: {e}")
  return None

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

def weighted_random_number(size, length):
    """
    Returns a random number to use in an instruction field.

    Most of the time (75%), it returns a small number useful for
    self-references (within the warrior's length). Occasionally (25%),
    it returns a larger number to reach across the core.
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
    splitline = re.split('[ \.,\n]', instruction.strip())
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
    Reads the text output from nMars to find the scores and warrior IDs.
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
            print(line.strip())
            splittedline=line.split()
            # Ensure line has enough parts to avoid IndexError
            if len(splittedline) > 4:
                scores.append(int(splittedline[4]))
                warriors.append(int(splittedline[0]))
    print(numline)
    return scores, warriors

def determine_winner(scores, warriors):
    """
    Decides who won the battle based on scores.

    If it's a draw (scores are equal), a winner is picked randomly.
    This prevents stagnation by removing one warrior anyway.
    """
    winner = None
    loser = None
    if scores[1] == scores[0]:
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

def parse_arguments():
    parser = argparse.ArgumentParser(description="Core War Evolver")
    parser.add_argument('-n', '--numwarriors', type=int, help='Number of warriors per arena (overrides settings.ini)')
    parser.add_argument('-t', '--clock-time', type=float, help='Runtime in hours (overrides settings.ini)')
    parser.add_argument('-r', '--reseed', action='store_true', help='Force re-seeding (sets ALREADYSEEDED=False)')
    return parser.parse_args()

if __name__ == "__main__":
  args = parse_arguments()
  if args.numwarriors is not None:
      NUMWARRIORS = args.numwarriors
  if args.clock_time is not None:
      CLOCK_TIME = args.clock_time
  if args.reseed:
      ALREADYSEEDED = False

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
      print(f"************** Switching from era {prevera + 1} to {era + 1} *******************")
      bag = construct_marble_bag(era)

    print ("{0:.2f}".format(CLOCK_TIME-runtime_in_hours) + \
           " hours remaining ({0:.2f}%".format(runtime_in_hours/CLOCK_TIME*100)+" complete) Era: "+str(era+1))

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

    winner, loser = determine_winner(scores, warriors)

    if ARCHIVE_LIST[era]!=0 and random.randint(1,ARCHIVE_LIST[era])==1:
      #archive winner
      print("storing in archive")
      with open(os.path.join(f"arena{arena}", f"{winner}.red"), "r") as fw:
        winlines = fw.readlines()
      with open(os.path.join("archive", f"{random.randint(1,9999)}.red"), "w") as fd:
        for line in winlines:
          fd.write(line)

    if UNARCHIVE_LIST[era]!=0 and random.randint(1,UNARCHIVE_LIST[era])==1:
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
    print("winner will breed with "+randomwarrior)
    fr = open(os.path.join(f"arena{arena}", f"{randomwarrior}.red"), "r")  # winner mates with random warrior
    ranlines = fr.readlines()
    fr.close()
    fl = open(os.path.join(f"arena{arena}", f"{loser}.red"), "w")  # winner destroys loser
    if random.randint(1, TRANSPOSITIONRATE_LIST[era])==1: #shuffle a warrior
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
        print("Nab instruction from arena " + str(donor_arena))
        donor_file = os.path.join(f"arena{donor_arena}", f"{random.randint(1, NUMWARRIORS)}.red")
        templine = random.choice(list(open(donor_file)))
      elif chosen_marble==Marble.MINOR_MUTATION: #modifies one aspect of instruction
        print("Minor mutation")
        splitline=re.split('[ \.,\n]', templine)
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
        print ("Micro mutation")
        splitline=re.split('[ \.,\n]', templine)
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
        print("Instruction library")
        templine=random.choice(list(open(LIBRARY_PATH)))
      elif chosen_marble==Marble.MAGIC_NUMBER_MUTATION:
        print ("Magic number mutation")
        splitline=re.split('[ \.,\n]', templine)
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
