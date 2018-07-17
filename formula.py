#!/usr/bin/env python

import argparse
from collections import namedtuple
import logging
from signal import signal, SIGPIPE, SIG_DFL
import sys

from graph import Graph
from decomposer import Decomposer
from td import TD

log = logging.getLogger(__name__)

class Literal(namedtuple("Literal", "sign var")):
    # https://stackoverflow.com/questions/7914152/can-i-overwrite-the-string-form-of-a-namedtuple#comment32362249_7914212
    __slots__ = ()

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

    def __repr__(self):
        return (f'({" | ".join([str(l) for l in self.literals])})'
                f'^{self.weight}')

    def __hash__(self):
        return hash(self.weight) ^ hash(tuple(self.literals))

    def variables(self):
        return (lit.var for lit in self.literals)

    def satisfied(self, assignment):
        """Is the clause satisfied by a given set of literals?"""
        return any(assignment[l.var] == l.sign for l in self.literals
                if l.var in assignment.variables)

    def falsified(self, assignment):
        """Is the clause falsified by a given set of literals?"""
        return all(
                l.var in assignment.variables
                and assignment[l.var] != l.sign
                for l in self.literals)

    def induced_by(self, variables):
        """Are the variables in the clause all in the given iterable?"""
        return all(l.var in variables for l in self.literals)


class Formula(object):
    def __init__(self, f):
        num_clauses = 0
        self.clauses = []
        variables = set()
        sum_of_soft_clauses_weight = 0

        for line in f:
            fields = line.split()
            if not fields or fields[0] == 'c':
                # empty or comment line
                pass

            elif fields[0] == 'p':
                # parameters line
                assert len(fields) == 5 and fields[1] == "wcnf", \
                        "Unexpected file format"
                num_vars = int(fields[2])
                num_clauses = int(fields[3])
                # Weight of hard clauses must be greater than the sum of the
                # weights of all soft clauses
                self.hard_weight = int(fields[4])

            else:
                # clause
                assert fields[-1] == '0'
                weight = int(fields[0])
                assert 0 < weight
                if weight < self.hard_weight:
                    sum_of_soft_clauses_weight += weight
                clause = [
                        Literal.from_int(int(x))
                        for x in frozenset(fields[1:-1])]
                assert all([1 <= l.var <= num_vars for l in clause]), \
                       "Invalid variable number"
                for l in clause:
                    variables.add(l.var)
                self.clauses.append(Clause(weight=weight, literals=clause))

        if num_clauses != len(self.clauses):
            log.warning(f"Read {len(self.clauses)} clauses, "
                        f"but {num_clauses} were declared")

        if num_vars != len(variables):
            log.warning(f"Saw {len(variables)} variables, "
                        f"but {num_vars} were declared")

        if self.hard_weight < sum_of_soft_clauses_weight:
            log.warning("Hard clause weight from p-line less than sum of"
                        "weights of soft clauses")

    def __str__(self):
        return " & ".join([str(c) for c in self.clauses])

    def variables(self):
        return set.union(*(set(c.variables()) for c in self.clauses))

    def primal_graph(self):
        g = Graph(len(self.variables()))
        for c in self.clauses:
            # make clique
            for (x, y) in [(x.var, y.var) for x in c.literals
                                          for y in c.literals
                                          if x.var < y.var]:
                g.add_edge(x, y)
        return g

    def induced_clauses(self, variables):
        return [c for c in self.clauses if c.induced_by(variables)]

    # Change variable names so that they are consecutive numbers.
    def remove_variable_gaps(self):
        new_var_number = {}
        num_vars = 0
        for c in self.clauses:
            for l in c.literals:
                if l.var not in new_var_number:
                    num_vars += 1
                    new_var_number[l.var] = num_vars
        for c in self.clauses:
            for i, l in enumerate(c.literals):
                c.literals[i] = Literal(l.sign, new_var_number[l.var])
        assert self.consecutive_variables()

    def consecutive_variables(self):
        """Return True if the variables are consecutive and start at 1."""
        variables = self.variables()
        max_var = max(variables)
        return min(variables) == 1 and len(variables) == max_var

    def write_wcnf(self, f=sys.stdout):
        """Write the formula to the given file in WCNF format."""
        assert self.hard_weight > sum(c.weight for c in self.clauses
                                      if c.weight < self.hard_weight), \
                f"Weight of hard clauses is {self.hard_weight}, but " \
                f"should be greater than the sum of weights of soft clauses " \
                + str(sum(c.weight for c in self.clauses))
        f.write(f"p wcnf {len(self.variables())} {len(self.clauses)}"
                f" {self.hard_weight}\n")
        for c in self.clauses:
            f.write(str(c.weight) + ' ' + ' '.join(str(l) for l in c.literals)
                    + " 0\n")


if __name__ == "__main__":
    signal(SIGPIPE,SIG_DFL)

    parser = argparse.ArgumentParser(
            description="Convert a WCNF formula to a graph and decompose it")
    parser.add_argument("file")
    parser.add_argument("--max-width", type=int)
    parser.add_argument("--heuristic", choices=["min-degree", "min-fill"],
                        default="min-degree")
    parser.add_argument("--normalize", choices=["weak"])
    args = parser.parse_args()

    if args.heuristic == "min-degree":
        heuristic = Graph.min_degree_vertex
    elif args.heuristic == "min-fill":
        heuristic = Graph.min_fill_vertex

    normalize = None
    if args.normalize == "weak":
        normalize = TD.weakly_normalize

    with open(args.file) as f:
        f = Formula(f)
        print(f)
        g = f.primal_graph()
        print(g)
        decomposer = Decomposer(g, heuristic,
                                max_width=args.max_width,
                                normalize=normalize)
        tds = decomposer.decompose()
        headline = "Partial TD" if len(tds) > 1 else "TD"
        for td in tds:
            print(f"{headline}:\n{td}")
        remainder = decomposer.remainder()
        if remainder:
            print(f"Remainder: {remainder}")
