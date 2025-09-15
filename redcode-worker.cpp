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
    SEQ, SNE, NOP,
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
    {"SEQ", SEQ}, {"SNE", SNE}, {"NOP", NOP}, {"ORG", ORG}
};

const std::map<std::string, Modifier> MODIFIER_MAP = {
    {"A", A}, {"B", B}, {"AB", AB}, {"BA", BA},
    {"F", F}, {"X", X}, {"I", I}
};

// Reverse lookups for logging
const char* OPCODE_NAMES[] = {
    "DAT", "MOV", "ADD", "SUB", "MUL", "DIV", "MOD",
    "JMP", "JMZ", "JMN", "DJN", "CMP", "SLT", "SPL",
    "SEQ", "SNE", "NOP", "ORG"
};

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
    std::stringstream ss(line);
    std::string opcode_full;

    if (!(ss >> opcode_full)) {
        throw std::runtime_error("Missing opcode in line: " + line);
    }

    std::string opcode_str, modifier_str;
    size_t dot_pos = opcode_full.find('.');
    if (dot_pos != std::string::npos) {
        opcode_str = opcode_full.substr(0, dot_pos);
        modifier_str = opcode_full.substr(dot_pos + 1);
    } else {
        opcode_str = opcode_full;
        modifier_str = "F"; // Default modifier
    }

    auto op_it = OPCODE_MAP.find(opcode_str);
    if (op_it == OPCODE_MAP.end()) {
        throw std::runtime_error("Unknown opcode '" + opcode_str + "' in line: " + line);
    }
    instr.opcode = op_it->second;

    auto mod_it = MODIFIER_MAP.find(modifier_str);
    if (mod_it == MODIFIER_MAP.end()) {
        throw std::runtime_error("Unknown modifier '" + modifier_str + "' in line: " + line);
    }
    instr.modifier = mod_it->second;

    std::string operands_str;
    std::getline(ss, operands_str);
    operands_str = trim(operands_str);

    if (operands_str.empty()) {
        throw std::runtime_error("Missing operands in line: " + line);
    }

    std::string a_str;
    std::string b_str;
    size_t comma_pos = operands_str.find(',');
    if (comma_pos != std::string::npos) {
        a_str = trim(operands_str.substr(0, comma_pos));
        b_str = trim(operands_str.substr(comma_pos + 1));
    } else {
        a_str = trim(operands_str);
        b_str = "$0"; // Default for missing B-field
    }

    if (a_str.empty()) {
        throw std::runtime_error("Missing A-field operand in line: " + line);
    }
    if (b_str.empty()) {
        throw std::runtime_error("Missing B-field operand in line: " + line);
    }

    if (std::string("#$*@{}<>").find(a_str[0]) != std::string::npos) {
        instr.a_mode = get_mode(a_str[0]);
        instr.a_field = parse_numeric_field(trim(a_str.substr(1)), "line: " + line);
    } else {
        instr.a_mode = DIRECT;
        instr.a_field = parse_numeric_field(a_str, "line: " + line);
    }

    if (std::string("#$*@{}<>").find(b_str[0]) != std::string::npos) {
        instr.b_mode = get_mode(b_str[0]);
        instr.b_field = parse_numeric_field(trim(b_str.substr(1)), "line: " + line);
    } else {
        instr.b_mode = DIRECT;
        instr.b_field = parse_numeric_field(b_str, "line: " + line);
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
        // Basic cleaning
        if (trimmed.empty() || trimmed.rfind(";", 0) == 0 || trimmed.rfind("END", 0) == 0) {
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

    void execute(WarriorProcess process, int read_limit, int write_limit, int max_processes) {
        int pc = process.pc;
        Instruction& instr = memory[pc];

        log(pc, instr);

        if (instr.opcode == DAT) {
            return; // Process terminates
        }

        // --- Operand Evaluation ---
        int a_ptr_final;
        int b_ptr_final;
        Instruction src;

        // --- A-Operand ---
        int primary_a_offset = fold(instr.a_field, read_limit);
        int intermediate_a_addr = normalize(pc + primary_a_offset, core_size);
        if (instr.a_mode == IMMEDIATE) {
            a_ptr_final = pc;
            src = instr;
        } else if (instr.a_mode == DIRECT) {
            a_ptr_final = intermediate_a_addr;
            src = memory[a_ptr_final];
        } else {
            bool use_a = (instr.a_mode == A_INDIRECT || instr.a_mode == A_PREDEC || instr.a_mode == A_POSTINC);
            bool predec = (instr.a_mode == A_PREDEC || instr.a_mode == B_PREDEC);
            bool postinc = (instr.a_mode == A_POSTINC || instr.a_mode == B_POSTINC);
            int& field = use_a ? memory[intermediate_a_addr].a_field : memory[intermediate_a_addr].b_field;
            if (predec) { field--; normalize_field(field); }
            int secondary_a_offset = field;
            int final_a_offset = fold(primary_a_offset + secondary_a_offset, read_limit);
            a_ptr_final = normalize(pc + final_a_offset, core_size);
            src = memory[a_ptr_final];
            if (postinc) { field++; normalize_field(field); }
        }

        // --- B-Operand ---
        int primary_b_offset = fold(instr.b_field, write_limit);
        int intermediate_b_addr = normalize(pc + primary_b_offset, core_size);
        if (instr.b_mode == IMMEDIATE) {
            b_ptr_final = pc; // Immediate B-mode targets the current instruction.
        } else if (instr.b_mode == DIRECT) {
            b_ptr_final = intermediate_b_addr;
        } else {
            bool use_a = (instr.b_mode == A_INDIRECT || instr.b_mode == A_PREDEC || instr.b_mode == A_POSTINC);
            bool predec = (instr.b_mode == A_PREDEC || instr.b_mode == B_PREDEC);
            bool postinc = (instr.b_mode == A_POSTINC || instr.b_mode == B_POSTINC);
            int& field = use_a ? memory[intermediate_b_addr].a_field : memory[intermediate_b_addr].b_field;
            if (predec) { field--; normalize_field(field); }
            int secondary_b_offset = field;
            int final_b_offset = fold(primary_b_offset + secondary_b_offset, write_limit);
            b_ptr_final = normalize(pc + final_b_offset, core_size);
            if (postinc) { field++; normalize_field(field); }
        }

        Instruction& dst = memory[b_ptr_final];
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
                switch (instr.modifier) {
                    case A: dst.a_field += src.a_field; normalize_field(dst.a_field); break;
                    case B: dst.b_field += src.b_field; normalize_field(dst.b_field); break;
                    case AB: dst.b_field += src.a_field; normalize_field(dst.b_field); break;
                    case BA: dst.a_field += src.b_field; normalize_field(dst.a_field); break;
                    case F: case I: dst.a_field += src.a_field; normalize_field(dst.a_field); dst.b_field += src.b_field; normalize_field(dst.b_field); break;
                    case X: dst.a_field += src.b_field; normalize_field(dst.a_field); dst.b_field += src.a_field; normalize_field(dst.b_field); break;
                }
                break;
            case SUB:
                switch (instr.modifier) {
                    case A: dst.a_field -= src.a_field; normalize_field(dst.a_field); break;
                    case B: dst.b_field -= src.b_field; normalize_field(dst.b_field); break;
                    case AB: dst.b_field -= src.a_field; normalize_field(dst.b_field); break;
                    case BA: dst.a_field -= src.b_field; normalize_field(dst.a_field); break;
                    case F: case I: dst.a_field -= src.a_field; normalize_field(dst.a_field); dst.b_field -= src.b_field; normalize_field(dst.b_field); break;
                    case X: dst.a_field -= src.b_field; normalize_field(dst.a_field); dst.b_field -= src.a_field; normalize_field(dst.b_field); break;
                }
                break;
            case MUL:
                switch (instr.modifier) {
                    case A: dst.a_field *= src.a_field; normalize_field(dst.a_field); break;
                    case B: dst.b_field *= src.b_field; normalize_field(dst.b_field); break;
                    case AB: dst.b_field *= src.a_field; normalize_field(dst.b_field); break;
                    case BA: dst.a_field *= src.b_field; normalize_field(dst.a_field); break;
                    case F: case I: dst.a_field *= src.a_field; normalize_field(dst.a_field); dst.b_field *= src.b_field; normalize_field(dst.b_field); break;
                    case X: dst.a_field *= src.b_field; normalize_field(dst.a_field); dst.b_field *= src.a_field; normalize_field(dst.b_field); break;
                }
                break;
            case DIV:
                {
                    bool div_by_zero = false;
                    switch (instr.modifier) {
                        case A: if (src.a_field == 0) div_by_zero = true; else dst.a_field /= src.a_field; break;
                        case B: if (src.b_field == 0) div_by_zero = true; else dst.b_field /= src.b_field; break;
                        case AB: if (src.a_field == 0) div_by_zero = true; else dst.b_field /= src.a_field; break;
                        case BA: if (src.b_field == 0) div_by_zero = true; else dst.a_field /= src.b_field; break;
                        case F: case I:
                            if (src.a_field == 0 || src.b_field == 0) div_by_zero = true;
                            else { dst.a_field /= src.a_field; dst.b_field /= src.b_field; }
                            break;
                        case X:
                            if (src.a_field == 0 || src.b_field == 0) div_by_zero = true;
                            else { dst.a_field /= src.b_field; dst.b_field /= src.a_field; }
                            break;
                    }
                    if (div_by_zero) return; else { normalize_field(dst.a_field); normalize_field(dst.b_field); }
                }
                break;
            case MOD:
                {
                    bool div_by_zero = false;
                    switch (instr.modifier) {
                        case A: if (src.a_field == 0) div_by_zero = true; else dst.a_field %= src.a_field; break;
                        case B: if (src.b_field == 0) div_by_zero = true; else dst.b_field %= src.b_field; break;
                        case AB: if (src.a_field == 0) div_by_zero = true; else dst.b_field %= src.a_field; break;
                        case BA: if (src.b_field == 0) div_by_zero = true; else dst.a_field %= src.b_field; break;
                        case F: case I:
                            if (src.a_field == 0 || src.b_field == 0) div_by_zero = true;
                            else { dst.a_field %= src.a_field; dst.b_field %= src.b_field; }
                            break;
                        case X:
                            if (src.a_field == 0 || src.b_field == 0) div_by_zero = true;
                            else { dst.a_field %= src.b_field; dst.b_field %= src.a_field; }
                            break;
                    }
                    if (div_by_zero) return; else { normalize_field(dst.a_field); normalize_field(dst.b_field); }
                }
                break;
            case CMP:
            case SEQ:
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
                process_queues[process.owner].push_back({a_ptr_final, process.owner});
                return;
            case JMZ:
                switch (instr.modifier) {
                    case A: if (dst.a_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case B: if (dst.b_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case AB: if (dst.b_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case BA: if (dst.a_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case F: case I: if (dst.a_field == 0 && dst.b_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case X: if (dst.a_field == 0 && dst.b_field == 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                }
                break;
            case JMN:
                switch (instr.modifier) {
                    case A: if (dst.a_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case B: if (dst.b_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case AB: if (dst.b_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case BA: if (dst.a_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case F: case I: if (dst.a_field != 0 || dst.b_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
                    case X: if (dst.a_field != 0 || dst.b_field != 0) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; } break;
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
                    if (jump) { process_queues[process.owner].push_back({a_ptr_final, process.owner}); return; }
                }
                break;
            case SPL:
                {
                    int next_pc = normalize(pc + 1, core_size);
                    process_queues[process.owner].push_back({next_pc, process.owner});
                    if (process_queues[process.owner].size() < max_processes) {
                        process_queues[process.owner].push_back({a_ptr_final, process.owner});
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
