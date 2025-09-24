# Python Core War Evolver

An Evolver for Core War, written in Python. You don't need to know Redcode (the language used in Core War).

A genetic algorithm will pit the warriors against each other, then breed the winner, with some random mutation.

If you have a suggestion, submit a pull request. I put it on Github to encourage contributions.

## Usage:

For all of these, modify the constants in settings.ini.

1. Edit the ARENA lists to contain the parameters of the competitions you want to compete in. If you just want to compete in one arena, you have lists of length 1.
2. Set ALREADYSEEDED to False. If you interrupt it and want to resume, set it to True.
3. Choose how much actual wall clock time (in hours) you plan to run the project for and modify CLOCK_TIME
4. python evolverstage.py
5. When done, out of the warriors in each arena, you will need to pick which is actually the best. CoreWin in round robin mode can find the best ones, or use a benchmarking tool.

## Special Features:

1. Evolve warriors to compete in multiple arenas at once. This is beneficial because useful instructions can be nabbed by warriors for use in other arenas.
	- A Sanitizer will chop the numerical values down to something that makes sense in the smaller core if needed. This was also used in Round 3 of the Global Masters Tournament.
2. Bias towards picking more useful instructions. (MOV, SPL, DJN most likely)
3. Bias towards picking small numbers (likely inside the warrior) (3 out of 4 chance).
4. Eras and wall clock time. Before you start, you decide how long you want to run the evolver for. Let's say 24 hours. It'll divide this time into 3 eras.
	- Exploration (single cell analogy)
		The primary activity of this phase is warriors reproducing themselves with mutation. One round of battle determines the winner. Single-celled organisms die easily but there will be many near-clones. A random mate is still selected but the offspring will start with instructions from the winner and there's a lower chance of switching to getting instructions from the other warrior.
	- Breeding (multicellular analogy)
		The primary activity of this phase is to use breeding to combine features of different warriors. They will fight for more rounds before declaring the winner. How breeding works: The winner, and a random warrior, are loaded side by side. Starting from a random warrior from those two, instructions are copied into the new warrior. Each instruction, there's a chance of switching to reading instructions from the other warrior. So the goal is alternating sections of instructions from each parent.
	- Optimization (complex life analogy)
		The primary activity of this phase is to fine tune constants and other behaviour. Warriors fight for even more rounds to determine the winner. Mutation is lower, and while breeding, larger chunks are copied into the new warrior.

	The cellular analogy is just to understand why different parameters were chosen in each era. Warriors are the same size in each era.
5. Progress tracker. Example:
```
8.00 hours remaining (0.01% complete) Era: 1
```
6. Finished the cycle you originally planned and want to optimize some more? Set:
```
FINAL_ERA_ONLY=True
ALREADYSEEDED=True #Make sure to set this True as well.
```

7. Two new evolution strategies.
    First, the single instruction modification strategies are now all under a "bag of marbles" analogy, to get them all under the same framework and even use fewer variables. Imagine a bag with six different-coloured marbles. One for each of the five modification strategies, plus one for "do nothing". The lists now tell how many marbles of each type to put in the bag for each era. A single random number decides which strategy is used. They are:
	- Do Nothing
	- Completely new random instruction
	- Nab instruction from another arena
	- Mini-mutation (change one thing about instruction)
	- Micro mutation. Increment or decrement a constant by one. Most prominent in the Optimization era.
	- Pull single instruction from instruction library. Maybe a previous evolution run, maybe one or more hand-written warriors. One text file. One instruction per line. Just assembled instructions, nothing else. If multiple warriors, just concatenated with no breaks. (Not needed and not included with distribution.)
8. Evolution strategy - Magic Number
	Let's look at the classic warrior, MICE (it's written in the old format, but that's ok, it's just for example):
```
jmp 2
dat 0
mov #12, **-1**
mov **@-2**, <5
djn -1, **-3**
spl @3
add #653, 2
jmz -5, **-6**
dat 833
```
All of the bold values end up pointing to the same address, but if it were advantageous for the address to be different, the odds of all those numbers changing to point to the same address in unison would be astronomically low. So, at the beginning of the warrior, the evolver will choose a magic number, and decrement it each instruction(because core war uses relative addressing) and if this mutation strategy is chosen, the evolver will replace either the A-field or B-field with that number. 

9. Value Normalizer.
	In the Nano Arena (size 80), for instance:
```
DJN.F $79,{-74
```
while legal, doesn't look so readable. It means the same thing as:
```
DJN.F $-1,{6
```
Evolver output will now rewrite numbers either negative or positive, whichever is closer to 0.

10. Archive and unarchive
	Create "archive" folder. After a battle, there is a chance of archiving the winner, or replacing the loser with something from the archive.
	- Keep clues as to how things evolved
	- Combat hyper-specialization
	- Transfer whole warriors between arenas
	- Easy way to insert warriors from
		- Previous evolution runs
		- Other evolved warriors
		- Other handwritten warriors
	- Collaborate with other instances (will need to edit source code to use absolute path)
		- Other instances on same machine
		- Over a LAN
		- Over the Internet with Google Drive, etc.

11. (New) Optional log file
Results of battles saved so you can analyse your progress. Current fields are 'era', 'arena', 'winner', 'loser', 'score1', 'score2', and 'bred_with'. Edit BATTLE_LOG_FILE setting to choose a file name; comment out or leave blank for no log.

12. Experimental CPU throttling support (disabled)
        The source includes commented-out hooks to integrate with the `psutil` Python package so the evolver can pause itself when overall CPU usage is high. The feature is currently experimental and therefore disabled by default. To try it, install `psutil` (`pip install psutil`), uncomment the `import psutil` line near the top of `evolverstage.py`, and restore the commented loop at the bottom of the file that checks `psutil.cpu_percent()`. Adjust the threshold to suit your system.

## Compiling `redcode-worker.cpp`

An experimental C++ worker (`redcode-worker.cpp`) can be built as a shared library for use with the Python evolver.

### Building with CMake (recommended)

CMake is the recommended build system because it selects the correct compiler and linker flags for your platform automatically, making the process consistent across Windows, macOS, and Linux.

1.  Create a build directory: `mkdir build && cd build`
2.  Run CMake: `cmake ..`
3.  Compile: `cmake --build .`

This will place the compiled library (`redcode_worker.so`, `.dll`, or `.dylib`) in the project's root directory.

### Building with g++

If you prefer compiling directly with `g++`, use the following command:

```
g++ -std=c++17 -shared -fPIC redcode-worker.cpp -o redcode_worker.so
```

To trace each instruction executed by the worker, set the environment variable `REDCODE_TRACE_FILE` to a log file path before running:

```
export REDCODE_TRACE_FILE=trace.log
```

Omit the variable to disable tracing.

## Docker

A `Dockerfile` is provided to run the evolver in an isolated environment. Build the image with:

```
docker build -t corewar-evolver .
```

Run the evolver:

```
docker run --rm -it corewar-evolver
```

The build step compiles the optional C++ worker (`redcode-worker.cpp`) so the library is ready to use inside the container.
