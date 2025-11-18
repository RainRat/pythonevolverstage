#!/usr/bin/env python3
"""
Scans a folder of Redcode files to find any files that contain
opcodes without a modifier (e.g., "MOV" instead of "MOV.I").
"""

import argparse
import glob
import sys
from pathlib import Path

# Opcodes that *must* have a modifier (e.g., .I, .A, .B)
OPCODES_REQUIRING_MODS = {
    'MOV',
    'ADD',
    'SUB',
    'MUL',
    'DIV',
    'MOD',
    'JMP',
    'JMZ',
    'JMN',
    'DJN',
    'CMP',  # Alias for SEQ
    'SEQ',
    'SNE',
    'SLT',
    'SPL',
    'DAT',
    'NOP'
}

# Pseudo-ops that look like opcodes but are fine without modifiers
PSEUDO_OPS = {'ORG', 'END'}


def find_unspecified_opcode(raw_line: str, line_num: int) -> tuple[str, int] | None:
    """
    Parses a line and returns the (opcode, line_num) if it finds
    an opcode that is missing a required modifier.
    
    e.g., "MOV >-30,<-2" -> ("MOV", 10)
    e.g., "MOV.I >-30,<-2" -> None
    """
    # Remove comments and whitespace
    line, *_ = raw_line.split(";", 1)
    stripped = line.strip()
    if not stripped:
        return None
    
    parts = stripped.split()
    
    for part in parts:
        key = part.upper()
        
        # 1. Check if it's an opcode that requires a modifier
        if key in OPCODES_REQUIRING_MODS:
            # This is a direct hit, e.g., the token is "MOV"
            return (key, line_num)
            
        # 2. Check if it *has* a modifier, e.g., "MOV.I"
        if '.' in key:
            base, _mod = key.split(".", 1)
            base = base.upper()
            if base == 'CMP': # Handle alias
                base = 'SEQ'
            
            # If the base is a required opcode, this line is
            # *correctly* specified. We can stop checking this line.
            if base in OPCODES_REQUIRING_MODS:
                return None
        
        # 3. Check for pseudo-ops like 'ORG'
        if key in PSEUDO_OPS:
            # This line is fine, stop checking it.
            return None

    # No unspecified opcodes found on this line
    return None


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Find Redcode files with unspecified opcodes "
            "(e.g., 'MOV' instead of 'MOV.I')."
        )
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="The folder to scan for files."
    )
    parser.add_argument(
        "--ext",
        nargs="+",
        default=[".red"],
        help="File extension(s) to check (e.g., .red .asm .txt)"
    )
    
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"Error: '{args.folder}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    # 1. Find all files to check
    files_to_check = []
    for ext in args.ext:
        # Use glob to find all matching files
        pattern = str(args.folder / f"*{ext}")
        files_to_check.extend(glob.glob(pattern))

    if not files_to_check:
        print(f"No files found in '{args.folder}' with extensions: {args.ext}")
        return

    print(f"Scanning {len(files_to_check)} files for missing modifiers...\n")
    
    files_with_errors = []

    # 2. Process each file
    for filepath_str in files_to_check:
        filepath = Path(filepath_str)
        
        try:
            with filepath.open("r", encoding="utf-8", errors="ignore") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    error = find_unspecified_opcode(line, line_num)
                    
                    if error:
                        op, ln = error
                        print(
                            f"Found file with unspecified opcode: {filepath.name}\n"
                            f"  - Line {ln}: Found '{op}' without a modifier.\n"
                        )
                        files_with_errors.append(filepath.name)
                        # No need to scan the rest of this file
                        break 

        except Exception as e:
            print(f"Could not read {filepath.name}: {e}")
            continue
    
    # 3. Print summary
    print("---")
    if not files_with_errors:
        print("✅ All scanned files seem to be fully specified.")
    else:
        print(f"🚨 Found {len(files_with_errors)} file(s) with unspecified opcodes:")
        # Use set() to only list each filename once
        for fname in sorted(list(set(files_with_errors))):
            print(f"  - {fname}")


if __name__ == "__main__":
    main()