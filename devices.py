class ShiftRegister:

    def __init__(self):
        self._register = 0x0000
        self._offset = 0x0

    def get_register(self):
        return (self._register >> self._offset) & 0xff

    def shift(self, val):
        self._register = (self._register >> 8) | (val << 7)

    def set_offset(self, val):
        self._offset = (val ^ 0xff) & 0x07


class Controller:

    def __init__(self):
        self._p1_reg = 0x08
        self._p2_reg = 0x00

    def reset(self):
        self._p1_reg = 0x08
        self._p2_reg = 0x00

    def get_p1(self):
        return self._p1_reg

    def get_p2(self):
        return self._p2_reg

    def start_p1(self):
        self._p1_reg |= 0x04

    def start_p2(self):
        self._p1_reg |= 0x02

    def mv_left_p1(self):
        self._p1_reg |= 0x20

    def mv_left_p2(self):
        self._p2_reg |= 0x20

    def mv_right_p1(self):
        self._p1_reg |= 0x40

    def mv_right_p2(self):
        self._p2_reg |= 0x40

    def shoot_p1(self):
        self._p1_reg |= 0x10

    def shoot_p2(self):
        self._p2_reg |= 0x10

    def add_credit(self):
        self._p1_reg |= 0x01


class Display:

    def __init__(self):
        self.max_cycles = 2000000/60

    def refresh(self, cycles):
        if cycles >= self.max_cycles:
            return 0xcf, 0xd7


devices = {
    'shft_reg': ShiftRegister(),
    'ctrl': Controller(),
    'dspl': Display(),
}
