# Python Core War Evolver

An Evolver for Core War, written in Python. You don't need to know Redcode (the language used in Core War) to use this tool.

This project uses a genetic algorithm to pit warriors against each other, breed the winners, and introduce mutations to evolve superior strategies over time.

Contributions are welcome! If you have a suggestion or improvement, please submit a pull request.

## Prerequisites

Before running the evolver, ensure you have the following:

*   **Python 3.x**: This project is written in Python.
*   **nMars**: The `nmars` Core War simulator must be installed and accessible.
    *   The executable (`nmars.exe` on Windows, `nmars` on Linux/macOS) should be in your system's PATH or placed in the root directory of this project.

## Configuration

All settings are managed in `settings.ini`. Open this file to customize the evolution parameters.

1.  **Arenas**: Edit the list-based parameters (e.g., `CORESIZE_LIST`, `CYCLES_LIST`) to define the environments. All lists must be the same length, corresponding to the number of arenas.
2.  **Duration**: Set `CLOCK_TIME` to the number of hours you want the evolution to run.
3.  **Seeding**:
    *   **First Run**: Set `ALREADYSEEDED = False`. This generates a new random population of warriors.
    *   **Resuming**: Set `ALREADYSEEDED = True`. This preserves the existing warriors and continues evolution from where it left off.
4.  **Optimization Mode**: Set `FINAL_ERA_ONLY = True` (and `ALREADYSEEDED = True`) to skip directly to the optimization phase. This is useful for fine-tuning an existing population.

## Usage

1.  Configure `settings.ini` as described above.
2.  Run the script:
    ```bash
    python evolverstage.py
    ```
3.  Monitor the output. The script will display progress, including the current Era and time remaining.
    ```text
    8.00 hours remaining (0.01% complete) Era: 1
    ```
4.  **Results**: When the process finishes (or is stopped), you can find the evolved warriors in the `arenaX` directories.
5.  **Selection**: Use a benchmarking tool (like CoreWin in round-robin mode) to test the final population and identify the best warriors.

## Output and Analysis

As the evolver runs, it generates several types of output:

### Warrior Files

*   **Arenas (`arena0/`, `arena1/`, ...)**: These directories contain the active population of warriors. Each warrior is a `.red` file (Redcode source), named by its ID (e.g., `15.red`).
*   **Archive (`archive/`)**: Successful warriors (winners) are occasionally copied here. This preserves a history of effective strategies and allows for re-introduction of genetic material later.

### Battle Log

If `BATTLE_LOG_FILE` is set in `settings.ini`, a CSV file is created to track every match. This is useful for analyzing evolution progress. The columns are:

*   **era**: The current phase of evolution (0, 1, or 2).
*   **arena**: The arena number where the battle took place.
*   **winner**: The ID of the winning warrior.
*   **loser**: The ID of the losing warrior (this warrior is subsequently overwritten).
*   **score1 / score2**: The scores returned by `nmars`.
*   **bred_with**: The ID of the warrior chosen to breed with the winner. The offspring of this pair replaces the loser.

## Special Features

*   **Multi-Arena Evolution**: Warriors can compete in multiple arenas simultaneously. Successful instructions from one environment can be adapted ("sanitized") and transferred to another.
*   **Smart Selection Bias**:
    *   Preference for useful instructions (MOV, SPL, DJN).
    *   Preference for small numbers (keeping references inside the warrior).
*   **Eras**: The evolution is divided into three phases based on `CLOCK_TIME`:
    1.  **Exploration (Era 1)**: High mutation, distinct winners. Focus on reproducing viable code.
    2.  **Breeding (Era 2)**: Winners breed with other warriors. Instructions are mixed to combine features.
    3.  **Optimization (Era 3)**: Fine-tuning of constants. Larger code chunks are preserved during breeding.
*   **Evolution Strategies ("Bag of Marbles")**: The probability of different mutation types changes over time. Strategies include:
    *   **Do Nothing**: Keep instruction as is.
    *   **Major Mutation**: New random instruction.
    *   **Nab Instruction**: Steal an instruction from another arena.
    *   **Mini Mutation**: Change one part of an instruction.
    *   **Micro Mutation**: Increment/decrement a value (fine-tuning).
    *   **Instruction Library**: Insert a predefined effective instruction (requires an external library file).
    *   **Magic Number**: Replace a value with a pre-selected "magic number" that optimizes relative addressing.
*   **Archiving**: Winners are occasionally archived. Losers can be replaced by unarchived warriors to reintroduce genetic diversity and prevent stagnation.
*   **Value Normalizer**: Rewrites instruction modifiers to be more readable (e.g., converting large offsets to their negative equivalents).
*   **Logging**: Set `BATTLE_LOG_FILE` in `settings.ini` to save match results to a CSV file for analysis.
