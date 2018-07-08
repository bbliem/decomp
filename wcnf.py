#!/usr/bin/env python

import argparse
import itertools
import logging
from signal import signal, SIGPIPE, SIG_DFL
import warnings

from formula import Formula, Literal
from graph import Graph
from decomposer import Decomposer


log = logging.getLogger(__name__)

# https://docs.python.org/3/library/itertools.html#itertools-recipes
# def powerset(iterable):
#     "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
#     s = list(iterable)
#     return itertools.chain.from_iterable(
#             itertools.combinations(s, r) for r in range(len(s)+1))


class Assignment(object):
    # a: dict assigning variables to booleans
    def __init__(self, variables, bits):
        self.variables = list(variables)
        self.bits = bits
        # Map variable to index in variable list / bit array
        self.index_of = {v: i for v, i in
                zip(self.variables, range(len(self.variables)))}

    @classmethod
    def from_dict(cls, d):
        bits = 0
        i = 0
        for (var, value) in d.items():
            bits |= value << i
            i += 1
        return cls(list(d), bits)

    def __repr__(self):
        return str(self.to_literals())

    def __hash__(self):
        return self.bits

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.variables == other.variables and self.bits == other.bits
        return NotImplemented

    def __getitem__(self, key):
        assert key in self.variables
        mask = 1 << self.index_of[key]
        return bool(self.bits & mask)

    def consistent(self, other):
        # common_vars = self.a.keys() & other.a.keys()
        # return all(self.a[k] == other.a[k] for k in common_vars)
        common_vars = [v for v in self.variables if v in other.variables]
        return all(self[v] == other[v] for v in common_vars)

    def restrict(self, variables):
        assert(all(v in self.variables for v in variables))
        indices = [self.index_of[v] for v in variables]
        bits = 0
        for index in indices:
            bits = (bits << 1) | (self.bits & bool(1 << index))
        return Assignment(variables, bits)

    def extend(self, new_vars, new_bits):
        assert(frozenset(self.variables).isdisjoint(frozenset(new_vars)))
        new_bits <<= len(self.variables)
        return Assignment(self.variables + new_vars, new_bits | self.bits)

    def to_literals(self):
        l = []
        mask = 1
        for var in self.variables:
            sign = bool(self.bits & mask)
            mask <<= 1
            l.append(Literal(sign=sign, var=var))
        #return [Literal(sign=s, var=v) for (v, s) in self.a.items()]
        return l


class Row(object):
    def __init__(self, falsified, num_falsified):
        self.falsified = falsified
        self.num_falsified = num_falsified

    def __repr__(self):
        return "; ".join([str(self.falsified),
                          str(self.num_falsified)])


class Table(object):
    def __init__(self, tree, formula):
        self.td = tree
        self.children = []
        self.local_vars = list(tree.node)
        self.new_vars = list(tree.introduced())
        self.common_vars = list(tree.common())

        for subtree in tree.children:
            self.children.append(Table(subtree, formula))

        self.local_clauses = formula.induced_clauses(tree.node)
        # self.new_clauses = [c for c in self.local_clauses
        #         if any(v in self.new_vars for v in c.variables())]
        self.new_clauses = []
        self.common_clauses = []
        for c in self.local_clauses:
            if any(v in self.new_vars for v in c.variables()):
                self.new_clauses.append(c)
            else:
                self.common_clauses.append(c)
        # self.rows = set()
        self.rows = {} # maps assignments to rows

    def __iter__(self):
        return iter(self.rows)

    def __str__(self):
        return self.to_str()

    def to_str(self, indent_level=0):
        return '\n'.join(
                '  ' * indent_level
                + str(a) + ": " + str(r) for a, r in self.rows.items())

    def print_recursively(self, indent_level=0):
        print(self.to_str(indent_level))
        indent_level += 1
        for child in self.children:
            child.print_recursively(indent_level)

    def joinable(self, rows):
        assert len(rows) == len(self.children)
        if len(rows) < 2:
            return True
        # true_common_vars = rows[0].true_vars & self.common_vars
        # return all((r.true_vars & self.common_vars) == true_common_vars
        #            for r in rows)
        return all(r.assignment.consistent(rows[0].assignment)
                   for r in rows[1:])

    def compute(self):
        for child in self.children:
            child.compute()

        log.debug(f"Now computing table of bag {set(self.td.node)}")

        # Go through all extension pointer tuples (EPTs)
        for ept in itertools.product(
                *(table.rows.items() for table in self.children)):
            log.debug(f"EPT = {list(ept)}")
            if not self.joinable(ept):
                log.debug("  EPT not joinable")
                continue

            common_assignment = (ept[0][0].restrict(self.common_vars)
                                 if ept else Assignment([], 0))
            common_falsified = [c for c in self.common_clauses
                                if c.falsified(common_assignment)]
            num_old_falsified = (
                    sum(r[1].num_falsified - len(common_falsified)
                        for r in ept)
                    + len(common_falsified))
            # log.debug(f"  Common assignment: {common_assignment}")
            # log.debug(f"  Common falsified: {common_falsified}")

            for bits in range(1 << len(self.new_vars)):
                assignment = common_assignment.extend(list(self.new_vars), bits)
                new_falsified = [c for c in self.new_clauses if c.falsified(assignment)]
                falsified = common_falsified + new_falsified
                num_falsified = num_old_falsified + len(new_falsified)
                log.debug(f"    Row candidate {assignment}: {Row(falsified, num_falsified)}")

                if assignment in self.rows:
                    log.debug("    Assignment already in table")
                    # XXX unnecessary extra lookup
                    row = self.rows[assignment]
                    if num_falsified < row.num_falsified:
                        # Improve the existing row
                        row.falsified = falsified
                        row.num_falsified = num_falsified

                else:
                    new_row = Row(falsified, num_falsified)
                    self.rows[assignment] = new_row


if __name__ == "__main__":
    signal(SIGPIPE,SIG_DFL)

    parser = argparse.ArgumentParser(
            description="Convert a WCNF formula to a graph and decompose it")
    # TODO Add parameter for maximum width
    parser.add_argument("file")
    parser.add_argument("--log", default="info")
    args = parser.parse_args()

    log_level_number = getattr(logging, args.log.upper(), None)
    if not isinstance(log_level_number, int):
        raise ValueError(f"Invalid log level: {loglevel}")
    logging.basicConfig(level=log_level_number)

    with open(args.file) as f:
        formula = Formula(f)
        print(formula)
        g = formula.primal_graph()
        print(g)
        td = Decomposer(g).decompose(Graph.min_degree_vertex)
        print(td)

        root_table = Table(td, formula)
        root_table.compute()

        root_table.print_recursively()
