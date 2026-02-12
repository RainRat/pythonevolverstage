# Python Core War Evolver

This tool evolves digital warriors for the game of Core War. It pits warriors against each other and breeds the winners to find stronger strategies. You can use this tool even if you do not know the Redcode language.

We welcome your contributions! If you have an idea to improve the tool, please submit a pull request.

## Prerequisites

You need the following to run the evolver:

*   **Python 3**: Install the latest version of Python 3.
*   **nMars Simulator**:
    1. Download nMars from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    2. Place the `nmars.exe` (Windows) or `nmars` (Linux/macOS) file in the project folder.
    3. If you use Linux or macOS, open your terminal and run `chmod +x nmars` to give the simulator permission to run.

## Configuration

Edit `settings.ini` to customize the evolution.

1.  **Time**: Set `CLOCK_TIME` to the number of hours you want the script to run.
2.  **Seeding**: Set `ALREADYSEEDED = False` to start a new evolution. Set it to `True` to resume from existing warriors.
3.  **Arenas**: You can run multiple arenas at the same time, each with its own rules like core size or cycle limits.
    *   **Important**: Make sure all settings ending in `_LIST` (like `CORESIZE_LIST`) have the same number of items.
    *   **Total Arenas**: Set `LAST_ARENA` to the total number of arenas minus one. For example, if you want 8 arenas, set `LAST_ARENA = 7`.
4.  **Optimization**: Set `FINAL_ERA_ONLY = True` to skip early evolution phases and fine-tune your best warriors.

## How to Run

### Quick Start
To start evolving immediately:
1.  Run `python evolverstage.py --restart`.
    *This command automatically initializes the population and starts the evolution.*

### Detailed Steps
1.  Check your settings in `settings.ini`.
2.  Open your terminal in the project folder.
3.  **Verify setup**: Run `python evolverstage.py --check` (or `-c`) to make sure your configuration and simulator are ready.
4.  **Start evolution**: Run `python evolverstage.py`.
    *   **Tip**: Use `python evolverstage.py --dump-config` (or `-d`) to view your active settings.
5.  **Monitor progress**: The script shows a progress bar and how much time is left:
    ```text
    08:00:00 left | [========----------------------]  25.00% | Era 1 | Battles: 1,200 (15.5/s)
    ```
6.  **Review results**: Find your evolved warriors in the `arenaX` folders (e.g., `arena0/`).
7.  **Find the champion**: Use the benchmark tool (see **Command Line Tools**) to test warriors against each other.

## Troubleshooting

*   **No progress**: If the progress bar stays at 0% and no files appear in `arena` folders, ensure you used the `--restart` flag or set `ALREADYSEEDED = False` for your first run.
*   **nMars errors**: Ensure the `nmars` executable is in the project folder and has the correct permissions.

## Command Line Tools

The script includes several tools to manage evolution and test warriors. You can use short aliases for most commands (e.g., `-s` instead of `--status`).

### Manage Evolution
*   **Status** (`--status`, `-s`): Shows population size, average warrior length, and current champions. Use `--json` for machine-readable output.
*   **Leaderboard** (`--leaderboard`, `-l`): Displays top-performing warriors based on recent win streaks.
*   **Trends** (`--trends`, `-r`): Analyzes evolution by comparing the whole population to the top performers.
*   **Harvest** (`--harvest`, `-p`): Collects the best warriors from the leaderboard into a specific folder.
*   **Seed** (`--seed`): Populates an arena with a set of specific warriors or folders.
*   **Restart/Resume**: Use `--restart` to start fresh or `--resume` to continue from your current files.

### Analyze and View
*   **Analyze** (`--analyze`, `-i`): Shows details about a warrior's code, such as the instructions it uses. Works on files, folders, or selectors.
*   **View** (`--view`, `-v`): Displays the source code of a warrior in your terminal.
*   **Normalize** (`--normalize`, `-n`): Standardizes a warrior's code format. Use `-o` to save the output to a file.
*   **Collect** (`--collect`, `-k`): Extracts and normalizes instructions from many warriors into a single library file.

### Run Battles
*   **Single Battle** (`--battle`, `-b`): Runs a match between two warriors.
*   **Tournament** (`--tournament`, `-t`): Runs a competition between a group of warriors. Use `--champions` to automatically include the winners from every arena.
*   **Benchmark** (`--benchmark`, `-m`): Tests one warrior against every opponent in a folder.

### Dynamic Selectors
Instead of a filename, you can use these keywords in most commands:
*   `top`: The #1 warrior on the leaderboard for the current arena.
*   `topN`: The #N warrior (e.g., `top3`).
*   `random`: A random warrior from the current population.

**Targeting Arenas**: Add `@N` to a selector to target a specific arena (e.g., `top@2` or `random@0`). You can also use the `--arena N` (or `-a N`) flag to set the default arena for a command.

**Example**: `python evolverstage.py --battle top@0 random@1`

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
*   **Smart Selection**: Automatically chooses useful instructions and numbers as warriors evolve.
*   **Evolution Phases**:
    1.  **Exploration**: Makes frequent changes to find new strategies.
    2.  **Breeding**: Combines successful warriors to pass on their best traits.
    3.  **Optimization**: Makes small changes to fine-tune your top warriors.
*   **Dynamic Mutations**: Uses a "Bag of Marbles" system to apply different changes, such as stealing instructions or adjusting "magic numbers."
