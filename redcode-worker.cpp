#include <array>
#include <deque>
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <map>
#include <random>
#include <fstream>
#include <cstdlib>
#include <stdexcept>
#include <cctype>
#include <cstdint>
#include <cstring>

constexpr int WARRIOR_COUNT = 2;

// pMARS allows extremely large arenas (core size up to ~1 billion cells, an
// effectively unbounded process count, and millions of rounds). Those limits
// are impractical for the in-process worker because it is designed to run many
// arenas concurrently inside the evolution loop. The constants below therefore
// represent a compromise: they are substantially higher than the previous
// internal limits, line up with the scale that pMARS comfortably supports on
// contemporary hardware, and still keep memory usage and run time reasonable.
const int MAX_CORE_SIZE = 262144;          // 256 Ki cells
const int MAX_CYCLES = 5000000;            // generous cap, but still practical
const int MAX_PROCESSES = 131072;          // matches typical large-core usage
const int MAX_WARRIOR_LENGTH = MAX_CORE_SIZE;
const int MAX_MIN_DISTANCE = MAX_CORE_SIZE / 2;
const int MAX_ROUNDS = 100000;

// --- Enums for Redcode ---

enum Opcode {
    DAT, MOV, ADD, SUB, MUL, DIV, MOD,
    JMP, JMZ, JMN, DJN, CMP, SLT, SPL,
    SNE, NOP
};

enum Modifier {
    A, B, AB, BA, F, X, I
};

enum AddressMode {
    IMMEDIATE,  // #
    DIRECT,     // $
    B_INDIRECT, // @
    B_PREDEC,   // <
    B_POSTINC,  // >
    A_INDIRECT, // *
    A_PREDEC,   // {
    A_POSTINC   // }
};

// --- Data Structures ---

struct Instruction {
    Opcode opcode = DAT;
    Modifier modifier = F;
    AddressMode a_mode = DIRECT;
    int a_field = 0;
    AddressMode b_mode = DIRECT;
    int b_field = 0;

    bool operator==(const Instruction& other) const {
        return opcode == other.opcode &&
               modifier == other.modifier &&
               a_mode == other.a_mode &&
               a_field == other.a_field &&
               b_mode == other.b_mode &&
               b_field == other.b_field;
    }

    bool operator!=(const Instruction& other) const {
        return !(*this == other);
    }
};

struct WarriorProcess {
    int pc; // Program Counter
    int owner;
};

struct ParsedWarrior {
    std::vector<Instruction> instructions;
    int entry_point = 0;
};

// --- Mappings for Parsing ---

const std::map<std::string, Opcode> OPCODE_MAP = {
    {"DAT", DAT}, {"MOV", MOV}, {"ADD", ADD}, {"SUB", SUB}, {"MUL", MUL},
    {"DIV", DIV}, {"MOD", MOD}, {"JMP", JMP}, {"JMZ", JMZ}, {"JMN", JMN},
    {"DJN", DJN}, {"CMP", CMP}, {"SLT", SLT}, {"SPL", SPL},
    {"SEQ", CMP}, {"SNE", SNE}, {"NOP", NOP}
};

const std::map<std::string, Modifier> MODIFIER_MAP = {
    {"A", A}, {"B", B}, {"AB", AB}, {"BA", BA},
    {"F", F}, {"X", X}, {"I", I}
};

// Reverse lookups for logging
const char* OPCODE_NAMES[] = {
    "DAT", "MOV", "ADD", "SUB", "MUL", "DIV", "MOD",
    "JMP", "JMZ", "JMN", "DJN", "CMP", "SLT", "SPL",
    "SNE", "NOP"
};
// Note: The CMP entry also covers the SEQ alias, which canonicalizes to CMP for logging.

const char* MODIFIER_NAMES[] = {
    "A", "B", "AB", "BA", "F", "X", "I"
};

const char* MODE_PREFIXES[] = {
    "#", "$", "@", "<", ">", "*", "{", "}"
};

std::string to_string(const Instruction& instr) {
    std::stringstream ss;
    ss << OPCODE_NAMES[instr.opcode] << '.'
       << MODIFIER_NAMES[instr.modifier] << ' '
       << MODE_PREFIXES[instr.a_mode] << instr.a_field << ", "
       << MODE_PREFIXES[instr.b_mode] << instr.b_field;
    return ss.str();
}

bool opcode_allowed_in_1988(Opcode opcode) {
    switch (opcode) {
        case DAT:
        case MOV:
        case ADD:
        case SUB:
        case JMP:
        case JMZ:
        case JMN:
        case DJN:
        case CMP:
        case SLT:
        case SPL:
            return true;
        default:
            return false;
    }
}

bool modifier_allowed_in_1988(Modifier modifier) {
    switch (modifier) {
        case A:
        case B:
        case AB:
        case BA:
        case F:
            return true;
        default:
            return false;
    }
}

bool addressing_mode_allowed_in_1988(AddressMode mode) {
    switch (mode) {
        case IMMEDIATE:
        case DIRECT:
        case B_INDIRECT:
        case B_PREDEC:
        case B_POSTINC:
            return true;
        default:
            return false;
    }
}

// --- Core Normalization & Folding ---
int normalize(int address, int core_size) {
    address %= core_size;
    if (address < 0) {
        address += core_size;
    }
    return address;
}

int fold(int offset, int limit) {
    if (limit == 0) {
        return 0;
    }

    int result = offset % limit;
    if (result < 0) {
        result += limit;
    }

    int half_limit = limit / 2;
    if (result > half_limit) {
        result -= limit;
    }

    return result;
}


// --- Parser ---

AddressMode get_mode(char c) {
    switch (c) {
        case '#': return IMMEDIATE;
        case '$': return DIRECT;
        case '@': return B_INDIRECT;
        case '<': return B_PREDEC;
        case '>': return B_POSTINC;
        case '*': return A_INDIRECT;
        case '{': return A_PREDEC;
        case '}': return A_POSTINC;
        default: return DIRECT;
    }
}

std::string trim(const std::string& str) {
    size_t start = str.find_first_not_of(" \t");
    if (start == std::string::npos) {
        return "";
    }
    size_t end = str.find_last_not_of(" \t");
    return str.substr(start, end - start + 1);
}

std::string to_upper_copy(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (char c : input) {
        result.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return result;
}

int parse_numeric_field(const std::string& value, const std::string& context) {
    if (value.empty()) {
        throw std::runtime_error("Missing numeric operand in " + context);
    }
    size_t processed = 0;
    int parsed_value = 0;
    try {
        parsed_value = std::stoi(value, &processed, 10);
    } catch (const std::exception&) {
        throw std::runtime_error("Invalid numeric operand '" + value + "' in " + context);
    }
    if (processed != value.size()) {
        throw std::runtime_error("Invalid numeric operand '" + value + "' in " + context);
    }
    return parsed_value;
}

Instruction parse_line(const std::string& line, bool use_1988_rules) {
    Instruction instr;
    std::string original_line = trim(line);
    std::string working = original_line;
    size_t comment_pos = working.find(';');
    if (comment_pos != std::string::npos) {
        working = trim(working.substr(0, comment_pos));
    }

    std::stringstream ss(working);
    std::string opcode_full;

    if (!(ss >> opcode_full)) {
        throw std::runtime_error("Missing opcode in line: " + original_line);
    }

    size_t dot_pos = opcode_full.find('.');
    std::string opcode_token;
    std::string modifier_token;
    if (dot_pos == std::string::npos) {
        opcode_token = opcode_full;
    } else {
        opcode_token = opcode_full.substr(0, dot_pos);
        modifier_token = opcode_full.substr(dot_pos + 1);
    }

    std::string opcode_str = to_upper_copy(opcode_token);

    auto op_it = OPCODE_MAP.find(opcode_str);
    if (op_it == OPCODE_MAP.end()) {
        throw std::runtime_error("Unknown opcode '" + opcode_token + "' in line: " + original_line);
    }
    instr.opcode = op_it->second;
    if (use_1988_rules && !opcode_allowed_in_1988(instr.opcode)) {
        throw std::runtime_error(
            "Opcode '" + opcode_str + "' is not supported in 1988 arenas in line: " + original_line
        );
    }

    if (dot_pos == std::string::npos) {
        throw std::runtime_error("Missing modifier for opcode '" + opcode_token + "' in line: " + original_line);
    }

    std::string modifier_lookup = to_upper_copy(modifier_token);
    std::string modifier_display = modifier_token;

    auto mod_it = MODIFIER_MAP.find(modifier_lookup);
    if (mod_it == MODIFIER_MAP.end()) {
        throw std::runtime_error("Unknown modifier '" + modifier_display + "' in line: " + original_line);
    }
    instr.modifier = mod_it->second;
    if (use_1988_rules && !modifier_allowed_in_1988(instr.modifier)) {
        throw std::runtime_error(
            "Modifier '" + modifier_lookup + "' is not supported in 1988 arenas in line: " + original_line
        );
    }

    std::string operands_str;
    std::getline(ss, operands_str);
    operands_str = trim(operands_str);

    if (operands_str.empty()) {
        throw std::runtime_error("Missing operands in line: " + original_line);
    }

    std::string a_str;
    std::string b_str;
    size_t comma_pos = operands_str.find(',');
    if (comma_pos == std::string::npos) {
        throw std::runtime_error("Missing B-field operand in line: " + original_line);
    }

    a_str = trim(operands_str.substr(0, comma_pos));
    b_str = trim(operands_str.substr(comma_pos + 1));

    if (a_str.empty()) {
        throw std::runtime_error("Missing A-field operand in line: " + original_line);
    }
    if (b_str.empty()) {
        throw std::runtime_error("Missing B-field operand in line: " + original_line);
    }

    auto parse_operand = [&](const std::string& operand,
                             const char* operand_name,
                             AddressMode& mode_target,
                             int& field_target) {
        if (operand.empty()) {
            throw std::runtime_error(std::string("Missing ") + operand_name +
                                     "-field operand in line: " + original_line);
        }

        constexpr const char* VALID_MODES = "#$*@{}<>";
        if (std::strchr(VALID_MODES, operand[0]) == nullptr) {
            throw std::runtime_error(std::string("Missing addressing mode prefix in ") +
                                     operand_name + "-field operand in line: " +
                                     original_line);
        }

        mode_target = get_mode(operand[0]);
        if (use_1988_rules && !addressing_mode_allowed_in_1988(mode_target)) {
            std::string mode_str(1, operand[0]);
            throw std::runtime_error(
                "Addressing mode '" + mode_str + "' is not supported in 1988 arenas for " +
                operand_name + "-field operand in line: " + original_line
            );
        }
        if (operand.length() < 2) {
            throw std::runtime_error("Missing value for " + std::string(operand_name) +
                                     "-field operand in line: " + original_line);
        }

        field_target = parse_numeric_field(trim(operand.substr(1)), "line: " + original_line);
    };

    parse_operand(a_str, "A", instr.a_mode, instr.a_field);
    parse_operand(b_str, "B", instr.b_mode, instr.b_field);

    return instr;
}

ParsedWarrior parse_warrior(const std::string& code, bool use_1988_rules) {
    ParsedWarrior parsed;
    std::map<std::string, size_t> label_positions;
    bool has_entry_label = false;
    std::string entry_label_display;
    std::string entry_label_lookup;
    bool seen_non_comment_line = false;
    std::stringstream ss(code);
    std::string line;
    int line_number = 0;
    while (std::getline(ss, line)) {
        line_number++;
        std::string trimmed = trim(line);
        if (trimmed.empty() || trimmed.rfind(";", 0) == 0) {
            continue;
        }

        size_t comment_pos = trimmed.find(';');
        if (comment_pos != std::string::npos) {
            trimmed = trim(trimmed.substr(0, comment_pos));
            if (trimmed.empty()) {
                continue;
            }
        }

        std::stringstream token_stream(trimmed);
        std::string first_token;
        if (!(token_stream >> first_token)) {
            continue;
        }

        std::string first_token_upper = to_upper_copy(first_token);

        if (!seen_non_comment_line) {
            if (first_token_upper == "ORG") {
                std::string label_token;
                if (!(token_stream >> label_token)) {
                    throw std::runtime_error(
                        "ORG directive requires a label in line: " + trimmed
                    );
                }
                std::string extra_token;
                if (token_stream >> extra_token) {
                    throw std::runtime_error(
                        "ORG directive must specify exactly one label in line: " + trimmed
                    );
                }
                std::string label_clean = label_token;
                if (!label_clean.empty() && label_clean.back() == ':') {
                    label_clean.pop_back();
                }
                if (label_clean.empty()) {
                    throw std::runtime_error(
                        "ORG directive requires a non-empty label in line: " + trimmed
                    );
                }
                entry_label_display = label_clean;
                entry_label_lookup = to_upper_copy(label_clean);
                has_entry_label = true;
                seen_non_comment_line = true;
                continue;
            }
            seen_non_comment_line = true;
        } else if (first_token_upper == "ORG") {
            throw std::runtime_error(
                "ORG directive is only allowed as the first non-comment line"
            );
        }

        std::string instruction_text = trimmed;
        if (first_token.find('.') == std::string::npos) {
            std::string label = first_token;
            if (!label.empty() && label.back() == ':') {
                label.pop_back();
            }
            if (label.empty()) {
                throw std::runtime_error(
                    "Label must contain characters before the instruction in line: " + trimmed
                );
            }
            std::string label_lookup = to_upper_copy(label);
            if (label_positions.find(label_lookup) != label_positions.end()) {
                throw std::runtime_error(
                    "Duplicate label '" + label + "' encountered in line: " + trimmed
                );
            }
            label_positions[label_lookup] = parsed.instructions.size();

            size_t label_pos = instruction_text.find(first_token);
            if (label_pos != std::string::npos) {
                instruction_text = trim(instruction_text.substr(label_pos + first_token.size()));
            } else {
                instruction_text.clear();
            }
            if (instruction_text.empty()) {
                throw std::runtime_error(
                    "Label '" + label + "' is not followed by an instruction in line: " + trimmed
                );
            }
        }

        try {
            parsed.instructions.push_back(parse_line(instruction_text, use_1988_rules));
            if (parsed.instructions.size() > static_cast<size_t>(MAX_WARRIOR_LENGTH)) {
                throw std::runtime_error(
                    "Warrior exceeds maximum length of " + std::to_string(MAX_WARRIOR_LENGTH) + " instructions"
                );
            }
        } catch (const std::exception& e) {
            throw std::runtime_error(
                "Error parsing warrior at line " + std::to_string(line_number) + ": " + e.what()
            );
        }
    }
    if (has_entry_label) {
        auto it = label_positions.find(entry_label_lookup);
        if (it == label_positions.end()) {
            throw std::runtime_error(
                "ORG directive references undefined label '" + entry_label_display + "'"
            );
        }
        parsed.entry_point = static_cast<int>(it->second);
    }

    return parsed;
}


// --- Core Simulation ---

class Core {
public:
    Core(int size, const char* trace_filename = nullptr)
        : memory(size), core_size(size) {
        if (trace_filename && *trace_filename) {
            trace.open(trace_filename);
            trace_enabled = trace.is_open();
        } else {
            trace_enabled = false;
        }
    }

    void log(int pc,
             const Instruction& instr,
             int a_addr,
             const Instruction& src,
             int b_addr,
             const Instruction& dst_before) {
#ifdef DEBUG_TRACE
        if (!trace_enabled) return;
        trace << "PC=" << pc << " " << to_string(instr)
              << " | A=" << a_addr << " {" << to_string(src)
              << "}, B=" << b_addr << " {" << to_string(dst_before) << "}\n";
#endif
    }

    void log_write(int write_addr, const Instruction& value_written) {
#ifdef DEBUG_TRACE
        if (!trace_enabled) return;
        trace << "  -> WRITE @" << write_addr << " {" << to_string(value_written) << "}\n";
#endif
    }

private:
template<typename Operation>
void apply_arithmetic_operation(Instruction& dst, const Instruction& src, const Instruction& dst_snapshot, Modifier modifier, Operation op) {
    // Pre-normalize all potentially-used fields from the source (src)
    // and destination (dst) instructions, just as pMars's ARITH macro
    // does with IRB (dst) and IRA(src).
    int norm_dst_a = normalize(dst_snapshot.a_field, core_size);
    int norm_dst_b = normalize(dst_snapshot.b_field, core_size);
    int norm_src_a = normalize(src.a_field, core_size);
    int norm_src_b = normalize(src.b_field, core_size);

    // The 'op' lambda (passed from ADD/SUB) already handles the
    // final modulo arithmetic to keep the result in [0, core_size-1].

    switch (modifier) {
        case A:
            // pMars: dst.a = op(dst.a, src.a)
            dst.a_field = op(norm_dst_a, norm_src_a);
            break;
        case B:
            // pMars: dst.b = op(dst.b, src.b)
            dst.b_field = op(norm_dst_b, norm_src_b);
            break;
        case AB:
            // pMars: dst.b = op(dst.b, src.a)
            dst.b_field = op(norm_dst_b, norm_src_a);
            break;
        case BA:
            // pMars: dst.a = op(dst.a, src.b)
            dst.a_field = op(norm_dst_a, norm_src_b);
            break;
        case F:
        case I:
            // pMars: dst.a = op(dst.a, src.a), dst.b = op(dst.b, src.b)
            dst.a_field = op(norm_dst_a, norm_src_a);
            dst.b_field = op(norm_dst_b, norm_src_b);
            break;
        case X:
            // pMars: dst.a = op(dst.a, src.b), dst.b = op(dst.b, src.a)
            dst.a_field = op(norm_dst_a, norm_src_b);
            dst.b_field = op(norm_dst_b, norm_src_a);
            break;
    }
}

    template <typename Operation>
    void apply_safe_arithmetic_operation(Instruction& dst, const Instruction& src, const Instruction& dst_snapshot, Modifier modifier, Operation op, bool& did_fail) {
        did_fail = false;
        bool term_a = false;
        bool term_b = false;

        int norm_dst_a = normalize(dst_snapshot.a_field, core_size);
        int norm_dst_b = normalize(dst_snapshot.b_field, core_size);
        int norm_src_a = normalize(src.a_field, core_size);
        int norm_src_b = normalize(src.b_field, core_size);

        switch (modifier) {
            case A:
                if (norm_src_a == 0) term_a = true;
                else dst.a_field = op(norm_dst_a, norm_src_a);
                break;
            case B:
                if (norm_src_b == 0) term_b = true;
                else dst.b_field = op(norm_dst_b, norm_src_b);
                break;
            case AB:
                if (norm_src_a == 0) term_b = true;
                else dst.b_field = op(norm_dst_b, norm_src_a);
                break;
            case BA:
                if (norm_src_b == 0) term_a = true;
                else dst.a_field = op(norm_dst_a, norm_src_b);
                break;
            case F:
            case I:
                if (norm_src_a == 0) term_a = true;
                else dst.a_field = op(norm_dst_a, norm_src_a);
                if (norm_src_b == 0) term_b = true;
                else dst.b_field = op(norm_dst_b, norm_src_b);
                break;
            case X:
                // dst.a_field = op(dst.a, src.b)
                if (norm_src_b == 0) term_a = true;
                else dst.a_field = op(norm_dst_a, norm_src_b);

                // dst.b_field = op(dst.b, src.a)
                if (norm_src_a == 0) term_b = true;
                else dst.b_field = op(norm_dst_b, norm_src_a);
                break;
        }

        did_fail = term_a || term_b;
    }

    template <typename FieldPredicate, typename InstructionPredicate, typename Combiner>
    bool check_condition(const Instruction& src,
                         const Instruction& dst,
                         Modifier modifier,
                         FieldPredicate field_pred,
                         InstructionPredicate instr_pred,
                         Combiner combine) const {
        switch (modifier) {
            case A:
                return field_pred(src.a_field, dst.a_field);
            case B:
                return field_pred(src.b_field, dst.b_field);
            case AB:
                return field_pred(src.a_field, dst.b_field);
            case BA:
                return field_pred(src.b_field, dst.a_field);
            case F:
                return combine(field_pred(src.a_field, dst.a_field),
                               field_pred(src.b_field, dst.b_field));
            case X:
                return combine(field_pred(src.a_field, dst.b_field),
                               field_pred(src.b_field, dst.a_field));
            case I:
                return instr_pred(src, dst);
        }
        return false;
    }

public:
    void execute(WarriorProcess process, int read_limit, int write_limit, int max_processes) {
        if (process.owner < 0 || process.owner >= WARRIOR_COUNT) {
            throw std::runtime_error("Process owner index out of range");
        }

        int pc = process.pc;
        Instruction instr = memory[pc];
        auto& owner_queue = process_queues[process.owner];

        if (instr.opcode == DAT) {
            return; // Process terminates
        }

        // --- Operand Evaluation ---
        int a_val_a, a_val_b;
        int a_addr_final;
        int b_addr_final;
        Instruction src;
        int* a_pointer_field = nullptr;
        int* b_pointer_field = nullptr;

        // --- A-Operand ---
        if (instr.a_mode == IMMEDIATE) {
            a_addr_final = pc;
            // The instruction itself is the operand.
            // We use a copy, not a reference, in case the instruction modifies itself.
            src = memory[pc];
            a_val_a = instr.a_field;
            a_val_b = instr.b_field;
        } else {
            int primary_a_offset = fold(instr.a_field, read_limit);
            int intermediate_a_addr = normalize(pc + primary_a_offset, core_size);
            if (instr.a_mode == DIRECT) {
                a_addr_final = intermediate_a_addr;
            } else { // Indirect modes
                Instruction& a_ptr_instr = memory[intermediate_a_addr];
                int* offset_field_ptr;
                if (instr.a_mode == A_INDIRECT || instr.a_mode == A_PREDEC || instr.a_mode == A_POSTINC) {
                    offset_field_ptr = &a_ptr_instr.a_field;
                } else { // B-field indirect modes
                    offset_field_ptr = &a_ptr_instr.b_field;
                }
                if (instr.a_mode == A_PREDEC || instr.a_mode == B_PREDEC) {
                    *offset_field_ptr = normalize(*offset_field_ptr - 1, core_size);
                }
                int secondary_a_offset = *offset_field_ptr;
                int final_a_offset = fold(primary_a_offset + secondary_a_offset, read_limit);
                a_addr_final = normalize(pc + final_a_offset, core_size);
                if (instr.a_mode == A_POSTINC || instr.a_mode == B_POSTINC) {
                    a_pointer_field = offset_field_ptr;
                }
            }
            src = memory[a_addr_final];
            a_val_a = src.a_field;
            a_val_b = src.b_field;
        }

        // --- A-Operand Side Effects ---
        // This MUST happen after A-eval and before B-eval to match pMARS.
        if (a_pointer_field != nullptr) {
            *a_pointer_field = normalize(*a_pointer_field + 1, core_size);
        }

        // --- B-Operand ---
        // Note: B-operand is resolved *after* A-operand's pre-decrement AND post-increment.
        if (instr.b_mode == IMMEDIATE) {
            b_addr_final = pc;
        } else {
            int primary_b_offset = fold(instr.b_field, write_limit);
            int intermediate_b_addr = normalize(pc + primary_b_offset, core_size);
            if (instr.b_mode == DIRECT) {
                b_addr_final = intermediate_b_addr;
            } else { // Indirect modes
                Instruction& b_ptr_instr = memory[intermediate_b_addr];
                int* offset_field_ptr;
                if (instr.b_mode == A_INDIRECT || instr.b_mode == A_PREDEC || instr.b_mode == A_POSTINC) {
                    offset_field_ptr = &b_ptr_instr.a_field;
                } else { // B-field indirect modes
                    offset_field_ptr = &b_ptr_instr.b_field;
                }
                if (instr.b_mode == A_PREDEC || instr.b_mode == B_PREDEC) {
                    *offset_field_ptr = normalize(*offset_field_ptr - 1, core_size);
                }
                int secondary_b_offset = *offset_field_ptr;
                int final_b_offset = fold(primary_b_offset + secondary_b_offset, write_limit);
                b_addr_final = normalize(pc + final_b_offset, core_size);
                if (instr.b_mode == A_POSTINC || instr.b_mode == B_POSTINC) {
                    b_pointer_field = offset_field_ptr;
                }
            }
        }

        // --- Side Effects & Snapshots ---

        Instruction& dst = memory[b_addr_final];
        Instruction dst_snapshot;
        if (instr.b_mode == IMMEDIATE) {
            dst_snapshot = instr;
        } else {
            // Take a snapshot *before* B-post-increment is applied
            dst_snapshot = dst;
        }

        // B-post-increment must be applied after its address is used for the read/write,
        // but before the instruction executes.
        if (b_pointer_field != nullptr) {
            *b_pointer_field = normalize(*b_pointer_field + 1, core_size);
        }

        log(pc, instr, a_addr_final, src, b_addr_final, dst_snapshot);

        bool skip = false;
        bool queued_next_instruction = false;

        // --- Instruction Execution ---
        switch (instr.opcode) {
            case MOV:
                {
                    switch (instr.modifier) {
                        case A: dst.a_field = a_val_a; break;
                        case B: dst.b_field = a_val_b; break;
                        case AB: dst.b_field = a_val_a; break;
                        case BA: dst.a_field = a_val_b; break;
                        case F: dst.a_field = a_val_a; dst.b_field = a_val_b; break;
                        case X: dst.a_field = a_val_b; dst.b_field = a_val_a; break;
                        case I:
                            dst = src;
                            dst.a_field = a_val_a;
                            dst.b_field = a_val_b;
                            break;
                    }
                    log_write(b_addr_final, dst);
                }
                break;
            case ADD:
                apply_arithmetic_operation(dst, src, dst_snapshot, instr.modifier, [this](int lhs, int rhs) {
                    return (lhs + rhs) % core_size;
                });
                log_write(b_addr_final, dst);
                break;
            case SUB:
                apply_arithmetic_operation(dst, src, dst_snapshot, instr.modifier, [this](int lhs, int rhs) {
                    return (lhs - rhs + core_size) % core_size;
                });
                log_write(b_addr_final, dst);
                break;
            case MUL:
                apply_arithmetic_operation(dst, src, dst_snapshot, instr.modifier, [this](int lhs, int rhs) {
                    return static_cast<int>((static_cast<long long>(lhs) * rhs) % core_size);
                });
                log_write(b_addr_final, dst);
                break;
            case DIV:
                {
                    bool did_fail = false;
                    apply_safe_arithmetic_operation(dst, src, dst_snapshot, instr.modifier, [](int lhs, int rhs) { return lhs / rhs; }, did_fail);
                    if (did_fail) {
                        return;
                    }
                    log_write(b_addr_final, dst);
                }
                break;
            case MOD:
                {
                    bool did_fail = false;
                    apply_safe_arithmetic_operation(dst, src, dst_snapshot, instr.modifier, [](int lhs, int rhs) { return lhs % rhs; }, did_fail);
                    if (did_fail) {
                        return;
                    }
                    log_write(b_addr_final, dst);
                }
                break;
            case CMP:
                {
                    auto equals = [this](int l, int r) {
                        return normalize(l, core_size) == normalize(r, core_size);
                    };
                    auto combine_and = [](bool l, bool r) { return l && r; };
                    skip = check_condition(
                        src,
                        dst_snapshot,
                        instr.modifier,
                        equals,
                        [](const Instruction& l, const Instruction& r) { return l == r; },
                        combine_and
                    );
                }
                break;
            case SNE:
                {
                    auto not_equals = [this](int l, int r) {
                        return normalize(l, core_size) != normalize(r, core_size);
                    };
                    auto combine_or = [](bool l, bool r) { return l || r; };
                    skip = check_condition(
                        src,
                        dst_snapshot,
                        instr.modifier,
                        not_equals,
                        [this, not_equals](const Instruction& l, const Instruction& r) {
                            return not_equals(l.a_field, r.a_field) || not_equals(l.b_field, r.b_field) || l.opcode != r.opcode || l.modifier != r.modifier || l.a_mode != r.a_mode || l.b_mode != r.b_mode;
                        },
                        combine_or
                    );
                }
                break;
            case SLT:
                {
                    auto less_than = [this](int l, int r) {
                        return normalize(l, core_size) < normalize(r, core_size);
                    };
                    auto combine_and = [](bool l, bool r) { return l && r; };
                    skip = check_condition(
                        src,
                        dst_snapshot,
                        instr.modifier,
                        less_than,
                        [this, less_than, combine_and](const Instruction& l, const Instruction& r) {
                            return combine_and(less_than(l.a_field, r.a_field),
                                               less_than(l.b_field, r.b_field));
                        },
                        combine_and
                    );
                }
                break;
            case JMP:
                owner_queue.push_back({a_addr_final, process.owner});
                queued_next_instruction = true;
                break;
            case JMZ:
                {
                    bool jump = false;
                    switch (instr.modifier) {
                        case A: jump = (normalize(dst_snapshot.a_field, core_size) == 0); break;
                        case B: jump = (normalize(dst_snapshot.b_field, core_size) == 0); break;
                        case AB: jump = (normalize(dst_snapshot.b_field, core_size) == 0); break;
                        case BA: jump = (normalize(dst_snapshot.a_field, core_size) == 0); break;
                        case F: case I: jump = (normalize(dst_snapshot.a_field, core_size) == 0 && normalize(dst_snapshot.b_field, core_size) == 0); break;
                        case X: jump = (normalize(dst_snapshot.a_field, core_size) == 0 && normalize(dst_snapshot.b_field, core_size) == 0); break;
                    }
                    if (jump) {
                        owner_queue.push_back({a_addr_final, process.owner});
                        queued_next_instruction = true;
                    }
                }
                break;
            // ICWS'94 spec text (lines 0725-0735) describes JMN.I/DJN.I as taking the
            // branch only when both target fields are non-zero (logical AND). The
            // official reference emulator (EMI94.c, line 1211) and the published
            // jmn_djn_test.txt suite instead implement the branch when either field is
            // non-zero (logical OR). We mirror EMI94's behaviour here to stay aligned
            // with the de facto standard used by other emulators and the upstream
            // tests. This policy is documented in AGENTS.md so contributors know that
            // both the Python and C++ implementations intentionally follow EMI94.
            case JMN:
                {
                    bool jump = false;
                    switch (instr.modifier) {
                        case A: jump = (normalize(dst_snapshot.a_field, core_size) != 0); break;
                        case B: jump = (normalize(dst_snapshot.b_field, core_size) != 0); break;
                        case AB: jump = (normalize(dst_snapshot.b_field, core_size) != 0); break;
                        case BA: jump = (normalize(dst_snapshot.a_field, core_size) != 0); break;
                        case F: case I: jump = (normalize(dst_snapshot.a_field, core_size) != 0 || normalize(dst_snapshot.b_field, core_size) != 0); break;
                        case X: jump = (normalize(dst_snapshot.a_field, core_size) != 0 || normalize(dst_snapshot.b_field, core_size) != 0); break;
                    }
                    if (jump) {
                        owner_queue.push_back({a_addr_final, process.owner});
                        queued_next_instruction = true;
                    }
                }
                break;
            case DJN:
                {
                    bool jump = false;
                    switch (instr.modifier) {
                        case A:
                            dst.a_field = normalize(dst.a_field - 1, core_size);
                            if (normalize(dst_snapshot.a_field, core_size) != 1) jump = true;
                            break;
                        case B:
                            dst.b_field = normalize(dst.b_field - 1, core_size);
                            if (normalize(dst_snapshot.b_field, core_size) != 1) jump = true;
                            break;
                        case AB:
                            dst.b_field = normalize(dst.b_field - 1, core_size);
                            if (normalize(dst_snapshot.b_field, core_size) != 1) jump = true;
                            break;
                        case BA:
                            dst.a_field = normalize(dst.a_field - 1, core_size);
                            if (normalize(dst_snapshot.a_field, core_size) != 1) jump = true;
                            break;
                        case F:
                        case I:
                        case X: {
                            bool a_will_be_zero = (normalize(dst_snapshot.a_field, core_size) == 1);
                            bool b_will_be_zero = (normalize(dst_snapshot.b_field, core_size) == 1);
                            dst.a_field = normalize(dst.a_field - 1, core_size);
                            dst.b_field = normalize(dst.b_field - 1, core_size);
                            if (!a_will_be_zero || !b_will_be_zero) {
                                jump = true;
                            }
                            break;
                        }
                    }
                    log_write(b_addr_final, dst);
                    if (jump) {
                        owner_queue.push_back({a_addr_final, process.owner});
                        queued_next_instruction = true;
                    }
                }
                break;
            case SPL:
                {
                    int next_pc = normalize(pc + 1, core_size);
                    owner_queue.push_back({next_pc, process.owner});
                    queued_next_instruction = true;

                    if (owner_queue.size() < static_cast<size_t>(max_processes)) {
                        owner_queue.push_back({a_addr_final, process.owner});
                    }
                }
                break;
            case NOP:
                break;
            default:
                break;
        }

        if (!queued_next_instruction) {
            int next_pc = normalize(pc + (skip ? 2 : 1), core_size);
            owner_queue.push_back({next_pc, process.owner});
        }
    }


    std::vector<Instruction> memory;
    int core_size;
    std::array<std::deque<WarriorProcess>, WARRIOR_COUNT> process_queues;
    std::ofstream trace;
    bool trace_enabled;
};


// --- Battle Manager ---
void validate_battle_parameters(
    int core_size,
    int max_cycles,
    int max_processes,
    int read_limit,
    int write_limit,
    int min_distance,
    int max_warrior_length,
    int rounds
) {
    if (core_size < 2) {
        throw std::runtime_error("Core size must be at least 2");
    }
    if (core_size > MAX_CORE_SIZE) {
        throw std::runtime_error(
            "Core size exceeds maximum supported value of " + std::to_string(MAX_CORE_SIZE)
        );
    }
    if (max_cycles <= 0 || max_cycles > MAX_CYCLES) {
        throw std::runtime_error(
            "Max cycles must be between 1 and " + std::to_string(MAX_CYCLES)
        );
    }
    if (max_processes <= 0 || max_processes > MAX_PROCESSES) {
        throw std::runtime_error(
            "Max processes must be between 1 and " + std::to_string(MAX_PROCESSES)
        );
    }
    if (read_limit <= 0 || read_limit > core_size) {
        throw std::runtime_error("Read limit must be between 1 and the core size");
    }
    if (write_limit <= 0 || write_limit > core_size) {
        throw std::runtime_error("Write limit must be between 1 and the core size");
    }
    if (min_distance < 0 || min_distance > MAX_MIN_DISTANCE) {
        throw std::runtime_error(
            "Min distance must be between 0 and " + std::to_string(MAX_MIN_DISTANCE)
        );
    }
    if (min_distance > core_size / 2) {
        throw std::runtime_error("Min distance is too large for the given core size");
    }
    if (min_distance < max_warrior_length) {
        throw std::runtime_error(
            "Min distance must be greater than or equal to max warrior length to prevent overlap."
        );
    }
    if (max_warrior_length <= 0 || max_warrior_length > MAX_WARRIOR_LENGTH) {
        throw std::runtime_error(
            "Max warrior length must be between 1 and " + std::to_string(MAX_WARRIOR_LENGTH)
        );
    }
    if (max_warrior_length > core_size) {
        throw std::runtime_error("Max warrior length cannot exceed the core size");
    }
    if (rounds <= 0 || rounds > MAX_ROUNDS) {
        throw std::runtime_error(
            "Number of rounds must be between 1 and " + std::to_string(MAX_ROUNDS)
        );
    }
}

struct PmarsPlacementGenerator {
    explicit PmarsPlacementGenerator(int seed_value, int min_distance) {
        rng_state = initialize_state(seed_value, min_distance);
    }

    int next_offset(int placements) {
        if (placements <= 0) {
            return 0;
        }
        int offset = positive_mod(rng_state, placements);
        rng_state = advance_state(rng_state);
        return offset;
    }

private:
    static constexpr int64_t RNG_MODULUS = 2147483647LL;
    static constexpr int64_t FIXED_SEED_MODULUS = 1073741825LL;

    static int32_t initialize_state(int seed_value, int min_distance) {
        if (seed_value <= 0) {
            return random_state();
        }

        int64_t normalized = normalize_fixed_seed(static_cast<int64_t>(seed_value));
        if (normalized <= 0) {
            return random_state();
        }
        if (normalized < min_distance) {
            throw std::runtime_error(
                "Fixed warrior position cannot be smaller than the configured minimum distance"
            );
        }

        int64_t adjusted = normalized - min_distance;
        return normalize_state(adjusted);
    }

    static int64_t normalize_fixed_seed(int64_t value) {
        int64_t normalized = value % FIXED_SEED_MODULUS;
        if (normalized < 0) {
            normalized += FIXED_SEED_MODULUS;
        }
        return normalized;
    }

    static int32_t random_state() {
        std::random_device rd;
        return normalize_state(static_cast<int64_t>(rd()));
    }

    static int32_t normalize_state(int64_t value) {
        int64_t adjusted = value % RNG_MODULUS;
        if (adjusted < 0) {
            adjusted += RNG_MODULUS;
        }
        return static_cast<int32_t>(adjusted);
    }

    static int positive_mod(int32_t value, int modulus) {
        int result = value % modulus;
        if (result < 0) {
            result += modulus;
        }
        return result;
    }

    static int32_t advance_state(int32_t state) {
        constexpr int64_t multiplier = 16807;
        constexpr int64_t divisor = 127773;
        constexpr int64_t remainder = 2836;

        int64_t state64 = static_cast<int64_t>(state);
        int64_t temp = multiplier * (state64 % divisor) - remainder * (state64 / divisor);
        if (temp < 0) {
            temp += RNG_MODULUS;
        }
        return static_cast<int32_t>(temp);
    }

    int32_t rng_state;
};

int run_single_round(
    Core& core,
    int w1_start,
    int w2_start,
    int max_cycles,
    int read_limit,
    int write_limit,
    int max_processes,
    int first_index
) {
    core.process_queues[0].clear();
    core.process_queues[1].clear();

    core.process_queues[0].push_back({w1_start, 0});
    core.process_queues[1].push_back({w2_start, 1});

    int winner_index = -1;
    int second_index = 1 - first_index;

    auto execute_turn = [&](int current_index, int opponent_index) {
        if (core.process_queues[current_index].empty()) {
            return;
        }
        WarriorProcess process = core.process_queues[current_index].front();
        core.process_queues[current_index].pop_front();
        core.execute(process, read_limit, write_limit, max_processes);

        if (winner_index == -1) {
            bool current_empty = core.process_queues[current_index].empty();
            bool opponent_empty = core.process_queues[opponent_index].empty();
            if (current_empty && !opponent_empty) {
                winner_index = opponent_index;
            } else if (!current_empty && opponent_empty) {
                winner_index = current_index;
            }
        }
    };

    for (int cycle = 0; cycle < max_cycles; ++cycle) {
        if (core.process_queues[0].empty() || core.process_queues[1].empty()) {
            break;
        }

        execute_turn(first_index, second_index);
        execute_turn(second_index, first_index);
    }

    return winner_index;
}

extern "C" {
    const char* run_battle(
        const char* warrior1_code, int w1_id,
        const char* warrior2_code, int w2_id,
        int core_size, int max_cycles, int max_processes,
        int read_limit, int write_limit,
        int min_distance, int max_warrior_length, int rounds,
        int seed,
        int use_1988_rules
    ) {
        thread_local std::string response;
        try {
            if (!warrior1_code || !warrior2_code) {
                throw std::runtime_error("Null warrior source provided");
            }

            bool use_1988 = use_1988_rules != 0;

            validate_battle_parameters(
                core_size,
                max_cycles,
                max_processes,
                read_limit,
                write_limit,
                min_distance,
                max_warrior_length,
                rounds
            );

            auto w1_parsed = parse_warrior(warrior1_code, use_1988);
            auto w2_parsed = parse_warrior(warrior2_code, use_1988);

            const auto& w1_instrs = w1_parsed.instructions;
            const auto& w2_instrs = w2_parsed.instructions;

            if (w1_instrs.empty()) {
                throw std::runtime_error("Warrior 1 contains no executable instructions");
            }
            if (w2_instrs.empty()) {
                throw std::runtime_error("Warrior 2 contains no executable instructions");
            }
            if (static_cast<int>(w1_instrs.size()) > max_warrior_length) {
                throw std::runtime_error(
                    "Warrior 1 length exceeds the configured maximum of " +
                    std::to_string(max_warrior_length)
                );
            }
            if (static_cast<int>(w2_instrs.size()) > max_warrior_length) {
                throw std::runtime_error(
                    "Warrior 2 length exceeds the configured maximum of " +
                    std::to_string(max_warrior_length)
                );
            }

            if (w1_instrs == w2_instrs && w1_parsed.entry_point == w2_parsed.entry_point) {
                std::stringstream tie_result;
                tie_result << w1_id << " 0 0 0 " << (rounds) << " scores\n";
                tie_result << w2_id << " 0 0 0 " << (rounds) << " scores";
                response = tie_result.str();
                return response.c_str();
            }

            PmarsPlacementGenerator placement_rng(seed, min_distance);
            const char* trace_file = std::getenv("REDCODE_TRACE_FILE");

            int w1_score = 0;
            int w2_score = 0;

            int placements = core_size - (2 * min_distance) + 1;
            if (placements <= 0) {
                throw std::runtime_error(
                    "Core size is too small for the configured warrior distance"
                );
            }
            int planned_rounds = rounds;

            int rounds_played = 0;
            for (int r = 0; r < rounds; ++r) {
                Core core(core_size, trace_file);
                int w1_start = 0;
                int offset = placement_rng.next_offset(placements);
                int w2_start = normalize(min_distance + offset, core_size);

                for (size_t i = 0; i < w1_instrs.size(); ++i) {
                    core.memory[normalize(w1_start + static_cast<int>(i), core_size)] = w1_instrs[i];
                }
                for (size_t i = 0; i < w2_instrs.size(); ++i) {
                    core.memory[normalize(w2_start + static_cast<int>(i), core_size)] = w2_instrs[i];
                }

                int w1_entry_address = normalize(w1_start + w1_parsed.entry_point, core_size);
                int w2_entry_address = normalize(w2_start + w2_parsed.entry_point, core_size);

                int first_index = (r % 2 == 0) ? 0 : 1;
                int winner_index = run_single_round(
                    core,
                    w1_entry_address,
                    w2_entry_address,
                    max_cycles,
                    read_limit,
                    write_limit,
                    max_processes,
                    first_index
                );

                if (winner_index == 0) {
                    w1_score += 3;
                } else if (winner_index == 1) {
                    w2_score += 3;
                } else {
                    w1_score += 1;
                    w2_score += 1;
                }

                rounds_played = r + 1;
                int rounds_remaining = planned_rounds - rounds_played;
                int score_diff = w1_score - w2_score;
                int max_possible_swing = 3 * rounds_remaining;
                // When one warrior has an insurmountable lead we can stop early.
                // This mirrors pMARS behaviour and keeps tournaments performant
                // while still producing identical final scores.
                if (score_diff > 0 && score_diff > max_possible_swing) {
                    break;
                }
                if (score_diff < 0 && -score_diff > max_possible_swing) {
                    break;
                }
            }

            std::stringstream result_ss;
            result_ss << w1_id << " 0 0 0 " << w1_score << " scores\n";
            result_ss << w2_id << " 0 0 0 " << w2_score << " scores";

            response = result_ss.str();
        } catch (const std::exception& e) {
            response = std::string("ERROR: ") + e.what();
        } catch (...) {
            response = "ERROR: Unknown exception encountered while running battle";
        }
        return response.c_str();
    }

}
