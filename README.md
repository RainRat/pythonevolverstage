# Python Core War Evolver

**Evolve digital warriors for the game of Core War.**

This tool automatically creates and improves programs (called "warriors") that compete in a virtual computer. It uses evolutionary principles—battling warriors against each other and breeding the winners—to discover powerful new strategies.

---

## What is Core War?

Core War is a classic programming game. Several programs are placed in the memory of a virtual computer. They take turns executing instructions to either disable their opponents or survive the longest. These programs are written in a simple assembly language called **Redcode**.

**You do not need to know Redcode to use this tool.** The evolver handles the programming for you, discovering winning tactics through trial and error.

---

## Main Ideas

Understanding these basic ideas will help you get the most out of the evolver.

### Evolution Phases
The tool automatically shifts its strategy as it runs through three distinct phases. These correspond to the three values you see for many settings in `settings.ini`.

1.  **Exploration (Era 1)**: The tool makes frequent, large changes to discover new and unusual strategies.
2.  **Breeding (Era 2)**: The tool focuses on combining the most successful warriors to pass on winning traits.
3.  **Optimization (Era 3)**: The tool makes small, precise adjustments to fine-tune the performance of top-tier warriors.

### Evolution Strategies
Instead of making completely random changes, the evolver uses seven intelligent strategies to create new warriors:
*   **Do Nothing**: Occasionally makes no changes, which helps to preserve successful programs as they are.
*   **Major Mutation**: Replaces an entire instruction with a random one to explore new possibilities.
*   **Minor Mutation**: Changes one part of an instruction (like an opcode or value) to refine it.
*   **Micro Mutation**: Adjusts a memory offset by exactly 1 to test very specific tactical changes.
*   **Magic Number**: Applies a consistent "magic number" across instructions to help create structured memory patterns.
*   **Library**: Pulls a known successful instruction from a library file (if provided).
*   **Nab**: Borrows a successful instruction from a warrior in a different arena.

### Tactical Strategies
The evolver identifies the behavior of warriors by analyzing their code. You will see these labels in the leaderboard and analysis reports:
*   **Paper (Replicator)**: Creates multiple copies of itself to overwhelm the opponent.
*   **Stone (Bomb-thrower)**: Throws "bombs" (data or instructions) into memory to disable other programs.
*   **Imp (Pulse)**: A simple, fast-moving program that is difficult to hit.
*   **Vampire / Pittrap**: Forces the opponent to jump to a location that disables them.
*   **Mover / Runner**: Moves through memory quickly to stay safe and avoid attacks.
*   **Wait / Shield**: A defensive program that waits for the opponent to make a mistake.
*   **Experimental**: A unique or complex strategy that does not fit into a standard category.

### Arenas
An "Arena" is a separate environment with its own set of rules (like memory size or maximum program length). Running multiple arenas at once allows you to evolve warriors for different types of competitions simultaneously. Warriors can even "trade" successful instructions between arenas.

---

## What You Need

To use this tool, you need:

1.  **Python 3**: Download and install it from [python.org](https://www.python.org/).
2.  **nMars Simulator**: This is the "engine" that runs the battles.
    *   Download nMars from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    *   Extract the download and find the `nmars.exe` (Windows) or `nmars` (Linux/macOS) file.
    *   **Important**: Copy that file into this project's main folder.
    *   **Linux/macOS users**: Open your terminal in the folder and run `chmod +x nmars` to give the simulator permission to run.
3.  **No extra libraries**: This project only uses the standard Python library and requires no additional packages (like `pip install`).

---

## How to Run

### Quick Start
1.  Open your terminal or command prompt in the project folder.
2.  **Start a new evolution**: Run `python evolverstage.py --restart`.
    *This command initializes a new population and starts the evolutionary process.*
3.  **Resume evolution**: Run `python evolverstage.py` or `python evolverstage.py --resume`.
    *This continues the evolution using your existing warriors.*

### Managing the Evolution
The evolver shows a real-time dashboard as it works:
```text
08:00:00 left | [==--------]  25.00% | Era 1 | Battles: 1,200 (15.5/s)
```

#### Reading the Dashboard
The status line tells you how the evolution is progressing:
*   **Time left**: How much longer the evolution will run.
*   **Progress bar**: A visual representation of the total time completed.
*   **Era**: The current evolution phase (1, 2, or 3).
*   **Battles**: The total number of matches completed.
*   **Speed**: How many battles are happening every second (e.g., 15.5/s).

*   **Monitor**: Use `python evolverstage.py --status --watch` for a detailed real-time view.
*   **Stop**: Press `Ctrl+C` at any time. Your progress is saved automatically.
*   **Check setup**: Run `python evolverstage.py --check` to verify your configuration.

---

## Files and Folders

As the evolver runs, it creates and manages several files and folders:

*   **arenaN/**: Each arena has its own folder (like `arena0`, `arena1`). This is where the actual warrior programs (.red files) are stored.
*   **archive/**: The tool occasionally saves the most successful warriors here to ensure their strategies are not lost as the population evolves.
*   **examples/**: A collection of successful warriors from previous evolution runs that you can use as references or opponents.
*   **battle_log.csv**: This file contains a detailed history of every match. It records which warriors won, who they bred with, and the final scores.

---

## Settings

You can customize the evolution by editing the `settings.ini` file in the project folder.

### Common Settings
*   **Start/Resume**: The `ALREADYSEEDED` setting controls whether you start a new evolution (`False`) or resume an existing one (`True`). Note that the `--restart` and `--resume` flags will override this setting.
*   **Time**: Set `CLOCK_TIME` to the number of hours you want the evolution to run.
*   **Arenas**: You can run multiple evolution environments at once.
    *   **LAST_ARENA**: Set this to the highest numbered arena you want to use. For example, if you want 8 arenas, the numbers are 0 through 7, so set this to `7`.
    *   **_LIST settings**: Ensure all settings ending in `_LIST` (like `CORESIZE_LIST`) have the same number of values as you have arenas.
*   **Skip to Fine-tuning**: Set `FINAL_ERA_ONLY = True` to skip the early exploration phases and focus exclusively on the Optimization phase for your best warriors.

### Understanding Three-Value Lists
Most mutation and strategy settings (like `NOTHING_LIST` or `RANDOM_LIST`) contain three values separated by commas. These correspond to the three evolution phases:
1.  The first value is used during **Exploration** (Era 1).
2.  The second value is used during **Breeding** (Era 2).
3.  The third value is used during **Optimization** (Era 3).

For example, `NOTHING_LIST = 10, 18, 27` means the "Do Nothing" mutation becomes more common as the evolution progresses, helping to stabilize successful programs.

---

## Command Line Tools

The script includes several tools for analyzing and testing your warriors.

### Status and Progress
*   **Status** (`--status`, `-s`): `python evolverstage.py --status --watch`
    *   Shows a real-time view of all arenas and population health.
*   **Leaderboard** (`--leaderboard`, `-l`): `python evolverstage.py --leaderboard`
    *   Lists the top-performing warriors based on their recent win streaks.
*   **Rankings** (`--rankings`, `-K`): `python evolverstage.py --rankings`
    *   Shows the top-performing warriors based on their lifetime win rate.
*   **Report** (`--report`, `-g`): `python evolverstage.py --report`
    *   Generates a comprehensive health and performance report for an arena.
*   **Trends** (`--trends`, `-r`): `python evolverstage.py --trends`
    *   Compares the whole population's code to the top-performing warriors.

### Analyze and View
*   **Inspect** (`--inspect`, `-x`): `python evolverstage.py --inspect top`
    *   Provides a detailed profile of a warrior's performance, strategy, and code.
*   **Lineage** (`--lineage`, `-j`): `python evolverstage.py --lineage top`
    *   Traces the parentage of a warrior to see its family tree.
*   **Meta** (`--meta`, `-u`): `python evolverstage.py --meta`
    *   Analyzes the distribution of different tactical strategies in an arena.
*   **Hall of Fame** (`--hall-of-fame`, `-H`): `python evolverstage.py --hall-of-fame`
    *   Displays the all-time best warrior for each tactical category.
*   **Analyze** (`--analyze`, `-i`): `python evolverstage.py --analyze top`
    *   Shows statistics on the instructions used by a warrior.
*   **Compare** (`--compare`, `-y`): `python evolverstage.py --compare top@0 top@1`
    *   Provides a side-by-side statistical comparison between two warriors.
*   **Diff** (`--diff`, `-f`): `python evolverstage.py --diff top1 top2`
    *   Provides a line-by-line code comparison between two warriors.
*   **View** (`--view`, `-v`): `python evolverstage.py --view top`
    *   Displays the Redcode source code of a warrior.

### Battles and Tournaments
*   **Tournament** (`--tournament`, `-t`): `python evolverstage.py --tournament`
    *   Runs an everyone-vs-everyone tournament. Defaults to the top 10 warriors.
*   **Gauntlet** (`--gauntlet`, `-G`): `python evolverstage.py --gauntlet top`
    *   Tests a warrior against the champions of every single arena.
*   **Benchmark** (`--benchmark`, `-m`): `python evolverstage.py --benchmark top folder/`
    *   Tests a warrior against every opponent in a specific folder.
*   **Single Battle** (`--battle`, `-b`): `python evolverstage.py --battle warrior1.red warrior2.red`

### Utilities and Optimization
*   **Optimize** (`--optimize`): `python evolverstage.py --optimize top`
    *   Automatically improves a warrior by testing small mutations against itself.
*   **Normalize** (`--normalize`, `-n`): `python evolverstage.py --normalize top`
    *   Cleans and standardizes a warrior's Redcode format.
*   **Export** (`--export`, `-e`): `python evolverstage.py --export top --output champion.red`
*   **Harvest** (`--harvest`, `-p`): `python evolverstage.py --harvest winners/`
    *   Collects the best warriors from the leaderboard into a folder.
*   **Seed** (`--seed`): `python evolverstage.py --seed my_warriors/`
    *   Populates arenas with specific warriors.
*   **Collect** (`--collect`, `-k`): `python evolverstage.py --collect folder/ -o library.txt`
    *   Creates an instruction library from a group of warriors.

### General Commands
*   **Check Setup** (`--check`, `-c`): `python evolverstage.py --check`
    *   Verifies your configuration and simulator setup.
*   **Dump Config** (`--dump-config`, `-d`): `python evolverstage.py --dump-config`
    *   Shows the active configuration from `settings.ini`.
*   **Version** (`--version`): `python evolverstage.py --version`
    *   Displays the current version of the tool.

**Note**: Add `--arena N` (or `-a N`) to any command to use the rules of a specific arena (default is Arena 0).

---

## Dynamic Selectors

You can use these keywords instead of a filename in most commands:

*   **top**: Selects the #1 warrior on the leaderboard.
*   **topN**: Selects the #N warrior (e.g., `top5`).
*   **random**: Selects a random warrior from the population.
*   **Warrior ID**: Selects a specific warrior by its ID number (e.g., `123`).

Target a specific arena by adding `@N` to a selector or filename (e.g., `top@2`, `random@0`).

---

## Troubleshooting

*   **No progress**: If the dashboard stays at 0% and no files appear in `arena` folders, ensure you used the `--restart` flag for your first run.
*   **nMars errors**: Make sure the `nmars` executable is in the project folder and has the correct permissions (`chmod +x nmars` on Linux/macOS).

---

## Features

*   **Multi-Arena Support**: Run many arenas with different rules simultaneously.
*   **Diversity Tracking**: Automatically monitors the population to prevent stagnation.
*   **Machine-Readable Output**: Most analysis commands support a `--json` flag for easy integration with other tools.

---

## Contributing

We welcome your contributions!

1.  Fork the repository.
2.  Make your improvements.
3.  Run the tests: `python -m unittest discover tests`.
4.  Submit a pull request.

---

## License

This project is licensed under the GNU Lesser General Public License v3.0 (LGPL-3.0). See `LICENSE.md` for details.
