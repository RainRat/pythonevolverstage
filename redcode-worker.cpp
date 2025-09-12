#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <map>
#include <list>
#include <random>

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
    ORG, NOP // ORG is a pseudo-op, NOP for invalid instructions
};

enum Modifier {
    A, B, AB, BA, F, X, I
};

enum AddressMode {
    IMMEDIATE,  // #
    DIRECT,     // $
    INDIRECT,   // * @
    PREDEC,     // { <
    POSTINC     // } >
};

// --- Data Structures ---

struct Instruction {
    Opcode opcode = DAT;
    Modifier modifier = F;
    AddressMode a_mode = DIRECT;
    int a_field = 0;
    AddressMode b_mode = DIRECT;
    int b_field = 0;
    int owner = -1; // Which warrior owns this instruction

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
    {"DJN", DJN}, {"CMP", CMP}, {"SLT", SLT}, {"SPL", SPL}, {"ORG", ORG}
};

const std::map<std::string, Modifier> MODIFIER_MAP = {
    {"A", A}, {"B", B}, {"AB", AB}, {"BA", BA},
    {"F", F}, {"X", X}, {"I", I}
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
        case '*': case '@': return INDIRECT;
        case '{': case '<': return PREDEC;
        case '}': case '>': return POSTINC;
        default: return DIRECT;
    }
}

Instruction parse_line(const std::string& line) {
    Instruction instr;
    std::string opcode_full, operands_str;
    std::stringstream ss(line);

    // 1. Opcode and optional Modifier
    ss >> opcode_full;
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
    instr.opcode = (op_it != OPCODE_MAP.end()) ? op_it->second : NOP;
    auto mod_it = MODIFIER_MAP.find(modifier_str);
    if (mod_it != MODIFIER_MAP.end()) instr.modifier = mod_it->second;

    // 2. Operands
    std::getline(ss, operands_str);
    // Trim leading space
    operands_str.erase(0, operands_str.find_first_not_of(" \t"));

    std::string a_str, b_str;
    size_t comma_pos = operands_str.find(',');
    if (comma_pos != std::string::npos) {
        a_str = operands_str.substr(0, comma_pos);
        b_str = operands_str.substr(comma_pos + 1);
    } else {
        a_str = operands_str;
        b_str = "$0"; // Default for missing B-field
    }

    // Trim trailing/leading whitespace from operands
    a_str.erase(a_str.find_last_not_of(" \t") + 1);
    b_str.erase(0, b_str.find_first_not_of(" \t"));

    // 3. A-field
    if (!a_str.empty()) {
        if (std::string("#$*@{}<>").find(a_str[0]) != std::string::npos) {
            instr.a_mode = get_mode(a_str[0]);
            try { instr.a_field = std::stoi(a_str.substr(1)); } catch (...) { instr.a_field = 0; }
        } else {
            instr.a_mode = DIRECT;
            try { instr.a_field = std::stoi(a_str); } catch (...) { instr.a_field = 0; }
        }
    }

    // 4. B-field
    if (!b_str.empty()) {
        if (std::string("#$*@{}<>").find(b_str[0]) != std::string::npos) {
            instr.b_mode = get_mode(b_str[0]);
            try { instr.b_field = std::stoi(b_str.substr(1)); } catch (...) { instr.b_field = 0; }
        } else {
            instr.b_mode = DIRECT;
            try { instr.b_field = std::stoi(b_str); } catch (...) { instr.b_field = 0; }
        }
    }

    return instr;
}

std::vector<Instruction> parse_warrior(const std::string& code) {
    std::vector<Instruction> warrior_code;
    std::stringstream ss(code);
    std::string line;
    while (std::getline(ss, line)) {
        // Basic cleaning
        if (line.empty() || line.rfind(";", 0) == 0 || line.rfind("END", 0) == 0) {
            continue;
        }
        warrior_code.push_back(parse_line(line));
    }
    return warrior_code;
}


// --- Core Simulation ---

class Core {
public:
    std::vector<int> instruction_counts;

    Core(int size) : memory(size), core_size(size) {
        instruction_counts.resize(2, 0);
    }

    void execute(WarriorProcess& process, int read_limit, int write_limit, int max_processes) {
        int pc = process.pc;
        Instruction& instr = memory[pc];

        if (instr.opcode == DAT || instr.b_mode == IMMEDIATE) {
            process.pc = -1;
            return;
        }

        // --- Operand Evaluation ---
        int a_ptr_base, a_ptr_final;
        int b_ptr_base, b_ptr_final;

        // 1. Evaluate A-Operand Pointer
        int folded_a_field = fold(instr.a_field, read_limit);
        switch(instr.a_mode) {
            case IMMEDIATE: a_ptr_base = pc; break;
            case DIRECT: a_ptr_base = normalize(pc + folded_a_field, core_size); break;
            case INDIRECT: a_ptr_base = normalize(pc + folded_a_field, core_size); break;
            case PREDEC: a_ptr_base = normalize(pc + folded_a_field, core_size); --memory[a_ptr_base].b_field; break;
            case POSTINC: a_ptr_base = normalize(pc + folded_a_field, core_size); break;
        }

        // 2. Resolve A-Operand Final Pointer
        if (instr.a_mode == INDIRECT || instr.a_mode == PREDEC || instr.a_mode == POSTINC) {
            a_ptr_final = normalize(a_ptr_base + fold(memory[a_ptr_base].b_field, read_limit), core_size);
        } else {
            a_ptr_final = a_ptr_base;
        }

        // 3. Post-increment A if needed
        if (instr.a_mode == POSTINC) {
            ++memory[a_ptr_base].b_field;
        }

        Instruction& src = (instr.a_mode == IMMEDIATE) ? instr : memory[a_ptr_final];

        // 4. Evaluate B-Operand Pointer
        int folded_b_field = fold(instr.b_field, write_limit);
        switch(instr.b_mode) {
            case DIRECT: b_ptr_base = normalize(pc + folded_b_field, core_size); break;
            case INDIRECT: b_ptr_base = normalize(pc + folded_b_field, core_size); break;
            case PREDEC: b_ptr_base = normalize(pc + folded_b_field, core_size); --memory[b_ptr_base].b_field; break;
            case POSTINC: b_ptr_base = normalize(pc + folded_b_field, core_size); break;
            case IMMEDIATE: process.pc = -1; return;
        }

        // 5. Resolve B-Operand Final Pointer
        if (instr.b_mode == INDIRECT || instr.b_mode == PREDEC || instr.b_mode == POSTINC) {
            b_ptr_final = normalize(b_ptr_base + fold(memory[b_ptr_base].b_field, write_limit), core_size);
        } else {
            b_ptr_final = b_ptr_base;
        }

        // 6. Post-increment B if needed
        if (instr.b_mode == POSTINC) {
            ++memory[b_ptr_base].b_field;
        }

        Instruction& dst = memory[b_ptr_final];
        bool skip = false;

        // --- Instruction Execution ---
        switch (instr.opcode) {
            case MOV:
                {
                    int previous_owner = dst.owner;
                    int new_owner = process.owner;
                    if (previous_owner != new_owner) {
                        if (previous_owner != -1) instruction_counts[previous_owner]--;
                        if (new_owner != -1) instruction_counts[new_owner]++;
                    }

                    switch (instr.modifier) {
                        case A: dst.a_field = src.a_field; break;
                        case B: dst.b_field = src.b_field; break;
                        case AB: dst.b_field = src.a_field; break;
                        case BA: dst.a_field = src.b_field; break;
                        case F: dst.a_field = src.a_field; dst.b_field = src.b_field; break;
                        case X: dst.a_field = src.b_field; dst.b_field = src.a_field; break;
                        case I: dst = src; break;
                    }
                    dst.owner = new_owner;
                }
                break;
            case ADD:
                switch (instr.modifier) {
                    case A: dst.a_field += src.a_field; break;
                    case B: dst.b_field += src.b_field; break;
                    case AB: dst.b_field += src.a_field; break;
                    case BA: dst.a_field += src.b_field; break;
                    case F: case I: dst.a_field += src.a_field; dst.b_field += src.b_field; break;
                    case X: dst.a_field += src.b_field; dst.b_field += src.a_field; break;
                }
                break;
            case SUB:
                switch (instr.modifier) {
                    case A: dst.a_field -= src.a_field; break;
                    case B: dst.b_field -= src.b_field; break;
                    case AB: dst.b_field -= src.a_field; break;
                    case BA: dst.a_field -= src.b_field; break;
                    case F: case I: dst.a_field -= src.a_field; dst.b_field -= src.b_field; break;
                    case X: dst.a_field -= src.b_field; dst.b_field -= src.a_field; break;
                }
                break;
            case MUL:
                switch (instr.modifier) {
                    case A: dst.a_field *= src.a_field; break;
                    case B: dst.b_field *= src.b_field; break;
                    case AB: dst.b_field *= src.a_field; break;
                    case BA: dst.a_field *= src.b_field; break;
                    case F: case I: dst.a_field *= src.a_field; dst.b_field *= src.b_field; break;
                    case X: dst.a_field *= src.b_field; dst.b_field *= src.a_field; break;
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
                    if (div_by_zero) process.pc = -1;
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
                    if (div_by_zero) process.pc = -1;
                }
                break;
            case CMP: // Same as SEQ
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
                process.pc = a_ptr_final; return;
            case JMZ:
                switch (instr.modifier) {
                    case A: if (dst.a_field == 0) { process.pc = a_ptr_final; return; } break;
                    case B: if (dst.b_field == 0) { process.pc = a_ptr_final; return; } break;
                    case AB: if (dst.b_field == 0) { process.pc = a_ptr_final; return; } break;
                    case BA: if (dst.a_field == 0) { process.pc = a_ptr_final; return; } break;
                    case F: case I: if (dst.a_field == 0 && dst.b_field == 0) { process.pc = a_ptr_final; return; } break;
                    case X: if (dst.a_field == 0 && dst.b_field == 0) { process.pc = a_ptr_final; return; } break;
                }
                break;
            case JMN:
                 switch (instr.modifier) {
                    case A: if (dst.a_field != 0) { process.pc = a_ptr_final; return; } break;
                    case B: if (dst.b_field != 0) { process.pc = a_ptr_final; return; } break;
                    case AB: if (dst.b_field != 0) { process.pc = a_ptr_final; return; } break;
                    case BA: if (dst.a_field != 0) { process.pc = a_ptr_final; return; } break;
                    case F: case I: if (dst.a_field != 0 || dst.b_field != 0) { process.pc = a_ptr_final; return; } break;
                    case X: if (dst.a_field != 0 || dst.b_field != 0) { process.pc = a_ptr_final; return; } break;
                }
                break;
            case DJN:
                {
                    int val;
                    bool jump = false;
                    switch (instr.modifier) {
                        case A: val = --dst.a_field; if (val != 0) jump = true; break;
                        case B: val = --dst.b_field; if (val != 0) jump = true; break;
                        case AB: val = --dst.b_field; if (val != 0) jump = true; break;
                        case BA: val = --dst.a_field; if (val != 0) jump = true; break;
                        case F: case I:
                            --dst.a_field; --dst.b_field;
                            if (dst.a_field != 0 || dst.b_field != 0) jump = true;
                            break;
                        case X:
                            --dst.a_field; --dst.b_field;
                            if (dst.a_field != 0 || dst.b_field != 0) jump = true;
                            break;
                    }
                    if (jump) { process.pc = a_ptr_final; return; }
                }
                break;
            case SPL:
                {
                    if (process_queues[process.owner].size() < max_processes) {
                        WarriorProcess new_process = { a_ptr_final, process.owner };
                        process_queues[process.owner].push_back(new_process);
                    }
                }
                break;
            default:
                break;
        }

        if (process.pc != -1) {
            process.pc = normalize(pc + (skip ? 2 : 1), core_size);
        }
    }


    std::vector<Instruction> memory;
    int core_size;
    std::map<int, std::list<WarriorProcess>> process_queues;
};


// --- Battle Manager ---
extern "C" {
    const char* run_battle(
        const char* warrior1_code, int w1_id,
        const char* warrior2_code, int w2_id,
        int core_size, int max_cycles, int max_processes,
        int min_distance
    ) {
        // 1. Initialize Core
        Core core(core_size);

        // 2. Parse Warriors
        auto w1_instrs = parse_warrior(warrior1_code);
        auto w2_instrs = parse_warrior(warrior2_code);

        // 3. Load Warriors into Core
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> distrib(0, core_size - 1);

        int w1_start = distrib(gen);
        int w2_start;
        do {
            w2_start = distrib(gen);
        } while (std::abs(w1_start - w2_start) < min_distance);

        for (size_t i = 0; i < w1_instrs.size(); ++i) {
            core.memory[normalize(w1_start + i, core_size)] = w1_instrs[i];
            core.memory[normalize(w1_start + i, core_size)].owner = 0;
        }
        core.instruction_counts[0] = w1_instrs.size();

        for (size_t i = 0; i < w2_instrs.size(); ++i) {
            core.memory[normalize(w2_start + i, core_size)] = w2_instrs[i];
            core.memory[normalize(w2_start + i, core_size)].owner = 1;
        }
        core.instruction_counts[1] = w2_instrs.size();

        // 4. Create initial processes
        core.process_queues[0].push_back({w1_start, 0});
        core.process_queues[1].push_back({w2_start, 1});

        // 5. Run simulation
        for (int cycle = 0; cycle < max_cycles; ++cycle) {
            if (core.process_queues[0].empty() || core.process_queues[1].empty() ||
                core.instruction_counts[0] == 0 || core.instruction_counts[1] == 0) {
                break; // Battle over
            }

            // Execute one process from each warrior's queue
            if (!core.process_queues[0].empty()) {
                WarriorProcess p = core.process_queues[0].front();
                core.process_queues[0].pop_front();
                core.execute(p, core_size, core_size, max_processes);
                if(p.pc != -1) core.process_queues[0].push_back(p);
            }
            if (!core.process_queues[1].empty()) {
                WarriorProcess p = core.process_queues[1].front();
                core.process_queues[1].pop_front();
                core.execute(p, core_size, core_size, max_processes);
                if(p.pc != -1) core.process_queues[1].push_back(p);
            }
        }

        // 6. Determine winner and format result
        int w1_procs = core.process_queues[0].size();
        int w2_procs = core.process_queues[1].size();

        // This is a static buffer. In a real scenario, you'd want to manage memory better.
        static std::string result_str;
        std::stringstream result_ss;

        // Format the output to be compatible with the Python script's parser.
        result_ss << w1_id << " 0 0 0 " << w1_procs << " scores\n";
        result_ss << w2_id << " 0 0 0 " << w2_procs << " scores";

        result_str = result_ss.str();
        return result_str.c_str();
    }
}
