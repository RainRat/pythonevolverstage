Evolutionary algorithm for the competitive programming game Core War.

Currently evolverstage.py supports:
 - shells to the external program nMars.exe.
 - shells to the external program pMars (source included in pMars/)
 - and the internal C++ server (`redcode-worker.cpp`)

"spec" refers to the "Draft of Proposed 1994 Core War Standard" (1994_core_war_standard.txt) + the features in the Extended draft (1994_extended.txt)

Configuration overrides belong in `settings.ini` as the single source of truth. Command-line flags are only `--config`, `--seed`, and `--verbosity`. Do not add more command-line flags unless specifically requested.

Do not write in user-facing docs that a feature is "new", or write in code comments that a method uses a "new way". Such references become obsolete. Remove them if seen.

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
- Do not commit empty `arena(n)/` or `archive/` folders. (They would just initially mislead the user about whether the arenas are already seeded and whether an archive is included with the repo.)

Adherence to spec:

Not supported:
-Battles between more than 2 warriors at a time.
-ORG pseudo-opcode: All of the warriors being evolved start at the first instruction to be easier to combine.
-END pseudo-opcode: Not required.
-In the cpp worker, ORG START with a single opcode labelled START is now supported to run benchmarks. The python code will not produce any warriors that use ORG. No other pseudo-opcodes or usage of labels is supported by the cpp worker.
-LDP/STP opcodes: Listed in the extended draft, but it doesn't work well with evolution, so not supported. If one is encountered in the Python module (ie. from the archive or instruction library): it can be replaced with a placeholder, or reselected as desired. If one is encountered in the C++ module, the standard unknown opcode error should be raised and the run halted.

Supported:
-Read/Write limits: enforced in both the Python and C++ implementations.
-JMN.I/DJN.I: we mirror the EMI94 reference implementation's "logical OR" semantics for multi-field tests. This matches the upstream test suite and avoids surprising contributors who compare against EMI94 or pMars.
-NOP: in the Extended spec, so it is supported.
-SNE, SEQ: in the Extended spec, so it is supported. SEQ is an alias for CMP, but CMP is more commonly used, so SEQ will be accepted as input, but internally only CMP is used.
-`{`, `}` and `*` modes: in the Extended spec, so it is supported.

Submodules:
-The official latest pMars source code has been included under pMars. Using it as an external battle program is supported, and it can also be compiled or browsed to resolve ambiguities about intended execution.
-Instruction semantics should match pMARS. When adding or updating instruction-level tests, treat pMARS as the reference implementation and prefer its behaviour over existing expectations if they disagree.

Debugging the C++ worker:

-To enable detailed instruction-level tracing, set the `DEBUG_TRACE` CMake option to `ON`. For example: `cmake .. -DDEBUG_TRACE=ON`.
-Set the `REDCODE_TRACE_FILE` environment variable to a filename. For example: `export REDCODE_TRACE_FILE=trace.log`.
-When the worker runs, it will append a log of every instruction executed to that file.
-This option is off by default because it has a significant performance cost.
