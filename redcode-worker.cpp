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
    INDIRECT_A, // *
    INDIRECT_B, // @
    PREDEC_A,   // {
    PREDEC_B,   // <
    POSTINC_A,  // }
    POSTINC_B   // >
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

// --- Core Normalization ---
int normalize(int address, int core_size) {
    address %= core_size;
    if (address < 0) {
        address += core_size;
    }
    return address;
}


// --- Parser ---

AddressMode get_mode(char c) {
    switch (c) {
        case '#': return IMMEDIATE;
        case '$': return DIRECT;
        case '*': return INDIRECT_A;
        case '@': return INDIRECT_B;
        case '{': return PREDEC_A;
        case '<': return PREDEC_B;
        case '}': return POSTINC_A;
        case '>': return POSTINC_B;
        default: return DIRECT; // Default if no mode specified
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

    int get_address(int pc, AddressMode mode, int field) {
        int addr;
        switch (mode) {
            case IMMEDIATE:
                return -1; // Special case, not an address
            case DIRECT:
                return normalize(pc + field, core_size);
            case INDIRECT_A:
                addr = normalize(pc + field, core_size);
                return normalize(pc + memory[addr].a_field, core_size);
            case INDIRECT_B:
                 addr = normalize(pc + field, core_size);
                return normalize(pc + memory[addr].b_field, core_size);
            // Not implementing other modes for this simplified version
            default:
                return normalize(pc + field, core_size);
        }
    }

    Instruction& get_instruction(int pc, AddressMode mode, int field) {
        int address = get_address(pc, mode, field);
        return memory[address];
    }

    void execute(WarriorProcess& process) {
        int pc = process.pc;
        Instruction& instr = memory[pc];

        if (instr.opcode == DAT || instr.b_mode == IMMEDIATE) {
            process.pc = -1;
            return;
        }

        int a_ptr = get_address(pc, instr.a_mode, instr.a_field);
        int b_ptr = get_address(pc, instr.b_mode, instr.b_field);

        Instruction& src = (instr.a_mode == IMMEDIATE) ? instr : memory[a_ptr];
        Instruction& dst = memory[b_ptr];

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

            // Flow control instructions (modifiers have limited/no standard effect)
            case JMP:
                process.pc = a_ptr;
                return;
            case JMZ:
                if (dst.b_field == 0) { // Simplified: only checks B-field
                    process.pc = a_ptr;
                    return;
                }
                break;
            case DJN:
                if (--dst.b_field != 0) { // Simplified: only acts on B-field
                    process.pc = a_ptr;
                    return;
                }
                break;
            case SPL:
                {
                    WarriorProcess new_process = { normalize(pc + 1, core_size), process.owner };
                    process_queues[process.owner].push_back(new_process);
                    process.pc = a_ptr;
                    return;
                }
            default:
                break;
        }

        if (process.pc != -1) {
            process.pc = normalize(pc + 1, core_size);
        }
    }


    std::vector<Instruction> memory;
    int core_size;
    std::map<int, std::list<WarriorProcess>> process_queues;
};


// --- Battle Manager ---
extern "C" {
    const char* run_battle(const char* warrior1_code, int w1_id, const char* warrior2_code, int w2_id) {
        // 1. Initialize Core
        Core core(DEFAULT_CORE_SIZE);

        // 2. Parse Warriors
        auto w1_instrs = parse_warrior(warrior1_code);
        auto w2_instrs = parse_warrior(warrior2_code);

        // 3. Load Warriors into Core
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> distrib(0, DEFAULT_CORE_SIZE - 1);

        int w1_start = distrib(gen);
        int w2_start;
        do {
            w2_start = distrib(gen);
        } while (std::abs(w1_start - w2_start) < DEFAULT_MIN_DISTANCE);

        for (size_t i = 0; i < w1_instrs.size(); ++i) {
            core.memory[normalize(w1_start + i, DEFAULT_CORE_SIZE)] = w1_instrs[i];
            core.memory[normalize(w1_start + i, DEFAULT_CORE_SIZE)].owner = 0;
        }
        core.instruction_counts[0] = w1_instrs.size();

        for (size_t i = 0; i < w2_instrs.size(); ++i) {
            core.memory[normalize(w2_start + i, DEFAULT_CORE_SIZE)] = w2_instrs[i];
            core.memory[normalize(w2_start + i, DEFAULT_CORE_SIZE)].owner = 1;
        }
        core.instruction_counts[1] = w2_instrs.size();

        // 4. Create initial processes
        core.process_queues[0].push_back({w1_start, 0});
        core.process_queues[1].push_back({w2_start, 1});

        // 5. Run simulation
        for (int cycle = 0; cycle < DEFAULT_MAX_CYCLES; ++cycle) {
            if (core.process_queues[0].empty() || core.process_queues[1].empty() ||
                core.instruction_counts[0] == 0 || core.instruction_counts[1] == 0) {
                break; // Battle over
            }

            // Execute one process from each warrior's queue
            if (!core.process_queues[0].empty()) {
                WarriorProcess& p = core.process_queues[0].front();
                core.execute(p);
                core.process_queues[0].pop_front();
                if(p.pc != -1) core.process_queues[0].push_back(p);
            }
            if (!core.process_queues[1].empty()) {
                WarriorProcess& p = core.process_queues[1].front();
                core.execute(p);
                core.process_queues[1].pop_front();
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
        // It expects a line containing "scores" with warrior ID at index 0 and score at index 4.
        result_ss << w1_id << " 0 0 0 " << w1_procs << " scores\n";
        result_ss << w2_id << " 0 0 0 " << w2_procs << " scores";

        result_str = result_ss.str();
        return result_str.c_str();
    }
}
