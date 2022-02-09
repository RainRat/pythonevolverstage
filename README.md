# Python Core War Evolver

An Evolver for Core War, written in Python. You will need probably need to edit the Python code to do what you want. But you don't need to know Redcode (the language used in Core War).

A genetic algorithm will pit the warriors against each other, then breed the winner, with some random mutation.

##Usage:

For all of these, modify the constants at the beginnning of the program.

1. Edit the ARENA lists to contain the parameters of the competitions you want to compete in. If you just want to compete in one arena, you have lists of length 1.
2. Set ALREADYSEEDED to False. If you interrupt it and want to resume, set it to True.
3. Choose how much actual wall clock time (in hours) you plan to run the project for and modify CLOCK_TIME

##Special Features:

1. Evolve warrior to compete in multiple arenas at once. This is beneficial because useful instructions can be nabbed by warriors for use in other arenas.
	- A Sanitizer will chop the numerical values down to something that makes sense in the smaller core if needed. This was also used in Round 3 of the Global Masters Tournament.
2. Bias towards picking more useful instructions.
3. Bias towards picking small numbers (likely inside the warrior) (3 out of 4 chance).
4. Eras and wall clock time. Before you start, you decide how long you want to run the evolver for. Let's say 24 hours. It'll divide this time into 3 eras.
	- Exploration (single cell)
		The primary activity of this phase is warriors reproducing themselves with mutation. One round of battle determines the winner. Single-celled organisms die easily but they will many near-clones. A random mate is still selected but the offspring will start with instructions from the winner and there's a lower chance of switching to getting instructions from the other warrior.
	- Breeding (multicellular)
		The primary activity of this phase is to use breeding to combine features of different warriors. They will fight for more rounds before declaring the winner. How breeding works: The winner, and a random warrior, are loaded side by side. Starting from a random warrior from those two, instructions are copied into the new warrior. Each instruction, there's a chance of switching to reading instructions from the other warrior. So the goal is alternating sections of instructions from each parent.
	- Optimization (complex life)
		The primary activity of this phase is to fine tune constants and other behaviour. Warriors fight for even more rounds to determine the winner. Mutation is lower, and while breeding, larger chunks are copied into the new warrior.