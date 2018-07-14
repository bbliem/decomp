#!/usr/bin/env python

import argparse
import copy
import itertools
import logging
from signal import signal, SIGPIPE, SIG_DFL
import sys


from decomposer import Decomposer
from formula import Formula, Literal
from graph import Graph
from td import TD


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

def select_falsifying_ep(ept):
    assert any(ep.cost > 0 for ep in ept)
    return next(ep for ep in ept if ep.cost > 0)


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
    def __init__(self, assignment, falsified, cost, epts):
        self.assignment = assignment
        self.falsified = falsified
        self.cost = cost
        self.epts = epts

    def __str__(self):
        return "; ".join([str(self.assignment),
                          '{'+ ','.join(str(c) for c in self.falsified) + '}',
                          str(self.cost)])

    def __repr__(self):
        return "; ".join([repr(self.assignment),
                          repr(self.falsified),
                          repr(self.cost),
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
        assert all(r.cost <= self.cost for r in ept)
        assignment = Assignment.combine(self.assignment,
                                        *[r.assignment for r in ept])
        falsified = self.falsified.union(*(r.falsified for r in ept))
        return Row(assignment, falsified, self.cost, [])

    # def find_falsified(self):
    #     """Find a "small" set of clauses such that every extension of this row
    #     falsifies at least one of these clauses.
    # 
    #     Formally, let C be a collection that contains, for each extension of
    #     this row, the clauses falsified by this extension. We are looking for a
    #     small hitting set for C.
    # 
    #     TODO: Explain more, write a one-liner docstring..."""
    #     assert self.cost > 0
    #     if self.falsified:
    #         return self.falsified
    #     # TODO


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
        return iter(self.rows.values())

    def __str__(self):
        return self.to_str()

    def to_str(self, indent_level=0):
        return '\n'.join(
                '  ' * indent_level
                + str(r) for r in self.rows.values())

    def write_recursively(self, f=sys.stdout, indent_level=0):
        """Write descendants of this table to the given file."""
        if indent_level > 0:
            f.write('\n')
        f.write(self.to_str(indent_level) + '\n')
        indent_level += 1
        for child in self.children:
            child.write_recursively(f, indent_level)

    def joinable(self, rows):
        assert len(rows) == len(self.children)
        if len(rows) < 2:
            return True
        return all(r.assignment.consistent(rows[0].assignment)
                   for r in rows[1:])

    def unsat(self):
        return all(r.cost > 0 for r in self.rows.values())

    def sat(self):
        return not self.unsat()

    def locally_unsat(self):
        return all(r.falsified for r in self.rows.values())

    def deep_unsat_descendants(self):
        if self.unsat() and all(c.sat() for c in self.children):
            yield self
        else:
            if self.locally_unsat():
                yield self
            for c in self.children:
                for d in c.deep_unsat_descendants():
                    yield d

    def compute(self):
        for child in self.children:
            child.compute()

        log.debug(f"Now computing table of bag {set(self.td.node)}")

        # Go through all extension pointer tuples (EPTs)
        for ept in itertools.product(
                *(table.rows.values() for table in self.children)):
            log.debug(f"EPT = {[str(ep) for ep in ept]}")
            if not self.joinable(ept):
                log.debug("  EPT not joinable")
                continue

            restricted_assignments = [
                    r.assignment.restrict(self.shared_vars[i])
                    for i, r in enumerate(ept)]
            log.debug(f"  Restricted assignments: {restricted_assignments}")
            inherited_assignment = Assignment.combine(*restricted_assignments)
            log.debug(f"  Inherited assignment: {inherited_assignment}")
            shared_cost = [
                    [c.weight for c in r.falsified
                        if c in self.shared_clauses[i]]
                    for i, r in enumerate(ept)]
            forgotten_cost = (
                    sum(r.cost - sum(shared_cost[i])
                        for i, r in enumerate(ept)))
            log.debug(f"  forgotten_cost: {forgotten_cost}")

            for bits in range(1 << len(self.new_vars)):
                assignment = inherited_assignment.extend_disjoint(
                        list(self.new_vars), bits)
                falsified = frozenset(c for c in self.local_clauses
                                      if c.falsified(assignment))
                cost = forgotten_cost + sum(c.weight for c in falsified)
                log.debug(
                        f"    Row candidate: "
                        f"{Row(assignment, falsified, cost, [ept])}")

                if assignment in self.rows:
                    # XXX unnecessary extra lookup
                    row = self.rows[assignment]
                    if cost < row.cost:
                        log.debug("    Replacing existing row")
                        row.falsified = falsified
                        row.cost = cost
                        row.epts = [ept]
                    elif cost == row.cost:
                        log.debug("    Adding EPT to existing row")
                        assert row.falsified == falsified
                        row.epts.append(ept)
                else:
                    log.debug("    Inserting new row")
                    new_row = Row(assignment, falsified, cost, [ept])
                    self.rows[assignment] = new_row

    def unsat_cores(self):
        for table in self.deep_unsat_descendants():
            yield table.unsat_core()

    def unsat_core(self):
        assert self.unsat()
        # Unify the falsified clauses of each row.
        # If a row has no falsified clauses, recursively extend it until we
        # reach falsified clauses.
        # return frozenset.union(*(r.find_falsified()
        #                          for r in self.rows.values()))
        # TODO explain the following
        core = set()
        stack = [r for r in self.rows.values()]
        while stack:
            row = stack.pop()
            if row.falsified:
                core |= row.falsified
            else:
                # For each EPT of the row, push an arbitrary EP with positive
                # cost to the stack
                for ept in row.epts:
                    stack.append(select_falsifying_ep(ept))
        return core



if __name__ == "__main__":
    signal(SIGPIPE, SIG_DFL)

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
        print("Parsing...")
        formula = Formula(f)
        log.debug(formula)
        print("Constructing primal graph...")
        g = formula.primal_graph()
        log.debug(g)
        print("Decomposing...")
        td = Decomposer(g, Graph.min_degree_vertex,
                        normalize=TD.weakly_normalize).decompose()
        log.debug(td)
        root_table = Table(td, formula)
        print("Solving...")
        root_table.compute()

        print("Resulting tables:")
        root_table.write_recursively()

        # for row in root_table.rows.values():
        #     print(f"Extensions of root row {row}:")
        #     for extension in row:
        #         print(extension)

        if root_table.unsat():
            print("Some cores:")
            for core in root_table.unsat_cores():
                print(core)
