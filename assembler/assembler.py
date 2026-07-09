"""
tiny-gpu 汇编器

ISA 指令编码格式 (16 bit):
    [15:12] opcode  | [11:8] rd  | [7:4] rs  | [3:0] rt

    BRnzp 特殊格式: [15:12]=0001 | [11:9] nzp | [8]=0 | [7:0] target_addr
    CONST 特殊格式: [15:12]=1001 | [11:8] rd  | [7:0] immediate

寄存器编码:
    R0-R12  -> 0-12
    %blockIdx  -> 13
    %blockDim  -> 14
    %threadIdx -> 15
"""

OPCODES = {
    'NOP':   0b0000,
    'BRNZP': 0b0001,
    'CMP':   0b0010,
    'ADD':   0b0011,
    'SUB':   0b0100,
    'MUL':   0b0101,
    'DIV':   0b0110,
    'LDR':   0b0111,
    'STR':   0b1000,
    'CONST': 0b1001,
    'RET':   0b1111,
}

REGISTERS = {f'R{i}': i for i in range(13)}
REGISTERS['%BLOCKIDX'] = 13
REGISTERS['%BLOCKDIM'] = 14
REGISTERS['%THREADIDX'] = 15


def strip_comment(line):
    """去掉 ; 注释"""
    return line.split(';')[0].strip()


def parse_register(token):
    key = token.upper().strip().rstrip(',')
    if key not in REGISTERS:
        raise ValueError(f"未知寄存器: {token}")
    return REGISTERS[key]


def parse_immediate(token):
    token = token.strip().rstrip(',')
    if token.startswith('#'):
        return int(token[1:])
    return int(token)


def parse_nzp(suffix):
    """将 BR 后缀 (如 'n', 'nz', 'nzp') 转为 3-bit 字段 [N, Z, P]"""
    suffix = suffix.lower()
    nzp = 0b000
    if 'n' in suffix:
        nzp |= 0b100
    if 'z' in suffix:
        nzp |= 0b010
    if 'p' in suffix:
        nzp |= 0b001
    return nzp


def encode_instruction(line, labels=None):
    """
    将单条指令编码为 16-bit 整数。

    参数:
        line:   一条指令字符串 (不含注释、标签)
        labels: 标签地址表 {'LABEL_NAME': address}，用于 BR 指令

    返回:
        16-bit 整数
    """
    if labels is None:
        labels = {}

    tokens = line.split()
    if not tokens:
        return None

    mnemonic = tokens[0].upper()

    if mnemonic == 'NOP':
        return (OPCODES['NOP'] << 12)

    if mnemonic == 'RET':
        return (OPCODES['RET'] << 12)

    if mnemonic.startswith('BR'):
        suffix = mnemonic[2:]
        nzp = parse_nzp(suffix)
        target_token = tokens[1].rstrip(',')
        if target_token in labels:
            target = labels[target_token]
        else:
            target = parse_immediate(target_token)
        return (OPCODES['BRNZP'] << 12) | (nzp << 9) | (target & 0xFF)

    if mnemonic == 'CMP':
        rs = parse_register(tokens[1])
        rt = parse_register(tokens[2])
        return (OPCODES['CMP'] << 12) | (rs << 4) | rt

    if mnemonic in ('ADD', 'SUB', 'MUL', 'DIV'):
        rd = parse_register(tokens[1])
        rs = parse_register(tokens[2])
        rt = parse_register(tokens[3])
        return (OPCODES[mnemonic] << 12) | (rd << 8) | (rs << 4) | rt

    if mnemonic == 'LDR':
        rd = parse_register(tokens[1])
        rs = parse_register(tokens[2])
        return (OPCODES['LDR'] << 12) | (rd << 8) | (rs << 4)

    if mnemonic == 'STR':
        rs = parse_register(tokens[1])
        rt = parse_register(tokens[2])
        return (OPCODES['STR'] << 12) | (rs << 4) | rt

    if mnemonic == 'CONST':
        rd = parse_register(tokens[1])
        imm = parse_immediate(tokens[2])
        return (OPCODES['CONST'] << 12) | (rd << 8) | (imm & 0xFF)

    raise ValueError(f"未知指令: {line}")


def assemble(source_text):
    """
    汇编完整 .asm 程序，返回 (program, data, threads)。

    两种行需要特别处理:
      1. 伪指令 (.threads / .data) — 不占 program memory，只提取参数
      2. 标签 (LABEL:)            — 不占 program memory，只记录地址
    其余的行都是指令，每条指令占 program memory 一行，pc 递增。
    """
    program = []
    data = []
    threads = 0
    labels = {}

    # 预处理: 拆成行列表 (保留行内容，每次循环再单独 strip)
    lines = source_text.split('\n')

    # ================================================================
    # Pass 1: 收集标签地址
    # 目的: 建立 labels 字典，如 {"LOOP": 12}，供 Pass 2 的 BR 指令查表
    # ================================================================
    pc = 0  # 指令计数器: 当前是第几条指令 (从0开始)

    for line in lines:
        line = strip_comment(line)   # 去掉 ; 注释
        line = line.strip()          # 去首尾空白
        if not line:                # 空行跳过
            continue

        # --- 伪指令: 不占 program memory，pc 不变 ---
        if line.startswith('.threads'):
            # 例: ".threads 4" -> tokens = [".threads", "4"]
            tokens = line.split()
            threads = int(tokens[1])
            continue

        if line.startswith('.data'):
            # 例: ".data 1 2 3 4" -> tokens = [".data", "1", "2", "3", "4"]
            tokens = line.split()
            values = [int(t) for t in tokens[1:]]
            data.extend(values)
            continue

        # --- 标签: 形如 "LOOP:" 或 "LOOP: ADD R1, R1, R2" ---
        # 提示: 用 line.split(':', 1) 拆成 [标签名, 剩余部分]
        #   "LOOP:"          -> ["LOOP", ""]      -> 只剩标签，pc 不变
        #   "LOOP: ADD R1.." -> ["LOOP", " ADD R1.."] -> 标签后还有指令，pc 要+1
        if ':' in line:
            parts = line.split(':', 1)
            label_name = parts[0].strip()
            rest = parts[1].strip()

            labels[label_name] = pc

            if rest:
                pc += 1
            continue

        # --- 普通指令: 占 program memory 一行 ---
        pc += 1

    # ================================================================
    # Pass 2: 编码指令
    # 目的: 用 encode_instruction() 把每条指令编码成 16-bit，存入 program
    # 此时 labels 字典已完整，BR 指令可以查表解析标签
    # ================================================================
    pc = 0  # 重新从 0 开始计数

    for line in lines:
        line = strip_comment(line)
        line = line.strip()
        if not line:
            continue

        if line.startswith('.threads') or line.startswith('.data'):
            continue

        if ':' in line:
            parts = line.split(':', 1)
            label_name = parts[0].strip()
            rest = parts[1].strip()
            if not rest:
                continue
            line = rest

        encoded = encode_instruction(line, labels)
        program.append(encoded)
        pc += 1

    return program, data, threads


if __name__ == '__main__':
    # 验证: 用 encode_instruction 逐条编码 matadd，对比 test_matadd.py 的手写二进制

    expected = [
        0b0101000011011110,  # MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # ADD R0, R0, %threadIdx
        0b1001000100000000,  # CONST R1, #0
        0b1001001000001000,  # CONST R2, #8
        0b1001001100010000,  # CONST R3, #16
        0b0011010000010000,  # ADD R4, R1, R0
        0b0111010001000000,  # LDR R4, R4
        0b0011010100100000,  # ADD R5, R2, R0
        0b0111010101010000,  # LDR R5, R5
        0b0011011001000101,  # ADD R6, R4, R5
        0b0011011100110000,  # ADD R7, R3, R0
        0b1000000001110110,  # STR R7, R6
        0b1111000000000000,  # RET
    ]

    instructions = [
        "MUL R0, %blockIdx, %blockDim",
        "ADD R0, R0, %threadIdx",
        "CONST R1, #0",
        "CONST R2, #8",
        "CONST R3, #16",
        "ADD R4, R1, R0",
        "LDR R4, R4",
        "ADD R5, R2, R0",
        "LDR R5, R5",
        "ADD R6, R4, R5",
        "ADD R7, R3, R0",
        "STR R7, R6",
        "RET",
    ]

    all_pass = True
    for i, (inst, exp) in enumerate(zip(instructions, expected)):
        result = encode_instruction(inst)
        status = "OK" if result == exp else "FAIL"
        if result != exp:
            all_pass = False
        print(f"  [{status}] line {i:2d} | {inst:40s} | got 0b{result:016b} | exp 0b{exp:016b}")

    print()
    if all_pass:
        print("=== encode_instruction 验证通过 ===")
    else:
        print("=== 有失败用例 ===")

    # ----------------------------------------------------------------
    # 验证 assemble(): 读取 kernels/matmul.asm，对比 test_matmul.py 的手写二进制
    # ----------------------------------------------------------------
    print()
    print("--- 验证 assemble() with matmul.asm ---")

    import os
    asm_path = os.path.join(os.path.dirname(__file__), '..', 'kernels', 'matmul.asm')
    with open(asm_path) as f:
        program, data, threads = assemble(f.read())

    expected_program = [
        0b0101000011011110,  # MUL R0, %blockIdx, %blockDim
        0b0011000000001111,  # ADD R0, R0, %threadIdx
        0b1001000100000001,  # CONST R1, #1
        0b1001001000000010,  # CONST R2, #2
        0b1001001100000000,  # CONST R3, #0
        0b1001010000000100,  # CONST R4, #4
        0b1001010100001000,  # CONST R5, #8
        0b0110011000000010,  # DIV R6, R0, R2
        0b0101011101100010,  # MUL R7, R6, R2
        0b0100011100000111,  # SUB R7, R0, R7
        0b1001100000000000,  # CONST R8, #0
        0b1001100100000000,  # CONST R9, #0
        0b0101101001100010,  # MUL R10, R6, R2        (LOOP)
        0b0011101010101001,  # ADD R10, R10, R9
        0b0011101010100011,  # ADD R10, R10, R3
        0b0111101010100000,  # LDR R10, R10
        0b0101101110010010,  # MUL R11, R9, R2
        0b0011101110110111,  # ADD R11, R11, R7
        0b0011101110110100,  # ADD R11, R11, R4
        0b0111101110110000,  # LDR R11, R11
        0b0101110010101011,  # MUL R12, R10, R11
        0b0011100010001100,  # ADD R8, R8, R12
        0b0011100110010001,  # ADD R9, R9, R1
        0b0010000010010010,  # CMP R9, R2
        0b0001100000001100,  # BRn LOOP
        0b0011100101010000,  # ADD R9, R5, R0
        0b1000000010011000,  # STR R9, R8
        0b1111000000000000,  # RET
    ]
    expected_data = [1, 2, 3, 4, 1, 2, 3, 4]
    expected_threads = 4

    print(f"  threads: got={threads}, expected={expected_threads}  {'OK' if threads == expected_threads else 'FAIL'}")
    print(f"  data:    got={data}, expected={expected_data}  {'OK' if data == expected_data else 'FAIL'}")

    if len(program) != len(expected_program):
        print(f"  program 长不符: got {len(program)} 条, expected {len(expected_program)} 条  FAIL")
    else:
        all_match = True
        for i, (got, exp) in enumerate(zip(program, expected_program)):
            if got != exp:
                all_match = False
                print(f"  [FAIL] line {i:2d} | got 0b{got:016b} | exp 0b{exp:016b}")
        if all_match:
            print(f"  program: {len(program)} 条指令全部匹配  OK")

    print()
    print("提示: Pass 2 里的 TODO 都填完后，上面的 FAIL 会变成 OK")
