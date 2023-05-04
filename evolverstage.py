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

#size, cycles, processes, length, distance

##archived 0-3 Global Masters
## 0 GM 1           8000,  80000,    64, 100, 100
## 1 GM 2            160,   1600,   160,   6,   6
## 2 GM 3           8000,  80000,  8000,  80,  80 #and use SANITIZE 9
## 3 GM 4            800,   8000,     4,  20,  20
##

# 0 Nano            80,    800,    80,   5,   5 
# 1 Tiny           800,   8000,   800,  20,  20
# 2 Tiny LP        800,   8000,     8,  50,  50
# 3 94 Medium P   8000,  80000,    64, 100, 100
# 4 94/Std/NOP    8000,  80000,  8000, 100, 100
# 5 94 LP         8000,  80000,     8, 100, 100
# 6 Tourney       8192, 100000,  8000, 300, 300
# 7 Experimental 55440, 500000, 10000, 200, 200

#Python starts lists at 0, so I decided not to fight it.
LASTARENA=7 #A LASTARENA of 7 means you are running 8 arenas
CORESIZE_LIST=[80,800,800,8000,8000,8000,8192,55440]
SANITIZE_LIST=[80,800,800,8000,8000,8000,8192,55440] #usually the same as above but may be needed for arenas like Global Masters Round 3.
CYCLES_LIST=[800,8000,8000,80000,80000,80000,100000,500000]
PROCESSES_LIST=[80,800,8,64,8000,8,8000,10000]
WARLEN_LIST=[5,20,50,100,100,100,300,200]
WARDISTANCE_LIST=[5,20,50,100,100,100,300,200]

NUMWARRIORS=500
ALREADYSEEDED=True ################# Set to False on first or it will not work.

CLOCK_TIME=24.0 #actual wall clock time in hours you want to take
FINAL_ERA_ONLY=False #if True, skip the first two eras and go straight to the last one(i.e. if you want to continue fine-tuning where you left off)
                     #Or you're doing other research into the parameters and don't want them changing.

#Five strategies for mutating a single instruction. Think of it like a bag of marbles of six different colours, and a different number of each colour.
NOTHING_LIST=[10,18,27] #one of the colours of marbles will do nothing to the instruction
RANDOM_LIST=[2,1,1] #This colour of marbles will create a completely random instruction.
NAB_LIST=[4,4,2] #This will nab an instruction from a different arena. (Set to 0 if you are only running one arena.)
MINI_MUT_LIST=[3,4,2] #This will do a mini mutation. (One part of the instruction replaced with something random.)
MICRO_MUT_LIST=[3,4,3] #This will do a micro mutation. (One of the numbers in the instruction increased or decreased by 1.)
LIBRARY_LIST=[6,2,1] #This will grab an instruction from the instruction library (not included). (Set to 0 if you haven't made a library.)
MAGIC_NUMBER_LIST=[3,3,2] #This will replace a constant with the magic number (chosen at beginning of warrior)

#my intuition is that at first, unarchiving should be rare:
#-if sharing archive with other runs, will allow unique adaptations to optimize before turning optimized warriors loose
#later on, unarchiving should be more common:
#-plenty of archived warriors to cycle through
ARCHIVE_LIST=[2000,3000,3000]
UNARCHIVE_LIST=[3000,2000,1000]


#******* Not included with distribution. You do not need to use this. ***********
LIBRARY_PATH="" #instructions to pull from. Maybe a previous evolution run, maybe one or more hand-written warriors.
#one instruction per line. Just assembled instructions, nothing else. If multiple warriors, just concatenated with no breaks.


CROSSOVERRATE_LIST=[10,2,5] # 1 in this chance of switching to picking lines from other warrior, per instruction
TRANSPOSITIONRATE_LIST=[10,12,20] # 1 in this chance of swapping location of multiple instructions, per warrior

BATTLEROUNDS_LIST=[1,20,100]
PREFER_WINNER_LIST=[True, False, False]

#Biasing toward more viable warriors. Most popular instructions more likely.
INSTR_SET=['MOV','MOV','MOV','MOV','MOV','MOV','MOV','MOV','MOV','MOV','SPL','SPL','SPL','SPL','SPL','DJN','DJN','DJN','DJN','ADD','SUB','MUL','DIV','MOD','JMP','JMZ','CMP']
INSTR_MODES=['#','$','*','@','{','<','}','>']
INSTR_MODIF=['A','B','AB','BA','F','X','I']

#custom function, Python modulo doesn't work how we want with negative numbers
def coremod(x,y):
  if x>0:
    numsign=1
  elif x<0:
    numsign=-1
  else:
    numsign=0
  x=abs(x)
  remainder=x%y
  return remainder*numsign

def corenorm(x,y):
  if x>y//2:
    return(-(y-x))
  if x<=-(y//2):
    return((y+x))
  return(x)

if ALREADYSEEDED==False: 
  print("Seeding")
  os.mkdir("archive")
  for arena in range (0,LASTARENA+1):
    os.mkdir("arena"+str(arena))
    for i in range(1, NUMWARRIORS+1):
      f=open("arena"+str(arena)+"\\"+str(i)+".red", "w") 
      for j in range(1, WARLEN_LIST[arena]+1):
        #Biasing toward more viable warriors: 3 in 4 chance of choosing an address within the warrior. Same bias in mutation.     
        if random.randint(1,4)==1:
          num1=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num1=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        if random.randint(1,4)==1:
          num2=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num2=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        f.write(random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+str(corenorm(coremod(num1,SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+","+random.choice(INSTR_MODES)+str(corenorm(coremod(num2,SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+"\n")
      f.close()

starttime=time.time() #time in seconds
era=-1

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
    print("************** Switching from era "+str(prevera+1)+" to "+str(era+1)+ " *******************")
    bag=[]
    bag.extend([0]* NOTHING_LIST[era])
    bag.extend([1]* RANDOM_LIST[era])
    bag.extend([2]* NAB_LIST[era])
    bag.extend([3]* MINI_MUT_LIST[era])
    bag.extend([4]* MICRO_MUT_LIST[era])
    bag.extend([5]* LIBRARY_LIST[era])
    bag.extend([6]* MAGIC_NUMBER_LIST[era])
    
  print ("{0:.2f}".format(CLOCK_TIME-runtime_in_hours) +" hours remaining ({0:.2f}%".format(runtime_in_hours/CLOCK_TIME*100)+" complete) Era: "+str(era+1))
  
  #in a random arena
  arena=random.randint(0, LASTARENA)
  #two random warriors
  while(True): #no self fights
    cont1=random.randint(1, NUMWARRIORS)
    cont2=random.randint(1, NUMWARRIORS)
    if cont1!=cont2:
      break;
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
  cmdline="nmars.exe arena"+str(arena)+"\\"+str(cont1)+".red arena"+str(arena)+"\\"+str(cont2)+".red -s "+str(CORESIZE_LIST[arena])+" -c "+str(CYCLES_LIST[arena])+" -p "+str(PROCESSES_LIST[arena])+" -l "+str(WARLEN_LIST[arena])+" -d "+str(WARDISTANCE_LIST[arena])+" -r "+str(BATTLEROUNDS_LIST[era])+" > output.txt"
  print(cmdline)
  os.system(cmdline)
  scores=[]
  warriors=[]
  #note nMars will sort by score regardless of the order in the command-line, so match up score with warrior
  with open('output.txt', 'r') as f:
    for line in f:
      if "scores" in line:
        print(line.strip())
        splittedline=line.split()
        scores.append( int(splittedline [4]))
        warriors.append( int(splittedline [0]))

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
     

  if random.randint(1,ARCHIVE_LIST[era])==1:
    #archive winner
    print("storing in archive")
    fw=open("arena"+str(arena)+"\\"+str(winner)+".red", "r")
    winnerraw=fw.read() #don't need to process it, just store as is
    fw.close()
    fd=open("archive\\"+str(random.randint(1,9999))+".red", "w")
    fd.write(winnerraw)
    fd.close()

  if random.randint(1,UNARCHIVE_LIST[era])==1:
    print("unarchiving")
    #replace loser with something from archive
    fs=open("archive\\"+random.choice(os.listdir("archive\\")))
    sourcelines=fs.readlines()
    fs.close()
    #this is more involved. the archive is going to contain warriors from different arenas. which isn't necessarily bad to get some crossover. A nano warrior would be workable,if
    #inefficient in a normal core. These are the tasks:
    #1. Truncate any too long
    #2. Pad any too short with DATs
    #3. Sanitize values
    #4. Try to be tolerant of working with other evolvers that may not space things exactly the same.
    fl=open("arena"+str(arena)+"\\"+str(loser)+".red", "w") #unarchived warrior destroys loser
    countoflines=0
    for line in sourcelines:
      countoflines=countoflines+1
      if countoflines>WARLEN_LIST[arena]:
        break
      line=line.replace('  ',' ').replace('START','').replace(', ',',').strip()
      splitline=re.split('[ \.,\n]', line)
      line=splitline[0]+"."+splitline[1]+" "+splitline[2][0:1]+str(corenorm(coremod(int(splitline[2][1:]),SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+","+splitline[3][0:1]+str(corenorm(coremod(int(splitline[3][1:]),SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+"\n"
      fl.write(line)
    while countoflines<WARLEN_LIST[arena]:
      countoflines=countoflines+1
      fl.write('DAT.F $0,$0\n')
    fl.close()
    continue #out of while (loser replaced by archive, no point breeding)
    
  #the loser is destroyed and the winner can breed with any warrior in the arena  
  fw=open("arena"+str(arena)+"\\"+str(winner)+".red", "r")
  winlines=fw.readlines()
  fw.close()
  randomwarrior=str(random.randint(1, NUMWARRIORS))
  print("winner will breed with "+randomwarrior)
  fr=open("arena"+str(arena)+"\\"+randomwarrior+".red", "r") #winner mates with random warrior
  ranlines=fr.readlines()
  fr.close()
  fl=open("arena"+str(arena)+"\\"+str(loser)+".red", "w") #winner destroys loser
    
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
    
  if random.randint(1,4)==1:
    magic_number=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
  else:
    magic_number=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])

  for i in range(0, WARLEN_LIST[arena]):
    #first, pick an instruction from either parent, even if it will get overwritten by a nabbed or random instruction
    if random.randint(1,CROSSOVERRATE_LIST[era])==1:
      if pickingfrom==1:
        pickingfrom=2
      else:
        pickingfrom=1

    if pickingfrom==1:
      templine=(winlines[i])
    else:
      templine=(ranlines[i])

    marble=random.choice(bag)  
    if marble==1: #a major mutation, completely random
      print("Major mutation")
      if random.randint(1,4)==1:
        num1=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
      else:
        num1=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
      if random.randint(1,4)==1:
        num2=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
      else:
        num2=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
      templine=random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+str(num1)+","+random.choice(INSTR_MODES)+str(num2)+"\n"
    elif (marble==2) and (LASTARENA!=0): #nab instruction from another arena. Doesn't make sense if not multiple arenas
      donor_arena=random.randint(0, LASTARENA)
      while (donor_arena==arena):
        donor_arena=random.randint(0, LASTARENA)
      print("Nab instruction from arena " + str(donor_arena))
      templine=random.choice(list(open("arena"+str(donor_arena)+"\\"+str(random.randint(1, NUMWARRIORS))+".red")))
    elif marble==3: #a minor mutation modifies one aspect of instruction
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
        
        if random.randint(1,4)==1:
          num1=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num1=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        splitline[2]=splitline[2][0:1]+str(num1)
      elif r==5:  
        splitline[3]=random.choice(INSTR_MODES)+splitline[3][1:]
      elif r==6:
        
        if random.randint(1,4)==1:
          num1=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num1=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        splitline[3]=splitline[3][0:1]+str(num1)
      templine=splitline[0]+"."+splitline[1]+" "+splitline[2]+","+splitline[3]+"\n"
    elif marble==4: #a micro mutation modifies one number by +1 or -1
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
    elif marble==5 and LIBRARY_PATH!="": #choose instruction from instruction library
      print("Instruction library")
      templine=random.choice(list(open(LIBRARY_PATH)))
    elif marble==6: #magic number mutation
      print ("Magic number mutation")
      splitline=re.split('[ \.,\n]', templine)
      r=random.randint(1,2)
      if r==1:
        splitline[2]=splitline[2][0:1]+str(magic_number)
      else:
        splitline[3]=splitline[3][0:1]+str(magic_number)
      templine=splitline[0]+"."+splitline[1]+" "+splitline[2]+","+splitline[3]+"\n"
      
    splitline=re.split('[ \.,\n]', templine)
    templine=splitline[0]+"."+splitline[1]+" "+splitline[2][0:1]+str(corenorm(coremod(int(splitline[2][1:]),SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+","+splitline[3][0:1]+str(corenorm(coremod(int(splitline[3][1:]),SANITIZE_LIST[arena]),CORESIZE_LIST[arena]))+"\n"
    fl.write(templine)      
    magic_number=magic_number-1  

  fl.close()
#  time.sleep(3) #uncomment this for simple proportion of sleep if you're using computer for something else

#experimental. detect if computer being used and yield to other processes.
#  while psutil.cpu_percent()>50: #I'm not sure what percentage of CPU usage to watch for. Probably depends from computer to computer and personal taste.
#    print("High CPU Usage. Pausing for 3 seconds.")
#    time.sleep(3)
