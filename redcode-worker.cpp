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

// --- Configuration ---
const int DEFAULT_CORE_SIZE = 8000;
const int DEFAULT_MAX_CYCLES = 80000;
const int DEFAULT_MAX_PROCESSES = 8000;
const int DEFAULT_MAX_WARRIOR_LENGTH = 100;
const int DEFAULT_MIN_DISTANCE = 100;

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
    "JMP", "JMZ", "JMN", "DJN", "CMP/SEQ", "SLT", "SPL",
    "SNE", "NOP", "ORG"
};
// Note: The CMP entry also covers the SEQ alias, which canonicalizes to CMP.

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
    if (offset > half_limit) return offset - limit;
    if (offset <= -half_limit) return offset + limit; // Note: Asymmetric range
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

    std::string opcode_token;
    std::string modifier_token;
    bool has_modifier = false;
    size_t dot_pos = opcode_full.find('.');
    if (dot_pos != std::string::npos) {
        opcode_token = opcode_full.substr(0, dot_pos);
        modifier_token = opcode_full.substr(dot_pos + 1);
        has_modifier = true;
    } else {
        opcode_token = opcode_full;
    }

    std::string opcode_str = to_upper_copy(opcode_token);
    std::string modifier_lookup = has_modifier ? to_upper_copy(modifier_token) : "F";
    std::string modifier_display = has_modifier ? modifier_token : "F";

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

    if (std::string("#$*@{}<>").find(a_str[0]) != std::string::npos) {
        instr.a_mode = get_mode(a_str[0]);
        instr.a_field = parse_numeric_field(trim(a_str.substr(1)), "line: " + original_line);
    } else {
        instr.a_mode = DIRECT;
        instr.a_field = parse_numeric_field(a_str, "line: " + original_line);
    }

    if (std::string("#$*@{}<>").find(b_str[0]) != std::string::npos) {
        instr.b_mode = get_mode(b_str[0]);
        instr.b_field = parse_numeric_field(trim(b_str.substr(1)), "line: " + original_line);
    } else {
        instr.b_mode = DIRECT;
        instr.b_field = parse_numeric_field(b_str, "line: " + original_line);
    }

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
                bool a_ok = apply(dst.a_field, src.a_field);
                bool b_ok = apply(dst.b_field, src.b_field);
                return a_ok && b_ok;
            }
            case X: {
                bool a_ok = apply(dst.a_field, src.b_field);
                bool b_ok = apply(dst.b_field, src.a_field);
                return a_ok && b_ok;
            }
        }

        return true;
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
            a_addr_final = pc;
            src = instr;
            src.b_field = instr.a_field;
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
                switch (instr.modifier) {
                    case A: if (src.a_field == dst.a_field) skip = true; break;
                    case B: if (src.b_field == dst.b_field) skip = true; break;
                    case AB: if (src.a_field == dst.b_field) skip = true; break;
                    case BA: if (src.b_field == dst.a_field) skip = true; break;
                    case F: if (src.a_field == dst.a_field && src.b_field == dst.b_field) skip = true; break;
                    case X: if (src.a_field == dst.b_field && src.b_field == dst.a_field) skip = true; break;
                    case I: if (src == dst) skip = true; break;
                }
                break;
            case SNE:
                switch (instr.modifier) {
                    case A: if (src.a_field != dst.a_field) skip = true; break;
                    case B: if (src.b_field != dst.b_field) skip = true; break;
                    case AB: if (src.a_field != dst.b_field) skip = true; break;
                    case BA: if (src.b_field != dst.a_field) skip = true; break;
                    case F: if (src.a_field != dst.a_field || src.b_field != dst.b_field) skip = true; break;
                    case X: if (src.a_field != dst.b_field || src.b_field != dst.a_field) skip = true; break;
                    case I: if (!(src == dst)) skip = true; break;
                }
                break;
            case SLT:
                switch (instr.modifier) {
                    case A: if (src.a_field < dst.a_field) skip = true; break;
                    case B: if (src.b_field < dst.b_field) skip = true; break;
                    case AB: if (src.a_field < dst.b_field) skip = true; break;
                    case BA: if (src.b_field < dst.a_field) skip = true; break;
                    case F: case I: if (src.a_field < dst.a_field && src.b_field < dst.b_field) skip = true; break;
                    case X: if (src.a_field < dst.b_field && src.b_field < dst.a_field) skip = true; break;
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
            // tests.
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
extern "C" {
    const char* run_battle(
        const char* warrior1_code, int w1_id,
        const char* warrior2_code, int w2_id,
        int core_size, int max_cycles, int max_processes,
        int min_distance, int rounds
    ) {
        static std::string response;
        try {
            auto w1_instrs = parse_warrior(warrior1_code);
            auto w2_instrs = parse_warrior(warrior2_code);

            std::random_device rd;
            std::mt19937 gen(rd());
            const char* trace_file = std::getenv("REDCODE_TRACE_FILE");

            int w1_score = 0;
            int w2_score = 0;

            int rounds_played = 0;
            for (int r = 0; r < rounds; ++r) {
                Core core(core_size, trace_file);
                std::uniform_int_distribution<> distrib(0, core_size - 1);

                int w1_start = distrib(gen);
                int w2_start;
                int circular_dist;
                do {
                    w2_start = distrib(gen);
                    int dist = std::abs(w1_start - w2_start);
                    circular_dist = std::min(dist, core_size - dist);
                } while (circular_dist < min_distance);

                for (size_t i = 0; i < w1_instrs.size(); ++i) {
                    core.memory[normalize(w1_start + i, core_size)] = w1_instrs[i];
                }
                for (size_t i = 0; i < w2_instrs.size(); ++i) {
                    core.memory[normalize(w2_start + i, core_size)] = w2_instrs[i];
                }

                core.process_queues[0].push_back({w1_start, 0});
                core.process_queues[1].push_back({w2_start, 1});

                for (int cycle = 0; cycle < max_cycles; ++cycle) {
                    if (core.process_queues[0].empty() || core.process_queues[1].empty()) {
                        break;
                    }
                    if (!core.process_queues[0].empty()) {
                        WarriorProcess p = core.process_queues[0].front();
                        core.process_queues[0].pop_front();
                        core.execute(p, core_size, core_size, max_processes);
                    }
                    if (!core.process_queues[1].empty()) {
                        WarriorProcess p = core.process_queues[1].front();
                        core.process_queues[1].pop_front();
                        core.execute(p, core_size, core_size, max_processes);
                    }
                }

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

                rounds_played = r + 1;
                int rounds_remaining = rounds - rounds_played;
                int score_diff = w1_score - w2_score;
                int max_possible_swing = 3 * rounds_remaining;
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
