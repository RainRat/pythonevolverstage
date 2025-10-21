# Python Core War Evolver

An Evolver for Core War, written in Python. You don't need to know Redcode (the language used in Core War).

A genetic algorithm will pit the warriors against each other, then breed the winner, with some random mutation.

If you have a suggestion, submit a pull request. I put it on Github to encourage contributions.

## Usage:

For all of these, modify the constants in settings.ini.

1. Edit the **per-arena lists** (like `CORESIZE_LIST`, `CYCLES_LIST`, etc.) to contain the parameters of the competitions you want to compete in. If you just want to compete in one arena, you have lists of length 1.
2. Set the **per-era lists** (like `BATTLEROUNDS_LIST`, `NOTHING_LIST`, `RANDOM_LIST`, etc.) to control the evolution process over time. The number of eras is defined by the number of entries in `BATTLEROUNDS_LIST`.
3. Set ALREADYSEEDED to False. If you interrupt it and want to resume, set it to True.
4. Choose how much actual wall clock time (in hours) you plan to run the project for and modify CLOCK_TIME
5. Select the battle engine by setting `BATTLE_ENGINE` to `nmars`, `internal`, or `pmars` in `settings.ini`. Use `nmars` to call the external nMars executable, `internal` to use the bundled C++ worker, or `pmars` to shell out to a local pMARS binary.
6. (Optional) Enable `IN_MEMORY_ARENAS` to cache warriors in RAM and reduce disk writes; adjust `ARENA_CHECKPOINT_INTERVAL` to control how often arenas are saved when running in this mode.
7. python evolverstage.py (add `--verbosity {terse,default,verbose,pseudo-graphical}` to control console output; use `--run-final-tournament` to immediately run the post-training bracket when the evolution loop completes)
    * Use `--seed <number>` when you want to replay the same evolution history. The evolver seeds Python's RNG with the provided value before selecting arenas, mutation strategies, or battle pairings, so every probabilistic decision—from "bag of marbles" draws to arena selection—follows the same sequence. This is invaluable when you are tuning settings and need to compare like-for-like behaviour.
8. When the program starts it prints a concise run summary based on `settings.ini` (and any command-line overrides). You will see which battle engine is active, how many arenas will be maintained, whether battles are logged, how warriors are stored, and if the final tournament (including CSV export) is enabled. This makes it easy to confirm that the configuration on disk matches your expectations before a long training session.
9. When done, out of the warriors in each arena, you will need to pick which is actually the best. CoreWin in round robin mode can find the best ones, or use a benchmarking tool.

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
7 hours 12 minutes 30.00 seconds remaining (0.01% complete) Era: 1
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

12. Champion-aware matchmaking
        Each arena tracks its current "champion"—the most recent warrior to win a non-draw battle there. When selecting contestants, there is roughly a 50% chance that the champion will be slotted into the next match. This gentle bias lets you repeatedly pressure successful warriors without turning every round into a deterministic ladder climb, and it encourages newcomers to prove themselves against the reigning specialist in that arena.

13. Tournament and evolution reporting
        The evolver now reports on itself so that long sessions leave an audit trail:
        - After the final tournament, the console prints arena averages, benchmark comparisons, and a per-warrior summary showing average score, standard deviation, and how many arenas each competitor appeared in. The report also highlights the most consistent performers (low variance with strong results) so that you can spot reliable generalists at a glance.
        - If you export the tournament standings (`--final-tournament-csv`), the rankings for every arena are written to disk alongside those console insights.
        - Whenever the main loop finishes—or you interrupt it with Ctrl+C—the evolver prints an evolution statistics digest listing battles per era, the total battle count, and the approximate speed in battles per hour. This makes it easy to compare throughput between different hardware setups or parameter combinations.

## Compiling `redcode-worker.cpp`

An experimental C++ worker (`redcode-worker.cpp`) can be built as a shared library for use with the Python evolver.

The easiest way to manage the build and test workflow is via the repository's `Makefile`:

* `make build` configures and compiles the worker with CMake, emitting the shared library (`redcode_worker.so`, `.dll`, or `.dylib`) in the project root.
* `make test` depends on `make build` and then runs the Python and C++ pytest suites (`tests/test_evolverstage.py` and `tests/test_redcode_worker.py`).
* `make docker-build` wraps the Docker image build so the container can be prepared with a single command.
* `make clean` removes the build directory and compiled shared libraries.

### Building with CMake (recommended)

CMake remains the recommended build system because it selects the correct compiler and linker flags for your platform automatically, making the process consistent across Windows, macOS, and Linux.

1.  Create a build directory: `mkdir build && cd build`
2.  Run CMake: `cmake ..`
3.  Compile: `cmake --build .`

The provided CMake configuration emits the compiled library (`redcode_worker.so`, `.dll`, or `.dylib`) in the project's root directory.

### Building with g++

If you prefer compiling directly with `g++`, use the following command (replace the output extension with `.dll` on Windows or `.dylib` on macOS):

```
g++ -std=c++17 -shared -fPIC redcode-worker.cpp -o redcode_worker.so
```

To trace each instruction executed by the worker, set the environment variable `REDCODE_TRACE_FILE` to a log file path before running:

```
export REDCODE_TRACE_FILE=trace.log
```

Omit the variable to disable tracing.

## Docker

A `Dockerfile` is provided to run the evolver in an isolated environment. Build the image with `make docker-build`, which wraps the command below:

```
docker build -t corewar-evolver .
```

Run the evolver:

```
docker run --rm -it corewar-evolver
```

The build step compiles the optional C++ worker (`redcode-worker.cpp`) so the library is ready to use inside the container.

### Running on Windows 11 with Docker Desktop and WSL

Docker Desktop integrates with WSL 2, so you can build and run the container from either a WSL terminal (Ubuntu, Debian, etc.)
or from PowerShell. The workflow below keeps your project files inside the WSL distribution, which avoids path-conversion edge
cases and gives the best filesystem performance when training warriors.

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) and ensure that:
   * **Use the WSL 2 based engine** is enabled in Docker Desktop's settings.
   * At least one Linux distribution is installed in WSL (e.g., Ubuntu) and is enabled for Docker integration.
2. Open the WSL distribution (for example, launch "Ubuntu" from the Start menu) and clone this repository inside the Linux
   filesystem:

   ```bash
   git clone https://github.com/<your-account>/pythonevolverstage.git
   cd pythonevolverstage
   ```

3. Build the Docker image from the WSL prompt:

   ```bash
   make docker-build
   ```

   The `docker` CLI from WSL communicates with the Windows Docker Desktop engine, so no additional setup is required.

4. Start the evolver inside a container. The `docker-run` make target wraps the recommended command:

   ```bash
   make docker-run
   ```

   To persist results such as evolved warriors or logs on the host, mount the project directory into the container when you run
   it:

   ```bash
   docker run --rm -it -v "$(pwd):/app" corewar-evolver
   ```

   Windows PowerShell users can run the same command outside WSL by replacing `$(pwd)` with `${PWD}`:

   ```powershell
   docker run --rm -it -v "${PWD}:/app" corewar-evolver
   ```

   In either environment, the evolver runs with the repository checked out at `/app` inside the container, so any modifications
   you make to configuration files (for example, `settings.ini`) are automatically visible to the running process.
