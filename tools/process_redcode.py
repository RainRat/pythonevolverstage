#!/usr/bin/env python3
"""
Utility to process pMARS-assembled Redcode files.

This script can operate in two modes:

1. 'combine': Reads one or more assembled warrior files, extracts all unique
   instructions (stripping labels and directives), and writes a single,
   sorted, deduplicated library.

2. 'strip': Reads one or more assembled warrior files and cleans each one
   individually, saving the result to a new file with a new extension.
   This mode can optionally preserve labels and directives.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import Iterable, Set, List, Optional
# Base opcodes supported by the evolver (from script 1)
_VALID_BASE_OPCODES = {
    "DAT", "MOV", "ADD", "SUB", "MUL", "DIV", "MOD",
    "JMP", "JMZ", "JMN", "DJN", "CMP", "SEQ", "SNE",
    "SLT", "SPL", "NOP",
}

# Pseudo-opcodes (from script 1)
_PSEUDO_OPS = {"ORG", "END"}

# All valid opcodes and pseudo-ops
_ALL_OPS = _VALID_BASE_OPCODES.union(_PSEUDO_OPS)


def format_instruction_operands(instruction_part: str) -> str:
    """
    Cleans up the operands of a line that is *already*
    just an instruction (no label).
    e.g., "MOV.I @ 75, { 79" -> "MOV.I @75, {79"
    e.g., "JMP START" -> "JMP START"
    (Function from script 2)
    """
    if ',' in instruction_part:
        # Two-operand instruction (e.g., MOV.I @ 75, { 79)
        try:
            comma_parts = instruction_part.split(',', 1)
            part_a = comma_parts[0]
            part_b = comma_parts[1]
            
            # Split opcode from first operand
            opcode_parts = part_a.split(None, 1)
            if len(opcode_parts) < 2:
                # Malformed line, e.g., " , 1"
                return f"Error: Bad format on line: {instruction_part}"

            opcode = opcode_parts[0]
            # Remove all spaces from A-field
            a_field = opcode_parts[1].replace(' ', '')
            
            # Remove all spaces from B-field after stripping
            b_field = part_b.strip().replace(' ', '')
            
            # Reconstruct with a single space after comma
            return f"{opcode} {a_field}, {b_field}"
            
        except Exception:
            return f"Error: Failed to parse 2-operand line: {instruction_part}"
            
    else:
        # One or zero-operand instruction (e.g., JMP START or NOP)
        op_parts = instruction_part.split(None, 1)
        
        if len(op_parts) == 1:
            # Zero-operand (e.g., NOP)
            return op_parts[0]
        elif len(op_parts) == 2:
            # One-operand (e.g., JMP START or DAT 0)
            opcode = op_parts[0]
            # Remove all spaces from the operand
            a_field = op_parts[1].replace(' ', '')
            return f"{opcode} {a_field}"
        else:
            # Should be an empty string, but check for safety
            return instruction_part # Return as-is


def clean_instruction_line(line: str, keep_directives: bool) -> str | None:
    """
    Cleans a single line of redcode assembly.
    (Combined logic from script 1 and 2)
    
    If keep_directives is False:
      Removes labels, comments, directives, and extra whitespace.
      e.g., " START SPL.B # 53, < 37" -> "SPL.B #53, <37"
      
    If keep_directives is True:
      Keeps labels and directives, but still cleans operands.
      e.g., " START SPL.B # 53, < 37" -> "START  SPL.B #53, <37"
    """
    
    # Remove trailing comments and whitespace.
    line_no_comment, *_ = line.split(";", 1)
    stripped_line = line_no_comment.strip()
    
    # Skip empty lines or pMARS headers/footers
    if (not stripped_line or
        stripped_line.startswith('Program') or
        'scores' in stripped_line):
        return None

    # --- Logic to separate label from instruction ---
    
    parts = stripped_line.split(None, 1)
    if not parts:
        return None
        
    first_word = parts[0]
    label_part: str | None = None
    instruction_part: str | None = None
    
    # Check if the first word is an opcode or pseudo-op
    base_op = first_word.split(".", 1)[0].upper()

    if base_op in _ALL_OPS:
        # No label
        label_part = None
        instruction_part = stripped_line
    else:
        # First word is NOT an opcode. Assume it's a label.
        label_part = first_word
        if len(parts) < 2:
            instruction_part = None # Line had only a label (e.g., "START")
        else:
            instruction_part = parts[1].strip()

    # --- Validation and Re-assembly ---
    
    # Case 1: We have an instruction part
    if instruction_part:
        instruction_words = instruction_part.split(None, 1)
        if not instruction_words:
            # e.g., line was "START " (label with empty space)
            instruction_part = None
        else:
            potential_opcode = instruction_words[0]
            base_pot_op = potential_opcode.split(".", 1)[0].upper()
            
            # Check if it's a pseudo-op
            if base_pot_op in _PSEUDO_OPS:
                if not keep_directives:
                    return None  # Skip ORG/END if not keeping directives
                # Keep directive as-is, but clean operands
                formatted_instruction = format_instruction_operands(instruction_part)
            
            # Check if it's a valid opcode
            elif base_pot_op in _VALID_BASE_OPCODES:
                # Format the instruction (e.g., "MOV.I @ 75, { 79")
                formatted_instruction = format_instruction_operands(instruction_part)
            
            # Check if it's junk (like "Recon 2 by...")
            else:
                # The part *after* the "label" is not an opcode.
                # This is a junk line.
                label_part = None
                instruction_part = None
                return None

        if "Error:" in formatted_instruction:
            print(f"Warning: {formatted_instruction}", file=sys.stderr)
            return None # Skip bad lines

        if keep_directives and label_part:
            # Re-add the label with standard spacing
            return f"{label_part}  {formatted_instruction}"
        else:
            # Just return the formatted instruction
            return formatted_instruction
            
    # Case 2: No instruction, but we found a label (e.g., "START")
    elif label_part and keep_directives:
        return label_part # Return the label on its own
        
    # Case 3: No instruction, and we don't care about directives
    else:
        return None


def run_combine_mode(paths: Iterable[Path], output: Path | None) -> None:
    """
    Read all input paths and write a sorted, deduplicated instruction list
    to the single output file (or stdout).
    (Logic from script 1)
    """
    print("Mode: combine. Building instruction library...")
    instructions: Set[str] = set()
    for file_path in paths:
        if not file_path.is_file():
            print(f"Warning: '{file_path}' is not a file. Skipping.")
            continue
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    # 'combine' mode *always* strips directives
                    instruction = clean_instruction_line(line, keep_directives=False)
                    if instruction is not None:
                        instructions.add(instruction)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            
    library = sorted(instructions)
    
    output_text = "\n".join(library) + "\n"

    if output is None:
        # Write to standard output
        print(output_text, end='')
        print(f"Done. Wrote {len(library)} unique instructions to stdout.")
    else:
        # Write to output file
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(output_text, encoding="utf-8")
            print(f"Done. Wrote {len(library)} unique instructions to {output}.")
        except Exception as e:
            print(f"Error writing to {output}: {e}")


def run_strip_mode(paths: Iterable[Path], ext: str, keep_directives: bool) -> None:
    """
    Read all input paths and write a new '.cleaned' file for each one.
    (Logic from script 2, modified for directive handling)
    """
    print(f"Mode: strip. Keeping directives: {keep_directives}.")
    processed_count = 0
    if not ext.startswith('.'):
        ext = '.' + ext
        
    for file_path in paths:
        if not file_path.is_file():
            print(f"Warning: '{file_path}' is not a file. Skipping.")
            continue

        print(f"Processing {file_path}...")
        
        # --- MODIFIED: Add flags ---
        found_start_label = False
        found_org_start = False
        new_lines: List[str] = []
        
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as f_in:
                for line in f_in:
                    cleaned_line = clean_instruction_line(line, keep_directives)
                    if cleaned_line:
                        new_lines.append(cleaned_line)
                        
                        # --- NEW: Check for flags if --keep-directives is on ---
                        if keep_directives:
                            # Check for 'START' as the first word (label)
                            # Catches both "START" and "START  MOV..."
                            if (cleaned_line.upper() == "START" or 
                                cleaned_line.upper().startswith("START ")):
                                found_start_label = True
                            
                            # Check for "ORG START"
                            if cleaned_line.upper() == "ORG START":
                                found_org_start = True
            
            # --- NEW: Post-processing logic ---
            # This block runs *after* the whole file is read, but *before* writing
            final_lines = new_lines # Default to the list we just built

            if keep_directives and found_start_label:
                # 1. Filter out any 'END START' lines
                processed_lines = [
                    ln for ln in new_lines 
                    if ln.upper() != "END START"
                ]
                
                # 2. Add 'ORG START' at the beginning if it wasn't found
                if not found_org_start:
                    processed_lines.insert(0, "ORG START")
                
                final_lines = processed_lines # Use the modified list
            # --- END NEW ---

            if final_lines: # <-- Use final_lines
                # Use .with_suffix to handle files with existing extensions
                new_filename = file_path.with_suffix(ext)
                
                # Handle case where foo.txt becomes foo.cleaned
                if str(new_filename) == str(file_path):
                     new_filename = Path(f"{file_path}{ext}")
                
                with open(new_filename, 'w', encoding='utf-8') as f_out:
                    f_out.write("\n".join(final_lines) + "\n") # <-- Use final_lines
                
                print(f"-> Created {new_filename}")
                processed_count += 1
            else:
                print(f"-> No relevant lines found in {file_path}.")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
    if processed_count == 0:
        print("\nNo files were processed.")
    else:
        print(f"\nDone. Processed {processed_count} files.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process pMARS-assembled Redcode files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Combine all .red files into a single library.txt\n"
            "  python process_redcode.py --mode combine -o library.txt *.red\n\n"
            "  # Strip all .asm files, creating .cleaned files (e.g., foo.asm -> foo.cleaned)\n"
            "  python process_redcode.py --mode strip *.asm\n\n"
            "  # Strip a file, keeping directives, and output to .rc file\n"
            "  python process_redcode.py --mode strip --keep-directives --ext .rc warrior.red"
        )
    )
    
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more input files to process."
    )
    
    parser.add_argument(
        "--mode",
        choices=['combine', 'strip'],
        required=True,
        help=(
            "'combine': Create a single, deduplicated instruction library.\n"
            "'strip': Clean each file individually into a new file."
        )
    )
    
    # Options for 'combine' mode
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Destination file for 'combine' mode. If omitted, "
            "the library is written to standard output."
        )
    )
    
    # Options for 'strip' mode
    parser.add_argument(
        "--ext",
        default='.cleaned',
        help="File extension to use for 'strip' mode (default: .cleaned)"
    )
    parser.add_argument(
        "--keep-directives",
        action='store_true',
        help="For 'strip' mode: preserve labels and directives (ORG, END, START)."
    )

    args = parser.parse_args()
    
    # --- NEW: Expand file globs (like *.txt) ---
    expanded_inputs = []
    for input_pattern in args.inputs:
        # Use glob.glob to find matching files.
        matched_files = glob.glob(str(input_pattern))
        if not matched_files:
            print(f"Warning: No files matched pattern '{input_pattern}'. Skipping.", file=sys.stderr)
        else:
            # Add all matched files as Path objects
            expanded_inputs.extend([Path(f) for f in matched_files])
    
    if not expanded_inputs:
        print("Error: No valid input files found after expanding patterns.", file=sys.stderr)
        sys.exit(1)
    # --- END NEW ---

    # --- Validate arguments based on mode (now uses expanded_inputs) ---
    if args.mode == 'combine':
        if args.keep_directives:
            parser.error("--keep-directives is only valid with --mode strip")
        if args.ext != '.cleaned':
             parser.error("--ext is only valid with --mode strip")
        # Use the new expanded list
        run_combine_mode(expanded_inputs, args.output)
        
    elif args.mode == 'strip':
        if args.output:
            parser.error("--output (-o) is only valid with --mode combine")
        # Use the new expanded list
        run_strip_mode(expanded_inputs, args.ext, args.keep_directives)


if __name__ == "__main__":
    main()
