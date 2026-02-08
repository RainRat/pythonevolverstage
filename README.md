# Python Core War Evolver

Evolve Core War warriors by pitting them against each other and breeding winners. The tool uses mutations to create stronger strategies over time. You do not need to know Redcode to use it.

Contributions are welcome! If you have a suggestion or improvement, please submit a pull request.

## Prerequisites

Before running the evolver, you need:

*   **Python 3.x**: Install Python 3 on your system.
*   **nMars Simulator**:
    1. Download nMars from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    2. Put `nmars.exe` (Windows) or `nmars` (Linux/macOS) in this folder.
    3. On Linux or macOS, run `chmod +x nmars` in your terminal to allow it to run.

## Configuration

Edit `settings.ini` to customize the evolution.

1.  **Time**: Set `CLOCK_TIME` to the number of hours you want the script to run.
2.  **Seeding**: Set `ALREADYSEEDED = False` to start a new evolution. Set it to `True` to resume from existing warriors.
3.  **Arenas**: Run multiple arenas with different rules (like core size or cycles).
    *   **Important**: All list settings (like `CORESIZE_LIST`, `CYCLES_LIST`) must be the same length.
    *   Set `LAST_ARENA` to the index of your final arena. For example, if you have 8 arenas, they are numbered 0 to 7, so set `LAST_ARENA` to 7.
4.  **Optimization**: Set `FINAL_ERA_ONLY = True` to skip early evolution phases and fine-tune your best warriors.

## How to Run

### Quick Start
To start evolving immediately:
1.  Run `python evolverstage.py --restart`.
    *This command automatically initializes the population and starts the evolution.*

### Detailed Steps
1.  Verify your settings in `settings.ini`.
2.  Open your terminal in the project folder.
3.  **Validate setup**: Run `python evolverstage.py --check` to ensure your configuration and simulator are ready.
4.  **Start evolution**: Run `python evolverstage.py`.
    *   **Tip**: Use `python evolverstage.py --dump-config` to see the active settings.
5.  **Monitor progress**: The script displays a progress bar and estimated time remaining:
    ```text
    08:00:00 left | [========----------------------]  25.00% | Era 1 | Battles: 1,200 (15.5/s)
    ```
6.  **Review results**: Find your evolved warriors in the `arenaX` folders (e.g., `arena0/`).
7.  **Find the champion**: Use the benchmark tool (see **Command Line Tools**) to test warriors against each other.

## Troubleshooting

*   **No progress**: If the progress bar stays at 0% and no files appear in `arena` folders, ensure you used the `--restart` flag or set `ALREADYSEEDED = False` for your first run.
*   **nMars errors**: Ensure the `nmars` executable is in the project folder and has the correct permissions.

## Command Line Tools

The script includes several tools for managing evolution and testing warriors.

### Manage Evolution
*   **Status**: `python evolverstage.py --status`
    *   Shows population size, average warrior length, and current champions. Use `--json` for machine-readable output.
*   **Leaderboard**: `python evolverstage.py --leaderboard`
    *   Displays top-performing warriors based on recent win streaks.
*   **Harvest**: `python evolverstage.py --harvest directory/`
    *   Collects the best warriors from the leaderboard into a specific folder.
*   **Restart/Resume**: Use `--restart` to start fresh or `--resume` to continue from your current files.

### Analyze and View
*   **Analyze**: `python evolverstage.py --analyze warrior.red`
    *   Shows details about a warrior's code, such as the types of instructions it uses.
*   **View**: `python evolverstage.py --view top`
    *   Displays the source code of a warrior. Supports keywords like `top` or `random`.

### Run Battles
*   **Single Battle**: `python evolverstage.py --battle warrior1.red warrior2.red`
*   **Tournament**: `python evolverstage.py --tournament directory/`
    *   Runs a round-robin competition between all warriors in a folder.
*   **Benchmark**: `python evolverstage.py --benchmark warrior.red directory/`
    *   Tests a warrior against all opponents in a folder.
*   **Normalize**: `python evolverstage.py --normalize warrior.red`
    *   Standardizes a warrior's code format.

**Note**: Add `--arena N` to any command to use the rules of a specific arena (default is Arena 0).

## Output Explained

### Warrior Files
*   **Arenas (`arena0/`, `arena1/`, ...)**: Contains the current population.
*   **Archive (`archive/`)**: Stores successful warriors to preserve good strategies.

### Battle Log
If `BATTLE_LOG_FILE` is set in `settings.ini`, results are saved to a CSV file:
*   **era**: Current evolution phase (1, 2, or 3).
*   **arena**: The arena where the battle occurred.
*   **winner/loser**: Warrior IDs.
*   **score1/score2**: Match scores.
*   **bred_with**: The ID of the warrior used for breeding after the match.

## Running Tests

To ensure the code is working correctly, you can run the included test suite.

### Standard Tests
```bash
python -m unittest discover tests
```

### Extended Tests (requires pytest)
1.  Install pytest: `pip install pytest`
2.  Run tests: `pytest`

## Features

*   **Multi-Arena Support**: Run many arenas with different rules at the same time.
*   **Intelligent Selection**: Automatically prioritizes useful instructions and numbers during evolution.
*   **Phased Evolution**:
    1.  **Exploration**: Uses frequent changes to find new strategies.
    2.  **Breeding**: Combines successful warriors to pass on winning traits.
    3.  **Optimization**: Fine-tunes code for peak performance.
*   **Dynamic Mutation**: Uses a "Bag of Marbles" system to randomly apply different mutation types, including instruction theft and "magic number" adjustments.
