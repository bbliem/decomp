#!/usr/bin/env python

import argparse
import copy
import itertools
import logging
from signal import signal, SIGPIPE, SIG_DFL


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

# Deletes the i'th bit (starting from the right with 0)
def delete_bit(bits, i):
    right_part = bits & (1 << i) - 1
    bits >>= i + 1
    bits <<= i
    return bits | right_part


class Assignment(object):
    # variables: list of variables.
    # bits store the truth values of the given variables, first variable is
    # leftmost bit.
    def __init__(self, variables, bits):
        self.variables = variables
        self.bits = bits
        # Map variable to index in variable list / bit array
        self.index_of = {
                v: i for v, i in
                zip(self.variables, range(len(self.variables) - 1, -1, -1))}

    def __repr__(self):
        return str(self.to_literals())

    def __hash__(self):
        # We only check the bits since we assume that we only hash assignments
        # from the same table, thus the variables are the same
        return self.bits

    # Two assignments are only equal if their variables are in the same order
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.variables == other.variables
                    and self.bits == other.bits)
        return NotImplemented

    def __getitem__(self, key):
        assert key in self.variables
        return self.bit(self.index_of[key])

    # Returns the bit with the given index (counted from the right)
    def bit(self, index):
        return bool(self.bits & (1 << index))

    def consistent(self, other):
        common_vars = [v for v in self.variables if v in other.variables]
        return all(self[v] == other[v] for v in common_vars)

    # Restrict the assignment to the given variables. If a given variable is
    # not in the assignment, it is ignored.
    def restrict(self, variables):
        # The following assertion only holds for our DP algorithm on weakly
        # normalized TDs.
        #assert all(v in self.variables for v in variables)
        indices = [self.index_of[v] for v in variables if v in self.variables]
        bits = 0
        for index in indices:
            bits = (bits << 1) | self.bit(index)
        return Assignment(variables, bits)

    # Return new assignment that extends this one by the given
    # variable-disjoint assignment
    def extend_disjoint(self, new_vars, new_bits):
        assert frozenset(self.variables).isdisjoint(frozenset(new_vars))
        extended_bits = (self.bits << len(new_vars)) | new_bits
        return Assignment(self.variables + new_vars, extended_bits)

    # Returns a new assignment that combines the given ones, which must be
    # consistent with each other
    def combine(*assignments):
        assert all(x.consistent(y)
                   for x, y in itertools.combinations(assignments, 2))
        if not assignments:
            return Assignment([], 0)

        # We first just append all assignments and then eliminate duplicate
        # variables
        combined_vars = []
        combined_bits = 0
        for a in assignments:
            combined_vars.extend(a.variables)
            combined_bits = (combined_bits << len(a.variables)) | a.bits

        # Eliminate duplicates
        seen_vars = set()
        final_vars = []
        i = len(combined_vars)
        for v in combined_vars:
            i -= 1
            if v in seen_vars:
                combined_bits = delete_bit(combined_bits, i)
            else:
                seen_vars.add(v)
                final_vars.append(v)

        return Assignment(final_vars, combined_bits)

    def to_literals(self):
        l = []
        mask = 1 << len(self.variables)
        for var in self.variables:
            mask >>= 1
            sign = bool(self.bits & mask)
            l.append(Literal(sign=sign, var=var))
        return l


class Row(object):
    def __init__(self, assignment, falsified, num_falsified, epts):
        self.assignment = assignment
        self.falsified = falsified
        self.num_falsified = num_falsified
        self.epts = epts

    def __str__(self):
        return "; ".join([str(self.assignment),
                          str(self.falsified),
                          str(self.num_falsified)])

    def __repr__(self):
        return "; ".join([repr(self.assignment),
                          repr(self.falsified),
                          repr(self.num_falsified),
                          repr(self.epts)])

    def __iter__(self):
        return RowIterator(self)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    # Returns a new row that extends this row by the given ept. The new row has
    # no EPTs.
    def extend(self, ept):
        assert all(r.num_falsified <= self.num_falsified for r in ept)
        assignment = Assignment.combine(self.assignment,
                                        *[r.assignment for r in ept])
        falsified = self.falsified.union(*(r.falsified for r in ept))
        return Row(assignment, falsified, self.num_falsified, [])


class RowIterator(object):
    def __init__(self, row):
        self.row = row
        self.ept_it = iter(row.epts)
        self.current_ept = None
        self.child_iterators = None
        self.current_combination = None

    def __iter__(self):
        return self

    def next_ept(self):
        self.current_ept = next(self.ept_it)
        self.child_iterators = [RowIterator(r) for r in self.current_ept]
        self.current_combination = [next(it) for it in self.child_iterators]

    def increment(self, i=0):
        if i == len(self.child_iterators):
            # The last one was the rightmost extension iterator.
            # Use next extension pointer tuple.
            self.next_ept()
            return

        try:
            self.current_combination[i] = next(self.child_iterators[i])
        except StopIteration:
            self.child_iterators[i] = RowIterator(self.current_ept[i])
            self.current_combination[i] = next(self.child_iterators[i])
            self.increment(i + 1)

    def __next__(self):
        if not self.current_ept:
            self.next_ept()
        else:
            self.increment()
        # self.current_combination now contains a row from each child table.
        # We combine these and add the local information.
        return self.row.extend(tuple(self.current_combination))


class Table(object):
    def __init__(self, tree, formula):
        self.td = tree
        self.children = []
        self.local_vars = list(tree.node)
        self.new_vars = list(tree.introduced())
        self.shared_vars = list(tree.shared())

        for subtree in tree.children:
            self.children.append(Table(subtree, formula))

        self.local_clauses = formula.induced_clauses(tree.node)
        # Store clauses that contain an introduced variable.
        self.new_clauses = []
        # For each child, store clauses that are "present" in both this TD node
        # and the child.
        self.shared_clauses = [[]] * len(self.children)
        for c in self.local_clauses:
            if any(v in self.new_vars for v in c.variables()):
                self.new_clauses.append(c)
            else:
                for i, child in enumerate(self.children):
                    if c in child.local_clauses:
                        self.shared_clauses[i].append(c)
        self.rows = {} # maps assignments to rows

    def __iter__(self):
        return iter(self.rows)

    def __str__(self):
        return self.to_str()

    def to_str(self, indent_level=0):
        return '\n'.join(
                '  ' * indent_level
                + str(r) for r in self.rows.values())

    def print_recursively(self, indent_level=0):
        if indent_level > 0:
            print()
        print(self.to_str(indent_level))
        indent_level += 1
        for child in self.children:
            child.print_recursively(indent_level)

    def joinable(self, rows):
        assert len(rows) == len(self.children)
        if len(rows) < 2:
            return True
        return all(r.assignment.consistent(rows[0].assignment)
                   for r in rows[1:])

    def unsat(self):
        return all(r.num_falsified > 0 for r in self.rows.values())

    def unsat_descendants(self):
        if self.unsat():
            yield self
        for c in self.children:
            for d in c.unsat_descendants():
                yield d

    def compute(self):
        for child in self.children:
            child.compute()

        log.debug(f"Now computing table of bag {set(self.td.node)}")

        # Go through all extension pointer tuples (EPTs)
        for ept in itertools.product(
                *(table.rows.values() for table in self.children)):
            log.debug(f"EPT = {ept}")
            if not self.joinable(ept):
                log.debug("  EPT not joinable")
                continue

            restricted_assignments = [
                    r.assignment.restrict(self.shared_vars[i])
                    for i, r in enumerate(ept)]
            log.debug(f"  Restricted assignments: {restricted_assignments}")
            inherited_assignment = Assignment.combine(*restricted_assignments)
            log.debug(f"  Inherited assignment: {inherited_assignment}")
            shared_falsified = [
                    [c for c in r.falsified if c in self.shared_clauses[i]]
                    for i, r in enumerate(ept)]
            num_forgotten_falsified = (
                    sum(r.num_falsified - len(shared_falsified[i])
                        for i, r in enumerate(ept)))
            log.debug(f"  num_forgotten_falsified: {num_forgotten_falsified}")

            for bits in range(1 << len(self.new_vars)):
                assignment = inherited_assignment.extend_disjoint(
                        list(self.new_vars), bits)
                falsified = frozenset(c for c in self.local_clauses
                                      if c.falsified(assignment))
                num_falsified = num_forgotten_falsified + len(falsified)
                log.debug(
                        f"    Row candidate: "
                        f"{Row(assignment, falsified, num_falsified, [ept])}")

                if assignment in self.rows:
                    # XXX unnecessary extra lookup
                    row = self.rows[assignment]
                    if num_falsified < row.num_falsified:
                        log.debug("    Replacing existing row")
                        row.falsified = falsified
                        row.num_falsified = num_falsified
                        row.epts = [ept]
                    elif num_falsified == row.num_falsified:
                        log.debug("    Adding EPT to existing row")
                        assert row.falsified == falsified
                        row.epts.append(ept)
                else:
                    log.debug("    Inserting new row")
                    new_row = Row(assignment, falsified, num_falsified, [ept])
                    self.rows[assignment] = new_row


if __name__ == "__main__":
    signal(SIGPIPE,SIG_DFL)

    parser = argparse.ArgumentParser(
            description="Dynamic programming on a TD of a MaxSAT instance")
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

        print("Resulting tables:")
        root_table.print_recursively()

        for row in root_table.rows.values():
            print(f"Extensions of root row {row}:")
            for extension in row:
                print(extension)

        if root_table.unsat():
            for d in root_table.unsat_descendants():
                print(f"Unsat descendant:\n{d}")
