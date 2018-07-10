#!/usr/bin/env python

import copy
import unittest

from td import TD

class TestTD(unittest.TestCase):
    def setUp(self):
        # TD:
        # 1
        #   2
        self.td1 = TD({1})
        self.td1.add_child(TD({2}))

        # 123
        #   14
        #   25
        #   26
        self.td2 = TD({1, 2, 3})
        self.td2.add_child(TD({1, 4}))
        self.td2.add_child(TD({2, 5}))
        self.td2.add_child(TD({2, 6}))

    def test_weakly_normalize(self):
        td1 = copy.deepcopy(self.td1)
        assert td1 == self.td1 # deliberately not self.assertEqual
        td1.weakly_normalize()
        self.assertEqual(td1, self.td1)

        td2 = copy.deepcopy(self.td2)
        assert td2 == self.td2 # deliberately not self.assertEqual
        td2.weakly_normalize()
        # Expected result:
        join_node = TD({1, 2})
        child1 = TD({1, 2})
        child2 = TD({1, 2})
        child3 = TD({1, 2})
        child1.add_child(TD({1, 4}))
        child2.add_child(TD({2, 5}))
        child3.add_child(TD({2, 6}))
        for c in [child1, child2, child3]:
            join_node.add_child(c)
        expected = TD({1,2,3})
        expected.add_child(join_node)
        self.assertEqual(td2, expected)


if __name__ == "__main__":
    unittest.main()
