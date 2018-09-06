import argparse

from disassembler import disassemble


def merge_bytes(high, low):
    """
    Merges two separate bytes to create an address

    e.g.:
        param high is 0x3E
        param low is 0xFF
        resulting address will be 0x3EFF
    """
    return (high << 8) | low


def extract_bytes(adr):
    """
    Splits an address into two words

    e.g.:
        param adr is 0x3EFF
        resulting values are 0x3E (high) and 0xFF (low)
    """
    return (adr >> 8) & 0xff, adr & 0xff


def parity(n):
    """ Sets the parity bit for the Flags construct """
    return n % 2 == 0


class Flags:

    def __init__(self):
        self.z = 0
        self.s = 0
        self.p = 0
        self.cy = 0
        self.ac = 0
        self._pad = 3


class State:

    def __init__(self, memory):
        self.memory = bytearray(memory) + bytearray(0x2000)  # ROM + RAM
        self.a = 0
        self.cc = Flags()
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = 0
        self.pc = 0
        self.int_enable = 0

    @property
    def bc(self):
        return merge_bytes(self.b, self.c)

    @bc.setter
    def bc(self, val):
        self.b, self.c = extract_bytes(val)

    @property
    def de(self):
        return merge_bytes(self.d, self.e)

    @de.setter
    def de(self, val):
        self.d, self.e = extract_bytes(val)

    @property
    def hl(self):
        return merge_bytes(self.h, self.l)

    @hl.setter
    def hl(self, val):
        self.h, self.l = extract_bytes(val)


devices = {}


def emulate(state, debug=0):

    opcode, arg1, arg2 = state.memory[state.pc:state.pc + 3]

    if debug:
        disassemble(state.memory, state.pc)
    if debug > 1:
        print("\tC=%d, P=%d, S=%d, Z=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z))
        print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
            state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
        ))

    if opcode == 0x00:
        pass
    elif opcode == 0x01:
        state.c = arg1
        state.b = arg2
        state.pc += 2
    elif opcode == 0x05:     # DCR B
        state.b = (state.b - 1) % 0xff
        state.cc.z = state.b == 0
    elif opcode == 0x06:     # MVI B byte
        state.b = arg1
        state.pc += 1
    elif opcode == 0x09:     # DAD B
        ans = state.hl + state.bc
        state.cc.cy = ans > 0xffff
        state.hl = ans
    elif opcode == 0x0d:     # DCR C
        state.c = (state.c - 1) % 0xff
        state.cc.z = state.c == 0
    elif opcode == 0x0e:     # MVI C byte
        state.c = arg1
        state.pc += 1
    elif opcode == 0x0f:     # RRC / Multiplication
        x = state.a
        state.a = ((x & 1) << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode == 0x11:
        state.d = arg2
        state.e = arg1
        state.pc += 2
    elif opcode == 0x13:
        n = (state.de + 1) % 0xffff
        state.de = n
    elif opcode == 0x19:     # DAD D
        ans = state.de + state.hl
        state.cc.cy = ans > 0xffff
        state.hl = ans
    elif opcode == 0x1a:     # LDAX D
        state.a = state.memory[state.de]
    elif opcode == 0x1f:     # RAR / Division
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode == 0x21:     # LXI H, word
        state.h = arg2
        state.l = arg1
        state.pc += 2
    elif opcode == 0x23:     # INX H
        n = (state.hl + 1) % 0xffff
        state.hl = n
    elif opcode == 0x26:     # MVI H
        state.h = arg1
        state.pc += 1
    elif opcode == 0x29:     # DAD H
        ans = state.hl << 1
        state.cc.cy = ans > 0xffff
        state.hl = ans
    elif opcode == 0x2f:     # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a ^= 0xff
    elif opcode == 0x31:     # LXI SP
        state.sp = merge_bytes(arg2, arg1)
        state.pc += 2
    elif opcode == 0x32:     # STA adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.a
        state.pc += 2
    elif opcode == 0x36:     # MVI M byte
        state.memory[state.hl] = arg1
    elif opcode == 0x3a:     # LDA adr
        adr = merge_bytes(arg2, arg1)
        state.a = state.memory[adr]
        state.pc += 2
    elif opcode == 0x3e:     # MVI A byte
        state.a = arg1
        state.pc += 1
    elif opcode == 0x41:
        state.b = state.c
    elif opcode == 0x42:
        state.b = state.d
    elif opcode == 0x43:
        state.b = state.e
    elif opcode == 0x56:      # MOV D, M
        state.d = state.memory[state.hl]
    elif opcode == 0x5e:      # MOV E, M
        state.e = state.memory[state.hl]
    elif opcode == 0x66:      # MOV H, M
        state.h = state.memory[state.hl]
    elif opcode == 0x6f:      # MOV L, A
        state.l = state.a
    elif opcode == 0x77:      # MOV M, A
        state.memory[state.hl] = state.a
    elif opcode == 0x7a:      # MOV A, D
        state.a = state.d
    elif opcode == 0x7b:      # MOV A, E
        state.a = state.e
    elif opcode == 0x7c:     # MOV A, H
        state.a = state.h
    elif opcode == 0x7e:     # MOV A, M
        state.a = state.memory[state.hl]
    elif opcode == 0x80:     # ADD B
        ans = state.a + state.b
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
        # store a byte of the result into register a
        state.a = ans & 0xff
    elif opcode == 0x81:     # ADD C
        ans = state.a + state.c
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode == 0x86:     # ADD M
        ans = state.a + state.memory[state.hl]
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode == 0xa7:     # ANA A
        ans = state.a & state.a
        state.cc.z = ans == 0
        state.cc.s = (ans & 0x80) != 0
        state.cc.cy = 0
        state.cc.p = parity(ans)
        state.a = ans
    elif opcode == 0xaf:     # XRA A
        ans = state.a ^ state.a
        state.cc.z = ans == 0
        state.cc.s = (ans & 0x80) != 0
        state.cc.cy = 0
        state.cc.p = parity(ans)
        state.a = ans
    elif opcode == 0xc1:     # POP B
        state.c = state.memory[state.sp]
        state.b = state.memory[state.sp + 1]
        state.sp += 2
    elif opcode == 0xc2:     # JNZ adr
        if state.cc.z == 0:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xc3:     # JMP adr
        state.pc = merge_bytes(arg2, arg1)
        return
    elif opcode == 0xc5:     # PUSH B
        state.memory[state.sp - 1] = state.b
        state.memory[state.sp - 2] = state.c
        state.sp -= 2
    elif opcode == 0xc6:     # ADI byte
        ans = state.a + arg1
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
        state.pc += 1
    elif opcode == 0xc9:     # RET
        # set pc to ret adr
        state.pc = merge_bytes(state.memory[state.sp + 1], state.memory[state.sp])
        # restore stack pointer
        state.sp += 2
    elif opcode == 0xcd:     # CALL adr
        # put the return address on the stack first
        ret = state.pc + 2
        hi, lo = extract_bytes(ret)
        state.memory[state.sp - 1] = hi
        state.memory[state.sp - 2] = lo
        state.sp -= 2
        # then go to adr
        state.pc = merge_bytes(arg2, arg1)
        return
    elif opcode == 0xd1:     # POP D
        state.e = state.memory[state.sp]
        state.d = state.memory[state.sp + 1]
        state.sp += 2
    elif opcode == 0xd3:     # OUT byte
        # palceholder while I discover what the device is supposed to do
        devices[arg1] = state.a
        state.pc += 1
    elif opcode == 0xd5:     # PUSH D
        state.memory[state.sp - 1] = state.d
        state.memory[state.sp - 2] = state.e
        state.sp -= 2
    elif opcode == 0xe1:     # POP H
        state.l = state.memory[state.sp]
        state.h = state.memory[state.sp + 1]
        state.sp += 2
    elif opcode == 0xe5:     # PUSH H
        state.memory[state.sp - 1] = state.h
        state.memory[state.sp - 2] = state.l
        state.sp -= 2
    elif opcode == 0xe6:     # ANI byte
        x = state.a & arg1
        state.cc.z = ((x & 0xff) == 0)
        state.cc.s = ((x & 0x80) != 0)
        state.cc.cy = 0
        state.cc.p = parity(x & 0xff)
        state.a = x
        state.pc += 1
    elif opcode == 0xeb:     # XCHG
        state.hl, state.de = state.de, state.hl
    elif opcode == 0xf1:     # POP PSW
        state.a = state.memory[state.sp + 1]
        psw = state.memory[state.sp]
        # copy each meaningful bit from psw to state
        state.cc.z = (0x01 == (psw & 0x01))
        state.cc.s = (0x02 == (psw & 0x02))
        state.cc.p = (0x04 == (psw & 0x04))
        state.cc.cy = (0x08 == (psw & 0x08))
        state.cc.ac = (0x10 == (psw & 0x10))
        state.sp += 2
    elif opcode == 0xf5:     # PUSH PSW
        state.memory[state.sp - 1] = state.a
        psw = state.cc.z
        psw |= state.cc.s << 1
        psw |= state.cc.p << 2
        psw |= state.cc.cy << 3
        psw |= state.cc.ac << 4
        state.memory[state.sp - 2] = psw
        state.sp -= 2
    elif opcode == 0xfb:     # EI
        state.int_enable = 1
    elif opcode == 0xfe:     # CPI byte
        x = state.a - arg1
        state.cc.z = (x & 0xff) == 0
        state.cc.s = (x & 0x80) != 0
        state.cc.p = parity(x & 0xff)
        state.cc.cy = state.a < arg1
        state.pc += 1
    else:
        raise NotImplementedError("opcode %02x is not implemented" % opcode)

    state.pc += 1


def parse():
    parser = argparse.ArgumentParser(
        description="Emulate programs for the Intel 8080 processor"
    )
    parser.add_argument('-d', '--debug', action='count', default=0,
                        help="Display debug output, can be specified up to 3 times")
    parser.add_argument('bin', nargs=1, help="Program to execute")
    return parser.parse_args()


def main():
    args = parse()

    with open(args.bin[0], 'rb') as f:
        state = State(f.read())

    count = 1
    while 1:
        emulate(state, args.debug)
        if args.debug == 3:
            print("Instruction count: %d" % count)
            count += 1


if __name__ == '__main__':
    main()
