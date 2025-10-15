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
-returns strings that begin with `"ERROR:"` when invalid warriors or parameters are detected. The Python runner treats these as
 fatal errors and raises an exception so the run halts cleanly.

**Both the Python and CPP should gracefully exit or throw an exception if there is an error or unexpected input. If the program exits, the last-known good warriors are still on the disk and nothing is lost. If the program does things like declaring battles a draw, or making assumptions about the redcode that are not what is actually written, it could corrupt the whole run.**

Testing requirements:

- Run the full Python and C++ test suites with `pytest tests/test_evolverstage.py tests/test_redcode_worker.py` before finishing.

Adherence to spec:

Not supported:
-Battles between more than 2 warriors at a time.
-ORG pseudo-opcode: All of the warriors being evolved start at the first instruction to be easier to combine. If the Python or CPP encounters one, an error should be raised and the run halted.
-LDP/STP opcodes: Listed in the extended draft, but it doesn't work well with evolution, so not supported

Supported:
-Read/Write limits: enforced in both the Python and C++ implementations. Configuration files that request limits outside the core size are rejected during validation.
-JMN.I/DJN.I: we mirror the EMI94 reference implementation's "logical OR" semantics for multi-field tests. This matches the upstream test suite and avoids surprising contributors who compare against EMI94 or pMars.
-NOP: in the Extended spec, so it is supported.
-SNE, SEQ: in the Extended spec, so it is supported. SEQ is an alias for CMP, but CMP is more commonly used, so SEQ will be accepted as input, but internally only CMP is used.
-`{`, `}` and `*` modes: in the Extended spec, so it is supported.

Submodules:
-The official latest pMars source code has been included under pMars. It may be a future project to add it as an alternate emulation engine. For now, it can be compiled or browsed to resolve ambiguities about intended execution.
-Instruction semantics should match pMARS. When adding or updating instruction-level tests, treat pMARS as the reference implementation and prefer its behaviour over existing expectations if they disagree.
