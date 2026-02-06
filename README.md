# Python Core War Evolver

Evolve Core War warriors using genetic algorithms. This tool pits warriors against each other, breeds winners, and introduces mutations to develop stronger strategies over time. You do not need to know Redcode to use it.

Contributions are welcome! If you have a suggestion or improvement, please submit a pull request.

## Prerequisites

Before running the evolver, you need:

*   **Python 3.x**: Ensure you have Python 3 installed.
*   **nMars Simulator**:
    1.  Download the latest version from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    2.  Place `nmars.exe` (Windows) or `nmars` (Linux/macOS) in the project folder.
    3.  (Linux/macOS) Make the file executable by running `chmod +x nmars` in your terminal.

## Configuration

Settings are in `settings.ini`. Open this file to customize how the evolution works.

1.  **Time**: Set `CLOCK_TIME` to the number of hours you want the script to run.
2.  **Seeding**: Set `ALREADYSEEDED = False` to start a new evolution. Set it to `True` to resume from existing warriors.
3.  **Arenas**: You can run multiple arenas with different rules (like core size or cycles).
    *   **Important**: All list settings (like `CORESIZE_LIST`, `CYCLES_LIST`) must be the same length.
    *   Update `LAST_ARENA` to match the index of your last arena. For example, if you have 8 arenas (indexed 0 to 7), set `LAST_ARENA = 7`.
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
    *   Shows population size and average warrior length for each arena. Use `--json` for machine-readable output.
*   **Restart**: `python evolverstage.py --restart`
    *   Starts from scratch, overwriting existing warriors.
*   **Resume**: `python evolverstage.py --resume`
    *   Continues evolution from your current files.

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

*   **Supports multiple arenas**: Evolve warriors in different environments simultaneously.
*   **Selects effective code**: Automatically prioritizes useful instructions and numbers during evolution.
*   **Phased Evolution**:
    1.  **Exploration (Era 1)**: High mutation rate to discover new strategies.
    2.  **Breeding (Era 2)**: Combines parts of winning warriors.
    3.  **Optimization (Era 3)**: Fine-tunes values for peak performance.
*   **Diverse Mutation Strategies**: Uses a "Bag of Marbles" system to randomly apply different mutation types, including instruction theft from other arenas and "magic number" adjustments.
