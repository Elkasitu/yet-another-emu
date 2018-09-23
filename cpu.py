import argparse
import numpy as np
import pygame
import time

from disassembler import disassemble
from bus import bus


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

    def __int__(self):
        return self.z | (self.s << 1) | (self.p << 2) | (self.cy << 3) | (self.ac << 4)


class State:

    def __init__(self, memory):
        self.memory = bytearray(memory) + bytearray(0x2000)  # ROM + RAM
        self.a = 0
        self._cc = Flags()
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = 0
        self.pc = 0
        self.int_enable = 0
        self.cycles = 0

    def calc_flags(self, ans, single=True):
        mask = 0xff if single else 0xffff
        self.cc.z = (ans & mask) == 0
        self.cc.s = (ans & (mask - (mask >> 1))) != 0
        self.cc.cy = ans > mask
        self.cc.p = parity(ans & mask)

    def nop(self):
        self.cycles += 4

    def push(self, reg):
        """
        Push a register pair onto the stack.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw|pc]
        """
        assert reg in 'bc de hl psw pc'.split(), "Register %s is not valid" % reg

        self.memory[self.sp - 1], self.memory[self.sp - 2] = extract_bytes(getattr(self, reg))
        self.sp -= 2
        self.cycles += 11

    def pop(self, reg):
        """
        Pop a value from the stack into a register pair.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw]
        """
        assert reg in 'bc de hl psw'.split(), "Register %s is not valid" % reg

        setattr(self, reg, merge_bytes(self.memory[self.sp + 1], self.memory[self.sp]))
        self.sp += 2
        self.cycles += 10

    def lxi(self, reg, high, low):
        """
        Set a register pair to the specified bytes

        Arguments:
            reg (str): register pair name [bc|de|hl|psw|sp]
            high (int): high byte
            low (int): low byte
        """
        assert reg in 'bc de hl psw sp'.split(), "Register %s is not valid" % reg

        setattr(self, reg, merge_bytes(high, low))
        self.pc += 2
        self.cycles += 10

    def dcr(self, reg):
        """
        Decrease the specified register by 1

        Arguments:
            reg (str): register name [a|b|c|d|e|h|l|m]
        """
        assert reg in 'b c d e h l m a'.split(), "Register %s is not valid" % reg

        if reg == 'm':
            ans = self.memory[self.hl] - 1
        else:
            ans = getattr(self, reg) - 1

        self.calc_flags(ans)

        if reg == 'm':
            self.memory[self.hl] = ans & 0xff
            self.cycles += 10
        else:
            setattr(self, reg, ans & 0xff)
            self.cycles += 5

    def mvi(self, reg, val):
        if reg == 'm':
            self.memory[self.hl] = val
            self.cycles += 10
        else:
            setattr(self, reg, val)
            self.cycles += 7
        self.pc += 1

    def dad(self, reg):
        ans = self.hl + getattr(self, reg)
        self.cc.cy = ans > 0xffff
        self.hl = ans
        self.cycles += 10

    def inx(self, reg):
        ans = getattr(self, reg) + 1
        self.calc_flags(ans, False)
        setattr(self, reg, ans & 0xffff)
        self.cycles += 5

    def dcx(self, reg):
        ans = getattr(self, reg) - 1
        self.calc_flags(ans, False)
        setattr(self, reg, ans & 0xffff)
        self.cycles += 5

    def inr(self, reg):
        ans = getattr(self, reg) + 1
        self.calc_flags(ans)
        setattr(self, reg, ans & 0xff)
        self.cycles += 5

    def add(self, reg):
        if reg == 'm':
            ans = self.a + self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a + getattr(self, reg)
            self.cycles += 4
        self.calc_flags(ans)
        self.a = ans & 0xff

    def ana(self, reg):
        if reg == 'm':
            ans = self.a & self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a & getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def ora(self, reg):
        if reg == 'm':
            ans = self.a | self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a | getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def xra(self, reg):
        if reg == 'm':
            ans = self.a ^ self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a ^ getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def stax(self, reg):
        self.memory[getattr(self, reg)] = self.a
        self.cycles += 7

    def rst(self, i):
        self.int_enable = 0
        self.push('pc')
        self.pc = 8 * i
        self.cycles += 11

    @property
    def cc(self):
        return self._cc

    @cc.setter
    def cc(self, val):
        self._cc.z = (0x01 == (val & 0x01))
        self._cc.s = (0x02 == (val & 0x02))
        self._cc.p = (0x04 == (val & 0x04))
        self._cc.cy = (0x08 == (val & 0x08))
        self._cc.ac = (0x10 == (val & 0x10))

    @property
    def psw(self):
        return merge_bytes(self.a, int(self.cc))

    @psw.setter
    def psw(self, val):
        self.a, self.cc = extract_bytes(val)

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

    @property
    def bitmap(self):

        def bitarray(byte):
            return [(byte >> i) & 1 for i in range(7, -1, -1)]

        def bit2rgb(bit):
            if bit:
                return [255, 255, 255]
            return [0, 0, 0]

        video_ram = self.memory[0x2400:]

        bytemap = []
        for i in range(224):
            start = i * 32
            # Inverse bcz little-endianness?
            bytemap.append(video_ram[start:start + 32][::-1])

        bitmap = []
        for row in bytemap:
            line = []
            for byte in row:
                line += bitarray(byte)
            bitmap.append(line)

        for i, row in enumerate(bitmap):
            for j, col in enumerate(row):
                bitmap[i][j] = bit2rgb(col)

        return np.array(bitmap)


def emulate(state, debug=0, opcode=None):

    # XXX: You *really* don't wanna reach the end of the memory
    if not opcode:
        opcode, arg1, arg2 = state.memory[state.pc:state.pc + 3]
        if debug:
            disassemble(state.memory, state.pc)
        if debug > 1:
            print("\tC=%d, P=%d, S=%d, Z=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z))
            print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
                state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
            ))

    if opcode == 0x00:
        # NOP
        state.nop()
    elif opcode == 0x01:
        # LXI B, D16
        state.lxi('bc', arg2, arg1)
    elif opcode == 0x02:
        # STAX B
        state.stax('bc')
    elif opcode == 0x03:
        # INX B
        state.inx('bc')
    elif opcode == 0x04:
        # INR B
        state.inr('b')
    elif opcode == 0x05:
        # DCR B
        state.dcr('b')
    elif opcode == 0x06:
        # MVI B, D8
        state.mvi('b', arg1)
    elif opcode == 0x07:
        # RLC
        h = state.a & 0x80
        state.cc.cy = h
        state.a = (state.a << 1) | h
        state.cycles += 4
    elif opcode == 0x09:
        # DAD B
        state.dad('bc')
    elif opcode == 0x0a:
        # LDAX B
        state.a = state.memory[state.bc]
        state.cycles += 7
    elif opcode == 0x0b:
        # DCX B
        state.dcx('bc')
    elif opcode == 0x0c:
        # INR C
        state.inr('c')
    elif opcode == 0x0d:
        # DCR C
        state.dcr('c')
    elif opcode == 0x0e:
        # MVI C, D8
        state.mvi('c', arg1)
    elif opcode == 0x0f:
        # RRC
        x = state.a
        state.a = ((x & 1) << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
        state.cycles += 4
    elif opcode == 0x11:
        # LXI D, D16
        state.lxi('de', arg2, arg1)
    elif opcode == 0x12:
        # STAX D
        state.stax('de')
    elif opcode == 0x13:
        # INX D
        state.inx('de')
    elif opcode == 0x14:
        # INR D
        state.inr('d')
    elif opcode == 0x15:
        # DCR D
        state.dcr('d')
    elif opcode == 0x16:
        # MVI D, D8
        state.mvi('d')
    elif opcode == 0x17:
        # RAL
        x = state.a
        state.a = (x << 1) | state.cc.cy
        state.cc.cy = (x & 0x80) == 1
        state.cycles += 4
    elif opcode == 0x19:
        # DAD D
        state.dad('de')
    elif opcode == 0x1a:
        # LDAX D
        state.a = state.memory[state.de]
        state.cycles += 7
    elif opcode == 0x1b:
        # DCX D
        state.dcx('de')
    elif opcode == 0x1c:
        # INR E
        state.inr('e')
    elif opcode == 0x1d:
        # DCR E
        state.dcr('e')
    elif opcode == 0x1e:
        # MVI E, D8
        state.mvi('e', arg1)
    elif opcode == 0x1f:
        # RAR
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
        state.cycles += 4
    elif opcode == 0x21:
        # LXI H, D16
        state.lxi('hl', arg2, arg1)
    elif opcode == 0x22:
        # SHLD, adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.l
        state.memory[adr + 1] = state.h
        state.cycles += 16
        state.pc += 2
    elif opcode == 0x23:
        # INX H
        state.inx('hl')
    elif opcode == 0x24:
        # INR H
        state.inr('h')
    elif opcode == 0x25:
        # DCR H
        state.dcr('h')
    elif opcode == 0x26:
        # MVI H, D8
        state.mvi('h', arg1)
    elif opcode == 0x27:
        # DAA
        lsb = state.a & 0x0f
        if lsb > 9 or state.cc.ac:
            state.a |= 0x06
        state.cc.ac = lsb + 6 > 0x0f
        hsb = state.a >> 4
        if hsb > 9 or state.cc.cy:
            ans = (state.a | 0x60) & 0xff
        if ans > 0xff:
            state.cc.cy = 1
        state.cc.p = parity(ans)
        state.cc.z = ans == 0
        state.cc.s = (ans & 0x80) != 0
        state.cycles += 4
    elif opcode == 0x29:
        # DAD H
        state.dad('hl')
    elif opcode == 0x2e:
        # MVI L, D8
        state.mvi('l', arg1)
    elif opcode == 0x2f:
        # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a ^= 0xff
        state.cycles += 4
    elif opcode == 0x31:
        # LXI SP, D16
        state.lxi('sp', arg2, arg1)
    elif opcode == 0x32:
        # STA adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.a
        state.pc += 2
        state.cycles += 13
    elif opcode == 0x35:
        # DCR M
        state.dcr('m')
    elif opcode == 0x36:
        # MVI M, D8
        state.mvi('m', arg1)
    elif opcode == 0x37:
        # STC
        state.cc.cy = 1
        state.cycles += 4
    elif opcode == 0x3a:
        # LDA adr
        adr = merge_bytes(arg2, arg1)
        state.a = state.memory[adr]
        state.pc += 2
        state.cycles += 13
    elif opcode == 0x3d:
        # DCR A
        state.dcr('a')
    elif opcode == 0x3e:
        # MVI A, D8
        state.mvi('a', arg1)
    elif opcode == 0x41:
        # MOV B, C
        state.b = state.c
        state.cycles += 5
    elif opcode == 0x42:
        # MOV B, D
        state.b = state.d
        state.cycles += 5
    elif opcode == 0x43:
        # MOV, B, E
        state.b = state.e
        state.cycles += 5
    elif opcode == 0x46:
        # MOV B, M
        state.b = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x4f:
        # MOV C, A
        state.c = state.a
        state.cycles += 5
    elif opcode == 0x56:
        # MOV D, M
        state.d = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x57:
        # MOV D, A
        state.d = state.a
        state.cycles += 5
    elif opcode == 0x5e:
        # MOV E, M
        state.e = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x5f:
        # MOV E, A
        state.e = state.a
        state.cycles += 5
    elif opcode == 0x66:
        # MOV H, M
        state.h = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x67:
        # MOV H, A
        state.h = state.a
        state.cycles += 5
    elif opcode == 0x6f:
        # MOV L, A
        state.l = state.a
        state.cycles += 5
    elif opcode == 0x77:
        # MOV M, A
        state.memory[state.hl] = state.a
        state.cycles += 7
    elif opcode == 0x79:
        # MOv A, C
        state.a = state.c
        state.cycles += 5
    elif opcode == 0x7a:
        # MOV A, D
        state.a = state.d
        state.cycles += 5
    elif opcode == 0x7b:
        # MOV A, E
        state.a = state.e
        state.cycles += 5
    elif opcode == 0x7c:
        # MOV A, H
        state.a = state.h
        state.cycles += 5
    elif opcode == 0x7d:
        # MOV A, L
        state.a = state.l
        state.cycles += 5
    elif opcode == 0x7e:
        # MOV A, M
        state.a = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x80:
        # ADD B
        state.add('b')
    elif opcode == 0x81:
        # ADD C
        state.add('c')
    elif opcode == 0x86:
        # ADD M
        state.add('m')
    elif opcode == 0xa7:
        # ANA A
        state.ana('a')
    elif opcode == 0xaf:
        # XRA A
        state.xra('a')
    elif opcode == 0xb0:
        # ORA B
        state.ora('b')
    elif opcode == 0xb3:
        # ORA E
        state.ora('e')
    elif opcode == 0xb6:
        # ORA M
        state.ora('m')
    elif opcode == 0xc1:
        # POP B
        state.pop('bc')
    elif opcode == 0xc2:
        # JNZ adr
        state.cycles += 10
        if state.cc.z == 0:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xc3:
        # JMP adr
        state.pc = merge_bytes(arg2, arg1)
        state.cycles += 10
        return
    elif opcode == 0xc5:
        # PUSH B
        state.push('bc')
    elif opcode == 0xc6:
        # ADI byte
        ans = state.a + arg1
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
        state.pc += 1
        state.cycles += 7
    elif opcode == 0xc8:
        # RZ
        if state.cc.z:
            state.pc = merge_bytes(state.memory[state.sp + 1], state.memory[state.sp])
            state.sp += 2
            state.cycles += 11
            return
        else:
            state.cycles += 5
    elif opcode == 0xc9:
        # RET
        # set pc to ret adr
        state.pc = merge_bytes(state.memory[state.sp + 1], state.memory[state.sp])
        # restore stack pointer
        state.sp += 2
        state.cycles += 10
        return
    elif opcode == 0xca:
        # JZ
        state.cycles += 10
        if state.cc.z:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xcd:
        # CALL adr
        # put the return address on the stack first
        ret = state.pc + 3
        hi, lo = extract_bytes(ret)
        state.memory[state.sp - 1] = hi
        state.memory[state.sp - 2] = lo
        state.sp -= 2
        # then go to adr
        state.pc = merge_bytes(arg2, arg1)
        state.cycles += 17
        return
    elif opcode == 0xcf:
        # RST 1
        state.rst(1)
        return
    elif opcode == 0xd1:
        # POP D
        state.pop('de')
    elif opcode == 0xd2:
        # JNC adr
        state.cycles += 10
        if not state.cc.cy:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xd3:
        # OUT byte
        bus.write(arg1, state.a)
        state.pc += 1
        state.cycles += 10
    elif opcode == 0xd5:
        # PUSH D
        state.push('de')
    elif opcode == 0xd7:
        # RST 2
        state.rst(2)
        return
    elif opcode == 0xd8:
        # RC
        if state.cc.cy:
            state.cycles += 11
            state.pc = merge_bytes(state.memory[state.sp + 1], state.memory[state.sp])
            state.sp += 2
            return
        else:
            state.cycles += 5
    elif opcode == 0xda:
        # JC adr
        state.cycles += 10
        if state.cc.cy:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xdb:
        # IN byte
        state.a = bus.read(arg1)
        state.pc += 1
        state.cycles += 10
    elif opcode == 0xe1:
        # POP H
        state.pop('hl')
    elif opcode == 0xe3:
        # XTHL
        state.l, state.memory[state.sp] = state.memory[state.sp], state.l
        state.h, state.memory[state.sp + 1] = state.memory[state.sp + 1], state.h
        state.cycles += 18
    elif opcode == 0xe5:
        # PUSH H
        state.push('hl')
    elif opcode == 0xe6:
        # ANI byte
        x = state.a & arg1
        state.cc.z = ((x & 0xff) == 0)
        state.cc.s = ((x & 0x80) != 0)
        state.cc.cy = 0
        state.cc.p = parity(x & 0xff)
        state.a = x
        state.pc += 1
        state.cycles += 7
    elif opcode == 0xe9:
        # PCHL
        state.pc = state.hl
        state.cycles += 5
    elif opcode == 0xeb:
        # XCHG
        state.hl, state.de = state.de, state.hl
        state.cycles += 5
    elif opcode == 0xf1:
        # POP PSW
        state.pop('psw')
    elif opcode == 0xf5:
        # PUSH PSW
        state.push('psw')
    elif opcode == 0xfb:
        # EI
        state.int_enable = 1
        state.cycles += 4
    elif opcode == 0xfe:
        # CPI, D8
        x = state.a - arg1
        state.cc.z = (x & 0xff) == 0
        state.cc.s = (x & 0x80) != 0
        state.cc.p = parity(x & 0xff)
        state.cc.cy = state.a < arg1
        state.pc += 1
        state.cycles += 7
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

    pygame.display.init()
    screen = pygame.display.set_mode((224, 256))

    count = 1
    while 1:
        if state.int_enable:
            if bus.loop(state.cycles):
                # Screen refresh
                screen.fill((0, 0, 0))
                pygame.surfarray.blit_array(screen, state.bitmap)
                pygame.display.flip()
                state.cycles = 0
                emulate(state, args.debug, bus.interrupts.popleft())
                continue

        emulate(state, args.debug)

        if args.debug >= 3:
            print("Instruction count: %d" % count)
            count += 1

        if args.debug >= 4:
            print("Current cycles: %d" % state.cycles)


if __name__ == '__main__':
    main()
