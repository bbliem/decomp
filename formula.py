#!/usr/bin/env python

from collections import namedtuple
import warnings

from graph import Graph
from decomposer import Decomposer

class Literal(namedtuple("Literal", "sign var")):
    # https://stackoverflow.com/questions/7914152/can-i-overwrite-the-string-form-of-a-namedtuple#comment32362249_7914212
    __slots__ = ()

    # def __new__(cls, integer):
    #     sign = (integer >= 0)
    #     var = abs(integer)
    #     self = super(Literal, cls).__new__(cls, sign, var)
    #     return self
    @classmethod
    def from_int(cls, integer):
        sign = (integer >= 0)
        var = abs(integer)
        return cls(sign=sign, var=var)

    def __repr__(self):
        return str(self.var) if self.sign else '-' + str(self.var)

    def negate(self):
        return Literal(not self.sign, self.var)


class Clause(namedtuple("Clause", "weight literals")):
    __slots__ = ()

    # XXX actually this should be __str__, but printing a list of clauses
    # prints the reprs. Here, __repr__ is, strictly speaking, not correct
    # because it's not unique.
    def __repr__(self):
        return f'({" | ".join([str(l) for l in self.literals])})'

    def __hash__(self):
        return hash(self.weight) ^ hash(tuple(self.literals))

    def variables(self):
        return (lit.var for lit in self.literals)

    # Is the clause satisfied by a given set of literals?
    def satisfied(self, assignment):
        return any(assignment[l.var] == l.sign for l in self.literals
                if l.var in assignment.variables)

    # Is the clause falsified by a given set of literals?
    def falsified(self, assignment):
        return all(
                l.var in assignment.variables
                and assignment[l.var] != l.sign
                for l in self.literals)


class Formula(object):
    def __init__(self, f):
        num_clauses = 0
        self.clauses = []
        variables = set()

        for line in f:
            fields = line.split()
            if not fields or fields[0] == 'c':
                # empty or comment line
                pass

            elif fields[0] == 'p':
                # parameters line
                assert len(fields) == 5 and fields[1] == "wcnf", "Unexpected file format"
                self.num_vars = int(fields[2])
                num_clauses = int(fields[3])
                self.hard_weight = int(fields[3])

            else:
                # clause
                assert fields[-1] == '0'
                weight = int(fields[0])
                assert 0 < weight <= self.hard_weight
                clause = [Literal.from_int(int(x)) for x in frozenset(fields[1:-1])]
                assert all([1 <= l.var <= self.num_vars for l in clause]), \
                       "Invalid variable number"
                for l in clause:
                    variables.add(l.var)
                self.clauses.append(Clause(weight=weight, literals=clause))

        if num_clauses != len(self.clauses):
            warnings.warn(f"Read {len(self.clauses)} clauses, "
                          f"but {num_clauses} were declared")

        if self.num_vars != len(variables):
            warnings.warn(f"Saw {len(variables)} variables, "
                          f"but {self.num_vars} were declared")

    def __str__(self):
        return " & ".join([str(c) for c in self.clauses])

    def primal_graph(self):
        g = Graph(self.num_vars)
        for c in self.clauses:
            # make clique
            for (x, y) in [(x.var, y.var) for x in c.literals
                                          for y in c.literals
                                          if x.var < y.var]:
                g.add_edge(x, y)
        return g

    def induced_clauses(self, variables):
        return [c for c in self.clauses
                if all(v in variables for v in c.variables())]


if __name__ == "__main__":
    with open("test.wcnf") as f:
        f = Formula(f)
        print(f)
        g = f.primal_graph()
        print(g)
        td = Decomposer(g).decompose(Graph.min_degree_vertex)
        print(td)

        print(f.induced_clauses(td.node))
