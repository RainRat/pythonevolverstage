;redcode
;name      JMN_DJN_Logic_Test
;author    Gemini
;strategy
; Tests the ambiguity between the ICWS'94 spec text (AND logic) and
; the reference EMI94.c implementation (OR logic) for JMN.I and DJN.I.
;
; After execution, inspect the B-fields of the flag instructions:
; 1 -> Detected OR logic (EMI94.c compliant)
; 2 -> Detected AND logic (Spec text compliant)

            ORG     start

; --- Data section for flags and test targets ---
flag_jmn_result DAT.F   #0, #0      ; Result for JMN test will be stored here.
flag_djn_result DAT.F   #0, #0      ; Result for DJN test will be stored here.

jmn_target      DAT.F   #1, #0      ; Target for JMN.I. Has one non-zero field.
djn_target      DAT.F   #1, #2      ; Target for DJN.I.

; --- Code section ---
start:
; --- JMN Test ---
; We test JMN.I against jmn_target (DAT #1, #0).
; OR logic  (1!=0 || 0!=0) is TRUE  -> Jumps to jmn_is_or
; AND logic (1!=0 && 0!=0) is FALSE -> Falls through to jmn_is_and
            JMN.I   jmn_is_or, jmn_target

jmn_is_and:
            MOV.B   #2, flag_jmn_result ; Set flag to 2 for AND logic.
            JMP     djn_test            ; Continue to the next test.

jmn_is_or:
            MOV.B   #1, flag_jmn_result ; Set flag to 1 for OR logic.

djn_test:
; --- DJN Test ---
; We test DJN.I against djn_target (DAT #1, #2).
; 1. The instruction at djn_target is decremented to DAT #0, #1.
; 2. The new values (0 and 1) are tested.
; OR logic  (0!=0 || 1!=0) is TRUE  -> Jumps to djn_is_or
; AND logic (0!=0 && 1!=0) is FALSE -> Falls through to djn_is_and
            DJN.I   djn_is_or, djn_target

djn_is_and:
            MOV.B   #2, flag_djn_result ; Set flag to 2 for AND logic.
            JMP     halt                ; End of tests.

djn_is_or:
            MOV.B   #1, flag_djn_result ; Set flag to 1 for OR logic.

halt:
; Execution stops here. Inspect the core at the flag locations.
            DAT.F   #0, #0

            END     start

;---

;Result from running in pMars reference implementation:

;00000   DAT.F  #     0, #    -7
;00001   DAT.F  #     0, #   -10
;00002   DAT.F  #     1, #     0
;00003   DAT.F  #     0, #     1
;00004   JMN.I  $     3, $    -2
;00005   MOV.B  #     2, $    -5
;00006   JMP.B  $     2, $     0
;00007   MOV.B  #     1, $    -7
;00008   DJN.I  $     3, $    -5
;00009   MOV.B  #     2, $    -8
;00010   JMP.B  $     2, $     0
;00011   MOV.B  #     1, $   -10
;00012   DAT.F  #     0, #     0
