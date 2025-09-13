Evolutionary algorithm for the competitive programming game Core War.

Currently evolverstage.py shells to the external program nMars.exe, but an experimental C++ server, redcode-worker.cpp, is under development.

"spec" refers to the "Draft of Proposed 1994 Core War Standard" (1994_core_war_standard.txt) + the features in the Extended draft (1994_extended.txt)

The Python program:
-Expects to receive programs that are already assembled, with all fields present, like:
```
MOV.I {-3,*-3
```
-Making sure all operands and labels have been resolved to literal numbers.
-Enforcing Warrior Length Limit.
-Making sure all instructions have all operands.
-Making sure all opcodes used are in the spec.
-So, these things should be checked during input, and then not do anything that could break those rules.
-It shouldn't normally send invalid code to the cpp, but if it receives invalid code, it can choose whether to gracefully exit or throw an exception.

The cpp program:
-should safely exit if it encounters a problem, but is not responsible for making assumptions about what was intended.

-Don't worry about supporting battles between more than 2 warriors at a time.
-None of the tourneys use Read/Write limits, so that can be skipped
-All of the warrior start at the first instruction, so there is no need to use the ORG pseudo-opcode, so that can be skipped.
