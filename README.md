# Python Core War Evolver

**Evolve digital warriors for the game of Core War.**

This tool automatically creates and improves programs (called "warriors") that compete in a virtual computer. It uses evolutionary principles—battling warriors against each other and breeding the winners—to discover powerful new strategies.

---

## What is Core War?

Core War is a classic programming game. Several programs are placed in the memory of a virtual computer. They take turns executing instructions to either disable their opponents or survive the longest. These programs are written in a simple assembly language called **Redcode**.

**You do not need to know Redcode to use this tool.** The evolver handles the programming for you, discovering winning tactics through trial and error.

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

## Configuration

You can customize the evolution by editing `settings.ini`.

*   **Time**: Set `CLOCK_TIME` to the number of hours you want the script to run.
*   **Arenas**: You can run multiple arenas with different rules (e.g., core size).
    *   Set `LAST_ARENA` to the total number of arenas minus one (e.g., `7` for 8 arenas).
    *   Ensure all `_LIST` settings (like `CORESIZE_LIST`) have the same number of values.
*   **Optimization**: Set `FINAL_ERA_ONLY = True` to skip early phases and focus on fine-tuning your best warriors.

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

*   **Evolution Phases**: The tool automatically shifts strategy as it runs:
    1.  **Exploration**: Discovers new strategies through frequent, large changes.
    2.  **Breeding**: Combines successful warriors to pass on winning traits.
    3.  **Optimization**: Makes small, precise adjustments to fine-tune performance.
*   **Multi-Arena Support**: Run many arenas with different rules simultaneously.
*   **Smart Mutation**: Uses a "Bag of Marbles" system to intelligently adjust instructions and "magic numbers."
*   **Diversity Tracking**: Automatically monitors the population to prevent stagnation.

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
