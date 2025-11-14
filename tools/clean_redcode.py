
import os
import sys

def format_instruction_operands(instruction_part):
    """
    Cleans up the operands of a line that is *already*
    just an instruction (no label).
    e.g., "MOV.I @ 75, { 79" -> "MOV.I @75, {79"
    e.g., "JMP START" -> "JMP START"
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


def clean_instruction_line(line, keep_labels=False):
    """
    Cleans a single line of redcode assembly.
    
    If keep_labels is False:
      Removes labels, comments, directives, and extra whitespace.
      e.g., " START SPL.B # 53, < 37" -> "SPL.B #53, <37"
      
    If keep_labels is True:
      Keeps labels and directives, but still cleans operands.
      e.g., " START SPL.B # 53, < 37" -> "START  SPL.B #53, <37"
    """
    
    stripped_line = line.strip()
    
    # Skip empty lines
    if not stripped_line:
        return None
        
    # --- MODIFIED ---
    # Skip comments or headers.
    # Directives (ORG, END) are now conditional on 'keep_labels'
    if (stripped_line.startswith(';') or 
        stripped_line.startswith('Program')):
        return None
    
    if (not keep_labels and 
        (stripped_line.startswith('ORG') or stripped_line.startswith('END'))):
        return None

    # --- NEW LOGIC TO SEPARATE LABEL FROM INSTRUCTION ---
    
    # Opcodes that don't use a '.' modifier.
    # ORG and END are included to treat them as instructions.
    known_opcodes = {'DAT', 'JMP', 'JMN', 'JMZ', 'NOP', 'ORG', 'END'}
    
    parts = stripped_line.split(None, 1)
    if not parts:
        return None
        
    first_word = parts[0]
    label_part = None
    instruction_part = None

    # Check if the first word is an opcode
    if '.' in first_word or first_word.upper() in known_opcodes:
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

    # --- VALIDATION (from previous fix) ---
    # If we have what we *think* is an instruction, validate it.
    if instruction_part:
        instruction_words = instruction_part.split(None, 1)
        if not instruction_words:
             # e.g., line was "START " (label with empty space)
            instruction_part = None
        else:
            potential_opcode = instruction_words[0]
            # Check if the part *after* the label is a valid opcode
            if not ('.' in potential_opcode or potential_opcode.upper() in known_opcodes):
                # This is the "Recon 2 by..." line.
                # The part after "Recon" ("2") is not an opcode.
                # Discard the whole line.
                label_part = None
                instruction_part = None

    # --- RE-ASSEMBLY ---
    
    # Case 1: We have an instruction part
    if instruction_part:
        formatted_instruction = format_instruction_operands(instruction_part)
        
        if "Error:" in formatted_instruction:
            return formatted_instruction # Propagate error

        if keep_labels and label_part:
            # Re-add the label with standard spacing
            return f"{label_part}  {formatted_instruction}"
        else:
            # Just return the formatted instruction
            return formatted_instruction
            
    # Case 2: No instruction, but we found a label (e.g., "START")
    elif label_part and keep_labels:
        return label_part # Return the label on its own
        
    # Case 3: No instruction, and we don't care about labels
    else:
        return None


def process_files_in_directory(keep_labels_and_org):
    """
    Reads all files in the current directory, cleans them,
    and writes the result to new files with a '.cleaned' suffix.
    
    Passes 'keep_labels_and_org' to the cleaning function.
    """
    
    # Get the name of this script to avoid processing it
    this_script_name = os.path.basename(sys.argv[0])
    
    processed_count = 0
    
    # Iterate over all items in the current directory
    for filename in os.listdir('.'):
        
        # Skip this script, directories, and already cleaned files
        if (filename == this_script_name or 
            not os.path.isfile(filename) or 
            filename.endswith('.cleaned') or
            filename.endswith('.py')):
            continue

        print(f"Processing {filename}...")
        new_lines = []
        try:
            with open(filename, 'r', encoding='utf-8', errors='ignore') as f_in:
                for line in f_in:
                    # --- MODIFIED ---
                    # Pass the flag to the clean function
                    cleaned_line = clean_instruction_line(line, keep_labels_and_org)
                    if cleaned_line:
                        new_lines.append(cleaned_line)
            
            if new_lines:
                new_filename = filename + '.cleaned'
                with open(new_filename, 'w', encoding='utf-8') as f_out:
                    for new_line in new_lines:
                        f_out.write(new_line + '\n')
                print(f"-> Created {new_filename}")
                processed_count += 1
            else:
                print(f"-> No relevant lines found in {filename}.")

        except Exception as e:
            print(f"Error processing {filename}: {e}")
            
    if processed_count == 0:
        print("\nNo files were processed. Make sure files are in this directory.")
    else:
        print(f"\nDone. Processed {processed_count} files.")


if __name__ == "__main__":
    # --- NEW ---
    # Ask the user for their preference
    #choice = ""
    #while choice not in ['y', 'n']:
        #choice = input("Keep labels and ORG/END directives? (y/n): ").strip().lower()

    #keep_labels = (choice == 'y')
    keep_labels = True
    if keep_labels:
        print("Mode: Keeping labels and directives.")
    else:
        print("Mode: Removing labels and directives.")
    print("---")
    
    process_files_in_directory(keep_labels_and_org=keep_labels)
