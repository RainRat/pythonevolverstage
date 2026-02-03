# Python Core War Evolver

An Evolver for Core War, written in Python. You don't need to know Redcode (the language used in Core War) to use this tool.

This project uses a genetic algorithm to pit warriors against each other, breed the winners, and introduce mutations to evolve superior strategies over time.

Contributions are welcome! If you have a suggestion or improvement, please submit a pull request.

## Prerequisites

Before running the evolver, you need:

*   **Python 3.x**: This project requires Python 3 to run.
*   **nMars**: This is the simulator that runs the battles.
    *   **Download**: Get the latest version from [SourceForge](https://sourceforge.net/projects/nmars/files/).
    *   **Windows**: Download `nmars.exe` and put it in the same folder as this project.
    *   **Linux/macOS**: Download `nmars` and put it in the same folder, or install it so it runs from your terminal.

## Configuration

Settings are in `settings.ini`. Open this file to change how the evolution works.

1.  **Arenas**: You can run multiple arenas with different rules (like size or cycles).
    *   **Important**: All list settings (like `CORESIZE_LIST`, `CYCLES_LIST`) must be the same length.
    *   Update `LAST_ARENA` to match the index of your last arena. For example, if you have 8 arenas (0 to 7), set `LAST_ARENA=7`.
2.  **Time**: Set `CLOCK_TIME` to how many hours you want the script to run.
3.  **Starting Fresh vs. Continuing**:
    *   **Start New**: Set `ALREADYSEEDED = False`. This creates random warriors to start.
    *   **Resume**: Set `ALREADYSEEDED = True`. This keeps your current warriors and continues evolving them.
4.  **Optimization**: Set `FINAL_ERA_ONLY = True` (and `ALREADYSEEDED = True`) to skip the chaotic early phases and just fine-tune your warriors.

## How to Run

1.  Check `settings.ini` to make sure it's set up how you want.
2.  Open your terminal or command prompt in the project folder.
3.  **Validate your setup**: Before starting a long run, check that everything is correct (settings, file paths, simulator).
    ```bash
    python evolverstage.py --check
    ```
    If it says "Configuration and environment are valid," you are good to go.

4.  **Run the script**:
    ```bash
    python evolverstage.py
    ```
    *   **Tip**: To see the exact settings the script is using (including defaults), run:
        ```bash
        python evolverstage.py --dump-config
        ```

5.  **Watch the Progress**: You will see output like this:
    ```text
    8.00 hours remaining (0.01% complete) Era: 1
    ```
6.  **Get Results**: When it's done (or if you stop it), look in the `arenaX` folders (like `arena0`) for the `.red` files. These are your evolved warriors.
7.  **Find the Best**: Use the built-in benchmark tool (see **Command Line Tools**) to test the final warriors against each other to find the champion.

## Command Line Tools

You can do more than just evolve warriors. The script includes tools to run battles, tournaments, and benchmarks.

### Manage Evolution
*   **Status**: `python evolverstage.py --status`
    *   Shows the current state of evolution, including population size and average warrior length for each arena. Add `--json` for machine-readable output.
*   **Force Restart**: `python evolverstage.py --restart`
    *   Starts from scratch (Era 1), overwriting any existing warriors in the arenas.
*   **Resume**: `python evolverstage.py --resume`
    *   Continues from where you left off, even if `settings.ini` says otherwise.

### Run Battles
*   **Single Battle**: Run one fight between two warriors.
    ```bash
    python evolverstage.py --battle warriors/warrior1.red warriors/warrior2.red
    ```
*   **Tournament**: Run a round-robin tournament between all warriors in a folder.
    ```bash
    python evolverstage.py --tournament warriors/
    ```
*   **Benchmark**: Test one warrior against a folder of opponents to see how good it is.
    ```bash
    python evolverstage.py --benchmark my_warrior.red warriors/
    ```
*   **Normalize**: Clean up a warrior's code or an entire directory to match the arena's standards.
    ```bash
    python evolverstage.py --normalize my_warrior.red
    # Normalize a whole directory to an output folder
    python evolverstage.py --normalize warriors/ -o cleaned_warriors/
    ```

**Note**: You can add `--arena N` (e.g., `--arena 1`) to most commands to use the rules of a specific arena. The default is Arena 0.

## Output Explained

### Warrior Files

*   **Arenas (`arena0/`, `arena1/`, ...)**: The current population. Each file (e.g., `15.red`) is a warrior.
*   **Archive (`archive/`)**: A backup of winning warriors. This saves good strategies so they aren't lost.

### Battle Log

If you set a filename for `BATTLE_LOG_FILE` in `settings.ini`, the script saves every battle result to a CSV file.
*   **era**: Evolution phase (0, 1, or 2).
*   **arena**: Which arena the fight happened in.
*   **winner/loser**: The IDs of the warriors.
*   **score1/score2**: The score from nMars.
*   **bred_with**: The ID of the partner warrior used to make the new warrior.

## Running Tests

To ensure the code is working correctly, you can run the included test suite. This is recommended if you plan to modify the code.

### Using unittest (Standard Library)
Most tests can be run using Python's built-in testing framework without installing additional packages:
```bash
python -m unittest discover tests
```

### Using pytest (Recommended)
For full coverage (including tests that require external fixtures), we recommend using `pytest`:
1.  **Install pytest**:
    ```bash
    pip install pytest
    ```
2.  **Run the tests**:
    ```bash
    pytest
    ```
The tests verify the logic for evolution, parsing, and battle execution (using a mock simulator), so you don't need `nMars` installed to run them.

## Features

*   **Multi-Arena**: Warriors can fight in different environments at the same time. Code that works well in one arena can be "sanitized" (adjusted) and moved to another.
*   **Smart Selection**: The evolver prefers useful instructions (like `MOV` and `SPL`) and efficient numbers.
*   **Eras**: Evolution happens in three stages:
    1.  **Exploration (Era 1)**: High mutation. Tries many different things.
    2.  **Breeding (Era 2)**: Winners breed more often. Combines good parts of different warriors.
    3.  **Optimization (Era 3)**: Fine-tuning. Changes small numbers to perfect the code.
*   **Mutation Strategies**: The "Bag of Marbles" system randomly picks how to change a warrior:
    *   **Do Nothing**: Keep it the same.
    *   **Major Mutation**: Create a totally new random instruction.
    *   **Nab Instruction**: Steal code from another arena.
    *   **Mini/Micro Mutation**: Change a small part of an instruction.
    *   **Magic Number**: Use a specific number known to be good.
