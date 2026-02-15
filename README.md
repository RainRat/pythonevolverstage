# Python Core War Evolver

This tool evolves digital warriors for the game of Core War. It pits warriors against each other and breeds the winners to find stronger strategies. You can use this tool even if you do not know the Redcode language.

We welcome your contributions! If you have an idea to improve the tool, please submit a pull request.

## Prerequisites

You need the following to run the evolver:

*   **Python 3**: Install the latest version of Python 3.
*   **nMars Simulator**:
    1. Download nMars from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    2. Place the `nmars.exe` (Windows) or `nmars` (Linux/macOS) file in the project folder or in your system's PATH.
    3. If you use Linux or macOS, open your terminal and run `chmod +x nmars` to give the simulator permission to run.

## Configuration

Edit `settings.ini` to customize the evolution. You can also use command line flags (see **Manage Evolution**) to start a new run or resume without editing the file.

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
3.  **Verify setup**: Run `python evolverstage.py --check` to make sure your configuration and simulator are ready.
4.  **Start evolution**: Run `python evolverstage.py`.
    *   **Tip**: Use `python evolverstage.py --dump-config` to view your active settings.
5.  **Monitor progress**: The script shows a progress bar and how much time is left:
    ```text
    08:00:00 left | [========----------------------]  25.00% | Era 1 | Battles: 1,200 (15.5/s)
    ```
6.  **Review results**: Find your evolved warriors in the `arenaX` folders (e.g., `arena0/`).
7.  **Find the champion**: Use the benchmark tool (see **Command Line Tools**) to test warriors against each other.

## Troubleshooting

*   **No progress**: If the progress bar stays at 0% and no files appear in `arena` folders, ensure you used the `--restart` flag or set `ALREADYSEEDED = False` for your first run.
*   **nMars errors**: Ensure the `nmars` executable is in the project folder or system PATH, and has the correct permissions.

## Command Line Tools

The script includes several tools for managing evolution and testing warriors.

### Manage Evolution
*   **Status**: `python evolverstage.py --status`
    *   Shows population size, average warrior length, and current champions. Use `--watch` (or `-w`) for real-time monitoring and `--json` for machine-readable output.
*   **Leaderboard**: `python evolverstage.py --leaderboard`
    *   Displays top-performing warriors based on recent win streaks.
*   **Harvest**: `python evolverstage.py --harvest folder/`
    *   Collects the best warriors from the leaderboard into a specific folder.
*   **Seed**: `python evolverstage.py --seed targets...`
    *   Populates all arenas (or a specific one with `--arena N`) with warriors from the specified files or folders.
*   **Restart/Resume**: Use `--restart` to start a new evolution or `--resume` to continue from your current files. These flags override the `ALREADYSEEDED` setting in `settings.ini`.
*   **Version**: `python evolverstage.py --version`
    *   Displays the current version of the tool.

### Analyze and View
*   **Analyze**: `python evolverstage.py --analyze warrior.red`
    *   Shows details about a warrior's code, such as the types of instructions it uses.
*   **Trends**: `python evolverstage.py --trends`
    *   Shows how the population's instructions compare to the top performers.
*   **Compare**: `python evolverstage.py --compare top@0 top@1`
    *   Provides a side-by-side statistical comparison between two warriors or populations.
*   **View**: `python evolverstage.py --view top`
    *   Displays the source code of a warrior. Supports keywords like `top` or `random`.
*   **Export**: `python evolverstage.py --export top --output champion.red`
    *   Saves a warrior with a standard Redcode header and clean formatting.
*   **Collect**: `python evolverstage.py --collect folder/ -o library.txt`
    *   Extracts and standardizes instructions from warriors to create a library.

### Run Battles
*   **Single Battle**: `python evolverstage.py --battle warrior1.red warrior2.red`
*   **Tournament**: `python evolverstage.py --tournament targets...`
    *   Runs an everyone-vs-everyone tournament between all warriors in a folder or a specific list of warriors. Use the `--champions` flag to automatically include winners from every arena.
*   **Benchmark**: `python evolverstage.py --benchmark warrior.red folder/`
    *   Tests a warrior against all opponents in a folder.
*   **Normalize**: `python evolverstage.py --normalize warrior.red`
    *   Standardizes a warrior's code format.

**Note**: Add `--arena N` to any command to use the rules of a specific arena (default is Arena 0).

## Dynamic Selectors

In many commands, you can use keywords instead of a filename to quickly target specific warriors:

*   **top**: Selects the #1 warrior on the leaderboard.
*   **topN**: Selects the #N warrior (e.g., `top5`).
*   **random**: Selects a random warrior from the population.

You can also target a specific arena by adding `@N` to any selector or filename:
*   `top@2`: The champion of Arena 2.
*   `random@0`: A random warrior from Arena 0.
*   `1.red@1`: Warrior 1 from Arena 1.

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
*   **Evolution Phases**: As time passes, the tool automatically shifts its strategy:
    1.  **Exploration**: The tool makes frequent, large changes to discover new strategies from scratch.
    2.  **Breeding**: Successful warriors are combined together to pass on their winning traits to new generations.
    3.  **Optimization**: The tool makes small, precise changes to fine-tune the performance of your best warriors.
*   **Dynamic Mutations**: Uses a "Bag of Marbles" system to apply different types of changes. It can steal successful instructions from other arenas or adjust "magic numbers" that help warriors survive.
