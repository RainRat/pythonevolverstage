# Python Core War Evolver

**Evolve digital warriors for the game of Core War.**

This tool automatically creates and improves programs (called "warriors") that compete in a virtual computer. It uses evolutionary principles—battling warriors against each other and breeding the winners—to discover powerful new strategies.

---

## What is Core War?

Core War is a classic programming game. Several programs are placed in the memory of a virtual computer. They take turns executing instructions to either disable their opponents or survive the longest. These programs are written in a simple assembly language called **Redcode**.

**You do not need to know Redcode to use this tool.** The evolver handles the programming for you, discovering winning tactics through trial and error.

---

## Core Concepts

Understanding these basic ideas will help you get the most out of the evolver.

### Evolution Phases
The tool automatically shifts its strategy as it runs through three distinct phases. These correspond to the three values you see for many settings in `settings.ini`.

1.  **Exploration (Era 1)**: The tool makes frequent, large changes to discover new and unusual strategies.
2.  **Breeding (Era 2)**: The tool focuses on combining the most successful warriors to pass on winning traits.
3.  **Optimization (Era 3)**: The tool makes small, precise adjustments to fine-tune the performance of top-tier warriors.

### Smart Mutation
Instead of making completely random changes, the evolver uses several intelligent mutation types:
*   **Major**: Replaces an entire instruction with a random one to explore new possibilities.
*   **Minor**: Changes one part of an instruction (like an opcode or value) to refine it.
*   **Micro**: Adjusts a memory offset by exactly 1 to test very specific tactical changes.
*   **Magic Number**: Applies a consistent "magic number" across different instructions, which often helps in creating structured memory patterns.
*   **Library**: Pulls a known successful instruction from a library file (if provided).
*   **Nab**: Borrows a successful instruction from a warrior in a different arena.

### Arenas
An "Arena" is a separate environment with its own set of rules (like memory size or maximum program length). Running multiple arenas at once allows you to evolve warriors for different types of competitions simultaneously. Warriors can even "trade" successful instructions between arenas.

---

## Prerequisites

To use this tool, you need:

1.  **Python 3**: Download and install it from [python.org](https://www.python.org/).
2.  **nMars Simulator**: This is the "engine" that runs the battles.
    *   Download nMars from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    *   Extract the download and find the `nmars.exe` (Windows) or `nmars` (Linux/macOS) file.
    *   **Important**: Copy that file into this project's main folder.
    *   **Linux/macOS users**: Open your terminal in the folder and run `chmod +x nmars` to give the simulator permission to run.

---

## How to Run

### Quick Start
1.  Open your terminal or command prompt in the project folder.
2.  **Start evolution**: Run `python evolverstage.py --restart`.
    *This command initializes a new population and starts the evolutionary process.*

### Managing the Evolution
The evolver shows a real-time dashboard as it works:
```text
08:00:00 left | [========----------------------]  25.00% | Era 1 | Battles: 1,200 (15.5/s)
```

*   **Monitor**: Use `python evolverstage.py --status --watch` for a detailed real-time view.
*   **Stop**: Press `Ctrl+C` at any time. Your progress is saved automatically.
*   **Resume**: Run `python evolverstage.py` to continue where you left off.
*   **Check setup**: Run `python evolverstage.py --check` to verify your configuration.

---

## File Organization

As the evolver runs, it creates and manages several files and folders:

*   **arenaN/**: Each arena has its own folder (like `arena0`, `arena1`). This is where the actual warrior programs (.red files) are stored.
*   **archive/**: The tool occasionally saves the most successful warriors here to ensure their strategies are not lost as the population evolves.
*   **battle_log.csv**: This file contains a detailed history of every match. It records which warriors won, who they bred with, and the final scores.

---

## Configuration

You can customize the evolution by editing the `settings.ini` file in the project folder.

### Common Settings
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

### Analyze and View
*   **Inspect**: `python evolverstage.py --inspect top`
    *   Provides a detailed profile of a warrior's performance, strategy, and code.
*   **Analyze**: `python evolverstage.py --analyze top`
    *   Shows statistics on the instructions used by the current champion.
*   **Trends**: `python evolverstage.py --trends`
    *   Compares the whole population's code to the top-performing warriors.
*   **Compare**: `python evolverstage.py --compare top@0 top@1`
    *   Provides a side-by-side statistical comparison between two warriors.
*   **View**: `python evolverstage.py --view top`
    *   Displays the Redcode source code of a warrior.

### Battles and Tournaments
*   **Tournament**: `python evolverstage.py --tournament arena0/`
    *   Runs an everyone-vs-everyone tournament between all warriors in a folder.
    *   Use the `--champions` flag to include winners from every arena.
*   **Benchmark**: `python evolverstage.py --benchmark top folder/`
    *   Tests a warrior against every opponent in a specific folder.
*   **Single Battle**: `python evolverstage.py --battle warrior1.red warrior2.red`

### Utilities
*   **Export**: `python evolverstage.py --export top --output champion.red`
*   **Harvest**: `python evolverstage.py --harvest winners/`
    *   Collects the best warriors from the leaderboard into a folder.
*   **Seed**: `python evolverstage.py --seed my_warriors/`
    *   Populates arenas with specific warriors.
*   **Collect**: `python evolverstage.py --collect folder/ -o library.txt`
    *   Creates an instruction library from a group of warriors.

**Note**: Add `--arena N` to any command to use the rules of a specific arena (default is Arena 0).

---

## Dynamic Selectors

You can use these keywords instead of a filename in most commands:

*   **top**: Selects the #1 warrior on the leaderboard.
*   **topN**: Selects the #N warrior (e.g., `top5`).
*   **random**: Selects a random warrior from the population.

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
