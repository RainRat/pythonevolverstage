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

#size, cycles, processes, length, distance
# 0-3 Global Masters
# 0 GM 1           8000,  80000,    64, 100, 100
# 1 GM 2            160,   1600,   160,   6,   6
# 2 GM 3           8000,  80000,  8000,  80,  80 #and use SANITIZE 9
# 3 GM 4            800,   8000,     4,  20,  20
##
# 4 Nano             80,    800,    80,   5,   5 
# 5 Tiny            800,   8000,   800,  20,  20
# 6 Tiny LP         800,   8000,     8,  50,  50
# 7 94 Medium P    8000,  80000,    64, 100, 100
# 8 94/Standard    8000,  80000,  8000, 100, 100
# 9 94 NOP         8000,  80000,  8000, 100, 100 #same as above (consider it putting more toward most popular hills, or just close the gap if you like)
# 10 94 LP         8000,  80000,     8, 100, 100
# 11 Tourney       8192, 100000,  8000, 300, 300
# 12 Experimental 55440, 500000, 10000, 200, 200
#Python starts lists at 0, so I decided not to fight it.
LASTARENA=3 #A LASTARENA of 12 means you are running 13 arenas
CORESIZE_LIST=[8000,160,8000,800,80,800,800,8000,8000,8000,8000,8192,55440,8000]
SANITIZE_LIST=[8000,160,   9,800,80,800,800,8000,8000,8000,8000,8192,55440,8000] #needed for Global Masters Round 3. Also makes code look better if from another arena
CYCLES_LIST=[80000,1600,80000,8000,800,8000,8000,80000,80000,80000,80000,100000,500000,80000]
PROCESSES_LIST=[64,160,8000,4,80,800,8,64,8000,8000,8,8000,10000,80]
WARLEN_LIST=[100,6,80,20,5,20,50,100,100,100,100,300,200,400]
WARDISTANCE_LIST=[100,6,80,20,5,20,50,100,100,100,100,300,200,4000]

NUMWARRIORS=500
ALREADYSEEDED=True ################# Set to False on first or it will not work.

CLOCK_TIME=24.0 #actual wall clock time in hours you want to take
FINAL_ERA_ONLY=False #if True, skip the first two eras and go straight to the last one(ie. if you want to continue fine-tuning where you left off)
                     #Or you're doing other research into the parameters and don't want them changing.
MUT_RATE_LIST=[8,16,24] # 1 in this chance of mutation, per instruction
MINI_MUT_RATE_LIST=[4,6,8]  # 1 in this chance of minor mutation, per instruction
CROSSOVERRATE_LIST=[10,2,8] # 1 in this chance of switching to picking lines from other warrior, per instruction
TRANSPOSITIONRATE_LIST=[10,12,20] # 1 in this chance of swapping location of multiple instructions, per warrior
BATTLEROUNDS_LIST=[1,20,100]
PREFER_WINNER_LIST=[True, False, False]

#Biasing toward more viable warriors. Most popular instructions more likely.
INSTR_SET=['MOV','MOV','MOV','MOV','SPL','SPL','DJN','DJN','ADD','SUB','MUL','DIV','MOD','JMP','JMZ','CMP']
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

if ALREADYSEEDED==False: 
  print("Seeding")
  for q in range (0,LASTARENA+1):
    os.mkdir("arena"+str(q))
    for i in range(1, NUMWARRIORS+1):
      f=open("arena"+str(q)+"\\"+str(i)+".red", "w") 
      for j in range(1, WARLEN_LIST[q]+1):
        #Biasing toward more viable warriors: 3 in 4 chance of choosing an address within the warrior. Same bias in mutation.     
        if random.randint(1,4)==1:
          num1=random.randint(-CORESIZE_LIST[q],CORESIZE_LIST[q])
        else:
          num1=random.randint(-WARLEN_LIST[q],WARLEN_LIST[q])
        if random.randint(1,4)==1:
          num2=random.randint(-CORESIZE_LIST[q],CORESIZE_LIST[q])
        else:
          num2=random.randint(-WARLEN_LIST[q],WARLEN_LIST[q])
        f.write(random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+str(num1)+","+random.choice(INSTR_MODES)+str(num2)+"\n")
      f.close()

starttime=time.time() #time in seconds
 
while(True):
  #before we do anything, determine which era we are in.
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

    for i in range(1, random.randint(1, int(WARLEN_LIST[arena]/2))):
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

  for i in range(0, WARLEN_LIST[arena]):
    if random.randint(1,MUT_RATE_LIST[era])==1: #a major mutation can either be completely random, or pick a instruction from any arena
      if random.randint(1,2)==1: #1= total random, 2=picked from instruction library
        
        if random.randint(1,4)==1:
          num1=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num1=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        if random.randint(1,4)==1:
          num2=random.randint(-CORESIZE_LIST[arena],CORESIZE_LIST[arena])
        else:
          num2=random.randint(-WARLEN_LIST[arena],WARLEN_LIST[arena])
        to_emit=random.choice(INSTR_SET)+"."+random.choice(INSTR_MODIF)+" "+random.choice(INSTR_MODES)+str(num1)+","+random.choice(INSTR_MODES)+str(num2)+"\n"
      else:
        donor_arena=random.randint(0, LASTARENA)
        while donor_arena==arena:
          donor_arena=random.randint(0, LASTARENA)
        print("nab instruction from arena " + str(donor_arena))
        to_emit=random.choice(list(open("arena"+str(donor_arena)+"\\"+str(random.randint(1, NUMWARRIORS))+".red")))
    else:
      if random.randint(1,CROSSOVERRATE_LIST[era])==1:
        if pickingfrom==1:
          pickingfrom=2
        else:
          pickingfrom=1

      if pickingfrom==1:
        templine=(winlines[i])
      else:
        templine=(ranlines[i])

      if random.randint(1,MINI_MUT_RATE_LIST[era])==1: #a minor mutation modifies one aspect of instruction
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
      to_emit=templine
      
    splitline=re.split('[ \.,\n]', to_emit)
    to_emit=splitline[0]+"."+splitline[1]+" "+splitline[2][0:1]+str(coremod(int(splitline[2][1:]),SANITIZE_LIST[arena]))+","+splitline[3][0:1]+str(coremod(int(splitline[3][1:]),SANITIZE_LIST[arena]))+"\n"
    if to_emit[-1]!="\n":
      to_emit=to_emit+"\n"
    fl.write(to_emit)      
  fl.close()
  #time.sleep(5) #optional sleep if still using computer for other things
