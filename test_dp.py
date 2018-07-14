#!/usr/bin/env python

import unittest

from dp import Assignment, Row, delete_bit
from formula import Literal

class TestAssignment(unittest.TestCase):
    def setUp(self):
        # Assignment {-1, 2}
        self.a1 = Assignment([1, 2], 1)
        # Assignment {1, -2}
        self.a2 = Assignment([1, 2], 2)
        # Assignment {-2}
        self.a3 = Assignment([2], 0)
        # Assignment {3}
        self.a4 = Assignment([3], 1)

    def test_bit(self):
        self.assertEqual(self.a1.bit(0), 1)
        self.assertEqual(self.a1.bit(1), 0)

        self.assertEqual(self.a2.bit(0), 0)
        self.assertEqual(self.a2.bit(1), 1)

        self.assertEqual(self.a3.bit(0), 0)

        self.assertEqual(self.a4.bit(0), 1)

    def test_consistent(self):
        self.assertEqual(self.a1.consistent(self.a1), True)
        self.assertEqual(self.a1.consistent(self.a2), False)
        self.assertEqual(self.a1.consistent(self.a3), False)
        self.assertEqual(self.a1.consistent(self.a4), True)
        self.assertEqual(self.a2.consistent(self.a1), False)
        self.assertEqual(self.a2.consistent(self.a2), True)
        self.assertEqual(self.a2.consistent(self.a3), True)
        self.assertEqual(self.a2.consistent(self.a4), True)
        self.assertEqual(self.a3.consistent(self.a1), False)
        self.assertEqual(self.a3.consistent(self.a2), True)
        self.assertEqual(self.a3.consistent(self.a3), True)
        self.assertEqual(self.a3.consistent(self.a4), True)
        self.assertEqual(self.a4.consistent(self.a1), True)
        self.assertEqual(self.a4.consistent(self.a2), True)
        self.assertEqual(self.a4.consistent(self.a3), True)
        self.assertEqual(self.a4.consistent(self.a4), True)

    def test_extend_disjoint(self):
        a1a4 = self.a1.extend_disjoint(self.a4.variables, self.a4.bits)
        self.assertEqual(a1a4[1], False)
        self.assertEqual(a1a4[2], True)
        self.assertEqual(a1a4[3], True)

        a4a1 = self.a4.extend_disjoint(self.a1.variables, self.a1.bits)
        self.assertEqual(a4a1[1], False)
        self.assertEqual(a4a1[2], True)
        self.assertEqual(a4a1[3], True)

    def test_combine(self):
        self.assertEqual(self.a1.combine(self.a1), self.a1)

        a1a4 = self.a1.combine(self.a4)
        self.assertEqual(a1a4[1], False)
        self.assertEqual(a1a4[2], True)
        self.assertEqual(a1a4[3], True)

        a2a3 = self.a2.combine(self.a3)
        self.assertEqual(a2a3[1], True)
        self.assertEqual(a2a3[2], False)

        a3a4 = self.a3.combine(self.a4)
        self.assertEqual(a3a4[2], False)
        self.assertEqual(a3a4[3], True)

        a2a3a4 = Assignment.combine(self.a2, self.a3, self.a4)
        self.assertEqual(a2a3a4[1], True)
        self.assertEqual(a2a3a4[2], False)
        self.assertEqual(a2a3a4[3], True)

    def test_to_literals(self):
        self.assertEqual(set(self.a1.to_literals()), {Literal.from_int(-1), Literal.from_int(2)})
        self.assertEqual(set(self.a2.to_literals()), {Literal.from_int(1), Literal.from_int(-2)})
        self.assertEqual(set(self.a3.to_literals()), {Literal.from_int(-2)})
        self.assertEqual(set(self.a4.to_literals()), {Literal.from_int(3)})

    def test_delete_bit(self):
        bits = 0b101101
        self.assertEqual(delete_bit(bits, 0), 0b10110)
        self.assertEqual(delete_bit(bits, 1), 0b10111)
        self.assertEqual(delete_bit(bits, 2), 0b10101)
        self.assertEqual(delete_bit(bits, 3), 0b10101)
        self.assertEqual(delete_bit(bits, 4), 0b11101)
        self.assertEqual(delete_bit(bits, 5), 0b01101)
        self.assertEqual(delete_bit(bits, 6), 0b101101)


class TestRow(unittest.TestCase):
    def setUp(self):
        # Row(assignment=[1,2],
        #     falsified={3},
        #     cost=1,
        #     epts=[()])
        self.r1 = Row(Assignment([1, 2], 3), {3}, 1, [()])

        # Row(assignment=[2,-3],
        #     falsified={4},
        #     cost=2,
        #     epts=[(r1)])
        self.r2 = Row(Assignment([2, 3], 2), {4}, 2, [(self.r1,)])

    def test_extend(self):
        r2ext = self.r2.extend((self.r1,))
        self.assertEqual(set(r2ext.assignment.variables), {1, 2, 3})
        self.assertEqual(r2ext.assignment[1], True)
        self.assertEqual(r2ext.assignment[2], True)
        self.assertEqual(r2ext.assignment[3], False)
        self.assertEqual(set(r2ext.falsified), {3, 4})
        self.assertEqual(r2ext.cost, 2)
        self.assertFalse(r2ext.epts)


if __name__ == "__main__":
    unittest.main()
