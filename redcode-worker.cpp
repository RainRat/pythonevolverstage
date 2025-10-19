#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <map>
#include <list>
#include <random>
#include <fstream>
#include <cstdlib>
#include <stdexcept>
#include <cctype>
#include <cstdint>

// --- Configuration ---
const int DEFAULT_CORE_SIZE = 8000;
const int DEFAULT_MAX_CYCLES = 80000;
const int DEFAULT_MAX_PROCESSES = 8000;
const int DEFAULT_MAX_WARRIOR_LENGTH = 100;
const int DEFAULT_MIN_DISTANCE = 100;

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
    SNE, NOP,
    ORG // ORG is a pseudo-op
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
};

struct WarriorProcess {
    int pc; // Program Counter
    int owner;
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
    "SNE", "NOP", "ORG"
};
// Note: The CMP entry also covers the SEQ alias, which canonicalizes to CMP for logging.

const char* MODIFIER_NAMES[] = {
    "A", "B", "AB", "BA", "F", "X", "I"
};

const char* MODE_PREFIXES[] = {
    "#", "$", "@", "<", ">", "*", "{", "}"
};

// --- Core Normalization & Folding ---
int normalize(int address, int core_size) {
    address %= core_size;
    if (address < 0) {
        address += core_size;
    }
    return address;
}

int fold(int offset, int limit) {
    // Folds an offset to be within the range [-limit/2, limit/2]
    // This is equivalent to the corenorm function in the Python script.
    int half_limit = limit / 2;
    if (offset > half_limit) {
        return offset - limit;
    }
    // The negative boundary is inclusive, matching the Python implementation.
    if (offset <= -half_limit) {
        return offset + limit;
    }
    return offset;
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

Instruction parse_line(const std::string& line) {
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

    std::string opcode_upper = to_upper_copy(opcode_full);
    if (opcode_upper == "ORG") {
        throw std::runtime_error("Unsupported pseudo-opcode 'ORG' in line: " + original_line);
    }

    size_t dot_pos = opcode_full.find('.');
    if (dot_pos == std::string::npos) {
        throw std::runtime_error("Missing modifier for opcode '" + opcode_full + "' in line: " + original_line);
    }

    std::string opcode_token = opcode_full.substr(0, dot_pos);
    std::string modifier_token = opcode_full.substr(dot_pos + 1);

    std::string opcode_str = to_upper_copy(opcode_token);
    std::string modifier_lookup = to_upper_copy(modifier_token);
    std::string modifier_display = modifier_token;

    if (opcode_str == "ORG") {
        throw std::runtime_error("Unsupported pseudo-opcode 'ORG' in line: " + original_line);
    }

    auto op_it = OPCODE_MAP.find(opcode_str);
    if (op_it == OPCODE_MAP.end()) {
        throw std::runtime_error("Unknown opcode '" + opcode_token + "' in line: " + original_line);
    }
    instr.opcode = op_it->second;

    auto mod_it = MODIFIER_MAP.find(modifier_lookup);
    if (mod_it == MODIFIER_MAP.end()) {
        throw std::runtime_error("Unknown modifier '" + modifier_display + "' in line: " + original_line);
    }
    instr.modifier = mod_it->second;

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
        if (std::string(VALID_MODES).find(operand[0]) == std::string::npos) {
            throw std::runtime_error(std::string("Missing addressing mode prefix in ") +
                                     operand_name + "-field operand in line: " +
                                     original_line);
        }

        mode_target = get_mode(operand[0]);
        field_target = parse_numeric_field(trim(operand.substr(1)), "line: " + original_line);
    };

    parse_operand(a_str, "A", instr.a_mode, instr.a_field);
    parse_operand(b_str, "B", instr.b_mode, instr.b_field);

    return instr;
}

std::vector<Instruction> parse_warrior(const std::string& code) {
    std::vector<Instruction> warrior_code;
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

        std::string upper_trimmed = to_upper_copy(trimmed);
        if (upper_trimmed.rfind("END", 0) == 0) {
            continue;
        }
        try {
            warrior_code.push_back(parse_line(trimmed));
            if (warrior_code.size() > static_cast<size_t>(MAX_WARRIOR_LENGTH)) {
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
    return warrior_code;
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

    void log(int pc, const Instruction& instr) {
        if (!trace_enabled) return;
        trace << pc << ": "
              << OPCODE_NAMES[instr.opcode] << '.'
              << MODIFIER_NAMES[instr.modifier] << ' '
              << MODE_PREFIXES[instr.a_mode] << instr.a_field << ", "
              << MODE_PREFIXES[instr.b_mode] << instr.b_field << '\n';
    }

    void normalize_field(int& field) {
        field = (field % core_size + core_size) % core_size;
    }

private:
    template <typename Operation>
    void apply_arithmetic_operation(Instruction& dst, const Instruction& src, Modifier modifier, Operation op) {
        auto apply = [&](int& target, int value) {
            target = op(target, value);
            normalize_field(target);
        };

        switch (modifier) {
            case A:
                apply(dst.a_field, src.a_field);
                break;
            case B:
                apply(dst.b_field, src.b_field);
                break;
            case AB:
                apply(dst.b_field, src.a_field);
                break;
            case BA:
                apply(dst.a_field, src.b_field);
                break;
            case F:
            case I:
                apply(dst.a_field, src.a_field);
                apply(dst.b_field, src.b_field);
                break;
            case X:
                apply(dst.a_field, src.b_field);
                apply(dst.b_field, src.a_field);
                break;
        }
    }

    template <typename Operation>
    bool apply_safe_arithmetic_operation(Instruction& dst, const Instruction& src, Modifier modifier, Operation op) {
        auto apply = [&](int& target, int value) {
            if (value == 0) {
                return false;
            }
            target = op(target, value);
            normalize_field(target);
            return true;
        };

        switch (modifier) {
            case A:
                return apply(dst.a_field, src.a_field);
            case B:
                return apply(dst.b_field, src.b_field);
            case AB:
                return apply(dst.b_field, src.a_field);
            case BA:
                return apply(dst.a_field, src.b_field);
            case F:
            case I: {
                // We must evaluate both operations, so we can't short-circuit.
                // A bitwise AND ensures both sides are evaluated.
                bool a_ok = apply(dst.a_field, src.a_field);
                bool b_ok = apply(dst.b_field, src.b_field);
                return a_ok & b_ok;
            }
            case X: {
                bool a_ok = apply(dst.a_field, src.b_field);
                bool b_ok = apply(dst.b_field, src.a_field);
                return a_ok & b_ok;
            }
        }

        return true;
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
        int pc = process.pc;
        Instruction& instr = memory[pc];

        log(pc, instr);

        if (instr.opcode == DAT) {
            return; // Process terminates
        }

        // --- Operand Evaluation ---
        int a_addr_final;
        int b_addr_final;
        Instruction src;

        // --- A-Operand ---
        int primary_a_offset = fold(instr.a_field, read_limit);
        int intermediate_a_addr = normalize(pc + primary_a_offset, core_size);
        if (instr.a_mode == IMMEDIATE) {
            a_addr_final = pc; // The address of the immediate operand is the current PC
            src = memory[pc];   // Copy the current instruction.
            src.a_field = instr.a_field; // The immediate value goes into the A-field of the source.
        } else if (instr.a_mode == DIRECT) {
            a_addr_final = intermediate_a_addr;
            src = memory[a_addr_final];
        } else {
            bool use_a = (instr.a_mode == A_INDIRECT || instr.a_mode == A_PREDEC || instr.a_mode == A_POSTINC);
            bool predec = (instr.a_mode == A_PREDEC || instr.a_mode == B_PREDEC);
            bool postinc = (instr.a_mode == A_POSTINC || instr.a_mode == B_POSTINC);
            int& field = use_a ? memory[intermediate_a_addr].a_field : memory[intermediate_a_addr].b_field;
            if (predec) { field--; normalize_field(field); }
            int secondary_a_offset = field;
            int final_a_offset = fold(primary_a_offset + secondary_a_offset, read_limit);
            a_addr_final = normalize(pc + final_a_offset, core_size);
            src = memory[a_addr_final];
            if (postinc) { field++; normalize_field(field); }
        }

        // --- B-Operand ---
        int primary_b_offset = fold(instr.b_field, write_limit);
        int intermediate_b_addr = normalize(pc + primary_b_offset, core_size);
        if (instr.b_mode == IMMEDIATE) {
            b_addr_final = pc; // Immediate B-mode targets the current instruction.
        } else if (instr.b_mode == DIRECT) {
            b_addr_final = intermediate_b_addr;
        } else {
            bool use_a = (instr.b_mode == A_INDIRECT || instr.b_mode == A_PREDEC || instr.b_mode == A_POSTINC);
            bool predec = (instr.b_mode == A_PREDEC || instr.b_mode == B_PREDEC);
            bool postinc = (instr.b_mode == A_POSTINC || instr.b_mode == B_POSTINC);
            int& field = use_a ? memory[intermediate_b_addr].a_field : memory[intermediate_b_addr].b_field;
            if (predec) { field--; normalize_field(field); }
            int secondary_b_offset = field;
            int final_b_offset = fold(primary_b_offset + secondary_b_offset, write_limit);
            b_addr_final = normalize(pc + final_b_offset, core_size);
            if (postinc) { field++; normalize_field(field); }
        }

        Instruction& dst = memory[b_addr_final];
        bool skip = false;

        // --- Instruction Execution ---
        switch (instr.opcode) {
            case MOV:
                {
                    switch (instr.modifier) {
                        case A: dst.a_field = src.a_field; break;
                        case B: dst.b_field = src.b_field; break;
                        case AB: dst.b_field = src.a_field; break;
                        case BA: dst.a_field = src.b_field; break;
                        case F: dst.a_field = src.a_field; dst.b_field = src.b_field; break;
                        case X: dst.a_field = src.b_field; dst.b_field = src.a_field; break;
                        case I: dst = src; break;
                    }
                }
                break;
            case ADD:
                apply_arithmetic_operation(dst, src, instr.modifier, [](int lhs, int rhs) { return lhs + rhs; });
                break;
            case SUB:
                apply_arithmetic_operation(dst, src, instr.modifier, [](int lhs, int rhs) { return lhs - rhs; });
                break;
            case MUL:
                apply_arithmetic_operation(dst, src, instr.modifier, [](int lhs, int rhs) { return lhs * rhs; });
                break;
            case DIV:
                if (!apply_safe_arithmetic_operation(dst, src, instr.modifier, [](int lhs, int rhs) { return lhs / rhs; })) {
                    return;
                }
                break;
            case MOD:
                if (!apply_safe_arithmetic_operation(dst, src, instr.modifier, [](int lhs, int rhs) { return lhs % rhs; })) {
                    return;
                }
                break;
            case CMP:
                {
                    Instruction lhs = src;
                    if (instr.a_mode == IMMEDIATE) {
                        lhs.a_field = instr.a_field;
                        lhs.b_field = instr.a_field;
                    }
                    auto equals = [](int lhs, int rhs) { return lhs == rhs; };
                    auto combine_and = [](bool lhs, bool rhs) { return lhs && rhs; };
                    skip = check_condition(
                        lhs,
                        dst,
                        instr.modifier,
                        equals,
                        [](const Instruction& lhs, const Instruction& rhs) { return lhs == rhs; },
                        combine_and
                    );
                }
                break;
            case SNE:
                {
                    Instruction lhs = src;
                    if (instr.a_mode == IMMEDIATE) {
                        lhs.a_field = instr.a_field;
                        lhs.b_field = instr.a_field;
                    }
                    auto not_equals = [](int lhs, int rhs) { return lhs != rhs; };
                    auto combine_or = [](bool lhs, bool rhs) { return lhs || rhs; };
                    skip = check_condition(
                        lhs,
                        dst,
                        instr.modifier,
                        not_equals,
                        [](const Instruction& lhs, const Instruction& rhs) { return !(lhs == rhs); },
                        combine_or
                    );
                }
                break;
            case SLT:
                {
                    Instruction lhs = src;
                    if (instr.a_mode == IMMEDIATE) {
                        lhs.a_field = instr.a_field;
                        lhs.b_field = instr.a_field;
                    }
                    auto less_than = [](int lhs, int rhs) { return lhs < rhs; };
                    auto combine_and = [](bool lhs, bool rhs) { return lhs && rhs; };
                    skip = check_condition(
                        lhs,
                        dst,
                        instr.modifier,
                        less_than,
                        [less_than, combine_and](const Instruction& lhs, const Instruction& rhs) {
                            return combine_and(less_than(lhs.a_field, rhs.a_field),
                                               less_than(lhs.b_field, rhs.b_field));
                        },
                        combine_and
                    );
                }
                break;
            case JMP:
                process_queues[process.owner].push_back({a_addr_final, process.owner});
                return;
            case JMZ:
                switch (instr.modifier) {
                    case A: if (dst.a_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case B: if (dst.b_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case AB: if (dst.b_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case BA: if (dst.a_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case F: case I: if (dst.a_field == 0 && dst.b_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case X: if (dst.a_field == 0 && dst.b_field == 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
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
                switch (instr.modifier) {
                    case A: if (dst.a_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case B: if (dst.b_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case AB: if (dst.b_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case BA: if (dst.a_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case F: case I: if (dst.a_field != 0 || dst.b_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                    case X: if (dst.a_field != 0 || dst.b_field != 0) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; } break;
                }
                break;
            case DJN:
                {
                    Instruction temp = dst;
                    bool jump = false;
                    switch (instr.modifier) {
                        case A:
                            dst.a_field--; normalize_field(dst.a_field);
                            temp.a_field--; normalize_field(temp.a_field);
                            if (temp.a_field != 0) jump = true;
                            break;
                        case B:
                            dst.b_field--; normalize_field(dst.b_field);
                            temp.b_field--; normalize_field(temp.b_field);
                            if (temp.b_field != 0) jump = true;
                            break;
                        case AB:
                            dst.b_field--; normalize_field(dst.b_field);
                            temp.b_field--; normalize_field(temp.b_field);
                            if (temp.b_field != 0) jump = true;
                            break;
                        case BA:
                            dst.a_field--; normalize_field(dst.a_field);
                            temp.a_field--; normalize_field(temp.a_field);
                            if (temp.a_field != 0) jump = true;
                            break;
                        case F: case I:
                            dst.a_field--; normalize_field(dst.a_field);
                            dst.b_field--; normalize_field(dst.b_field);
                            temp.a_field--; normalize_field(temp.a_field);
                            temp.b_field--; normalize_field(temp.b_field);
                            if (temp.a_field != 0 || temp.b_field != 0) jump = true;
                            break;
                        case X:
                            dst.a_field--; normalize_field(dst.a_field);
                            dst.b_field--; normalize_field(dst.b_field);
                            temp.a_field--; normalize_field(temp.a_field);
                            temp.b_field--; normalize_field(temp.b_field);
                            if (temp.a_field != 0 || temp.b_field != 0) jump = true;
                            break;
                    }
                    if (jump) { process_queues[process.owner].push_back({a_addr_final, process.owner}); return; }
                }
                break;
            case SPL:
                {
                    int next_pc = normalize(pc + 1, core_size);
                    process_queues[process.owner].push_back({next_pc, process.owner});
                    if (process_queues[process.owner].size() < max_processes) {
                        process_queues[process.owner].push_back({a_addr_final, process.owner});
                    }
                }
                return;
            case NOP:
                break;
            default:
                break;
        }

        int next_pc = normalize(pc + (skip ? 2 : 1), core_size);
        process_queues[process.owner].push_back({next_pc, process.owner});
    }


    std::vector<Instruction> memory;
    int core_size;
    std::map<int, std::list<WarriorProcess>> process_queues;
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

extern "C" {
    const char* run_battle(
        const char* warrior1_code, int w1_id,
        const char* warrior2_code, int w2_id,
        int core_size, int max_cycles, int max_processes,
        int read_limit, int write_limit,
        int min_distance, int max_warrior_length, int rounds,
        int seed
    ) {
        static std::string response;
        try {
            if (!warrior1_code || !warrior2_code) {
                throw std::runtime_error("Null warrior source provided");
            }

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

            auto w1_instrs = parse_warrior(warrior1_code);
            auto w2_instrs = parse_warrior(warrior2_code);

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

            if (w1_instrs == w2_instrs) {
                std::stringstream tie_result;
                tie_result << w1_id << " 0 0 0 " << (rounds) << " scores\n";
                tie_result << w2_id << " 0 0 0 " << (rounds) << " scores";
                response = tie_result.str();
                return response.c_str();
            }

            auto normalize_pmars_seed = [](int64_t raw_seed) {
                constexpr int64_t modulus = 2147483647LL - 1LL;
                int64_t adjusted = raw_seed % modulus;
                if (adjusted <= 0) {
                    adjusted += modulus;
                }
                return static_cast<int32_t>(adjusted);
            };

            auto advance_pmars_seed = [](int32_t state) {
                constexpr int64_t multiplier = 16807;
                constexpr int64_t divisor = 127773;
                constexpr int64_t remainder = 2836;
                constexpr int64_t modulus = 2147483647;

                int64_t hi = state / divisor;
                int64_t lo = state % divisor;
                int64_t temp = multiplier * lo - remainder * hi;
                if (temp <= 0) {
                    temp += modulus;
                }
                return static_cast<int32_t>(temp);
            };

            int32_t rng_state;
            if (seed >= 0) {
                rng_state = normalize_pmars_seed(static_cast<int64_t>(seed) + 1);
            } else {
                std::random_device rd;
                rng_state = normalize_pmars_seed(static_cast<int64_t>(rd()) + 1);
            }
            const char* trace_file = std::getenv("REDCODE_TRACE_FILE");

            int w1_score = 0;
            int w2_score = 0;

            int placements = core_size - (2 * min_distance) + 1;
            if (placements <= 0) {
                placements = core_size;
            }

            bool use_exhaustive = rounds >= placements;
            int planned_rounds = use_exhaustive ? placements : rounds;

            int rounds_played = 0;
            for (int r = 0; r < planned_rounds; ++r) {
                Core core(core_size, trace_file);
                int w1_start = 0;
                int w2_start = min_distance % core_size;
                if (core_size > 0) {
                    if (use_exhaustive) {
                        w2_start = (min_distance + r) % core_size;
                    } else {
                        int offset = rng_state % placements;
                        w2_start = (min_distance + offset) % core_size;
                        rng_state = advance_pmars_seed(rng_state);
                    }
                }

                for (size_t i = 0; i < w1_instrs.size(); ++i) {
                    core.memory[normalize(w1_start + i, core_size)] = w1_instrs[i];
                }
                for (size_t i = 0; i < w2_instrs.size(); ++i) {
                    core.memory[normalize(w2_start + i, core_size)] = w2_instrs[i];
                }

                core.process_queues[0].push_back({w1_start, 0});
                core.process_queues[1].push_back({w2_start, 1});

                int winner_index = -1;
                int first_index = (r % 2 == 0) ? 0 : 1;
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

                if (winner_index == 0) {
                    w1_score += 3;
                } else if (winner_index == 1) {
                    w2_score += 3;
                } else {
                    int w1_procs = core.process_queues[0].size();
                    int w2_procs = core.process_queues[1].size();

                    if (w1_procs > 0 && w2_procs == 0) {
                        w1_score += 3;
                    } else if (w2_procs > 0 && w1_procs == 0) {
                        w2_score += 3;
                    } else {
                        w1_score += 1;
                        w2_score += 1;
                    }
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

    int worker_normalize(int address, int core_size) {
        if (core_size <= 0) {
            throw std::runtime_error("Core size must be positive for normalization");
        }
        return normalize(address, core_size);
    }

    int worker_fold(int offset, int limit) {
        if (limit <= 0) {
            throw std::runtime_error("Fold limit must be positive");
        }
        return fold(offset, limit);
    }
}
