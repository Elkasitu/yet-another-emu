from collections import namedtuple

Flags = namedtuple("Flags", "z s p cy ac pad")
State = namedtuple("State", "a b c d e h l sp pc mem cc int_enable")


def emulate(state):

    def parity(n):
        pass

    opcode = state.mem[state.pc]

    if opcode[0] == 0x01:
        state.c = opcode[1]
        state.b = opcode[2]
    elif opcode[0] == 0x41:
        state.b = state.c
    elif opcode[0] == 0x42:
        state.b = state.d
    elif opcode[0] == 0x43:
        state.b = state.e
    elif opcode[0] == 0x80:     # ADD B
        ans = int(state.a) + int(state.b)
        # set zero flag if ans is 0
        # 0x00 & 0xff = 0x00 True
        # 0x10 & 0xff = 0x10 False
        state.cc.z = ((ans & 0xff) == 0)
        # set sign flag if left-most bit is 1
        # 0b0001 & 0b1000 = 0b0000 -> False
        # 0b1001 & 0b1000 = 0b1000 -> True
        state.cc.s = ((ans & 0x80) != 0)
        # set carry flag if ans is greater than 0xff
        state.cc.cy = ans > 0xff
        # set parity, ans % 2 == 0: True, else False
        state.cc.p = parity(ans & 0xff)
        # store 2 bytes of the result into register a
        state.a = ans & 0xff
    elif opcode[0] == 0x81:     # ADD C
        ans = int(state.a) + int(state.c)
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode[0] == 0x86:     # ADD M
        # shift eight bits left to concatenate H & L
        adr = (state.h << 8) | state.l
        ans = int(state.a) + int(state.memory[adr])
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode[0] == 0xc2:     # JNZ adr
        if state.cc.z == 0:
            state.pc = (opcode[2] << 8) | opcode[1]
        else:
            state.pc += 2
    elif opcode[0] == 0xc3:     # JMP adr
        state.pc = (opcode[2] << 8) | opcode[1]
    elif opcode[0] == 0xc6:     # ADI byte
        ans = int(state.a) + int(opcode[1])
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode[0] == 0xc9:     # RET
        # set pc to ret adr
        state.pc = state.memory[state.sp] | (state.memory[state.sp + 1] << 8)
        # restore stack pointer
        state.sp += 2
    elif opcode[0] == 0xcd:     # CALL adr
        # return address
        ret = state.pc + 2
        # put high part of ret in pos -1 of the stack
        state.memory[state.sp - 1] = (ret >> 8) & 0xff
        # put low part of ret in pos -2 of the stack
        state.memory[state.sp - 2] = ret & 0xff
        state.sp -= 2
        state.pc = (opcode[2] << 8) | opcode[1]

    state.pc += 1
