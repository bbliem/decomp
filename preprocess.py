#!/usr/bin/env python

import argparse
import io
import logging
import signal
from td import TD

from collections import namedtuple
from decomposer import Decomposer
from dp import Table
from formula import Formula, Clause, Literal
from graph import Graph
import qm

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

log = logging.getLogger(__name__)

FormulaChange = namedtuple("FormulaChange", "add_var add_cl remove_cl_indices")
# Contains a list of clauses to add as well as a set of *indices* of clauses to
# remove

def on_timeout():
    raise Exception()

def invert_bits(bits, num_bits):
    return ((1 << num_bits) - 1) ^ bits

def process_table(table, td, formula, greatest_var, simplify_clauses):
    bag_union = td.union_of_bags()
    forgotten = bag_union - td.node
    formula_change = FormulaChange(add_var=[],
                                   add_cl=[],
                                   remove_cl_indices=set())

    log.info(f"Processing table with hard weight {table.hard_weight}")
    for i, c in enumerate(formula.clauses):
        # if c.induced_by(bag_union):
        if any(l.var in forgotten for l in c.literals):
            # Remove clause
            formula_change.remove_cl_indices.add(i)
            log.info(f"Found clause to be deleted {c}")

    if simplify_clauses:
        assignments_by_cost = {}
        variables = None
        for row in table:
            if not variables:
                variables = row.assignment.variables
            assert row.assignment.variables == variables

            local_cost = sum(c.weight for c in row.falsified)
            forgotten_cost = row.cost - local_cost
            if forgotten_cost > 0 and local_cost < formula.hard_weight:
                if row.cost < table.hard_weight:
                    # cost = row.cost
                    cost = forgotten_cost
                else:
                    cost = formula.hard_weight
                log.debug(f"Found assignment {row.assignment} with cost {cost}")
                if cost not in assignments_by_cost:
                    assignments_by_cost[cost] = []
                assignments_by_cost[cost].append(row.assignment)

        # For each weight, minimize the clauses to be added (Quine-McCluskey)
        for cost, assignments in assignments_by_cost.items():
            if len(assignments) < 3:
                log.debug(f"Only {len(assignments)} assignments of cost {cost}; "
                          "not simplifying")
                for assignment in assignments:
                    new_clause = Clause(
                            cost,
                            [l.negate() for l in assignment.to_literals()])
                    formula_change.add_cl.append(new_clause)
                    log.info(f"Found new clause to be added: {new_clause}")
                continue

            # Add a new dummy variable, which will incur a cost of 'cost' when
            # false. We enforce that it is set to false when any of the clauses
            # in the simplification would be violated. For this, we add its
            # negation to each clause of the simplification and make this a
            # hard clause.
            # If we instead turned each clause in the simplification into a
            # soft clause, we may pay one cost multiple times if multiple
            # clauses in the simplification are violated. This would make
            # our technique unsound.
            greatest_var += 1
            formula_change.add_var.append(greatest_var)
            new_clause = Clause(cost, [Literal(sign=True, var=greatest_var)])
            formula_change.add_cl.append(new_clause)

            log.info(f"Found new clause to be added: {new_clause} "
                     "(along with new dummy variable)")

            bitstrings = [a.bits for a in assignments]
            log.debug(f"Minimizing cost {cost} assignments "
                      f"{[bin(s) for s in bitstrings]} over "
                      f"{variables} using Quine-McCluskey")
            result = qm.QuineMcCluskey().simplify(bitstrings,
                                                  dc=[],
                                                  num_bits=len(variables))
            for assignment in result:
                literals = []
                for i, value in enumerate(assignment):
                    if value == '1':
                        literals.append(Literal(sign=False,
                                                var=variables[i]))
                    elif value == '0':
                        literals.append(Literal(sign=True,
                                                var=variables[i]))
                # new_clause = Clause(cost, literals)
                # formula_change.add_cl.append(new_clause)
                # log.info(f"Found new clause to be added: {new_clause} (obtained by simplification)")
                new_clause = Clause(formula.hard_weight,
                                    literals + [Literal(sign=False, var=greatest_var)])
                formula_change.add_cl.append(new_clause)
                log.info(f"Found new clause to be added: {new_clause} (obtained by simplification)")

    else: # not simplify_clauses
        for row in table:
            local_cost = sum(c.weight for c in row.falsified)
            forgotten_cost = row.cost - local_cost
            # Add a clause if the row's cost exceeds the local cost, unless the
            # local cost exceeds the hard weight (since we don't care about the
            # cost if we know that hard constraints are violated)
            if forgotten_cost > 0 and local_cost < formula.hard_weight:
                if row.cost < table.hard_weight:
                    new_cost = forgotten_cost
                else:
                    new_cost = formula.hard_weight
                new_clause = Clause(
                        new_cost,
                        [l.negate() for l in row.assignment.to_literals()])
                log.info(f"Found new clause to be added: {new_clause}")
                formula_change.add_cl.append(new_clause)

        # for row in table:
        #     if row.cost > 0:
        #         if row.cost < table.hard_weight:
        #             new_cost = row.cost
        #         else:
        #             new_cost = formula.hard_weight
        #         new_clause = Clause(
        #                 new_cost,
        #                 [l.negate() for l in row.assignment.to_literals()])
        #         log.info(f"Found new clause {new_clause}")
        #         formula_change.add_cl.append(new_clause)

    if len(formula_change.add_cl) < len(formula_change.remove_cl_indices):
        log.info("Decrease in clauses: "
                 + str(len(formula_change.remove_cl_indices)
                       - len(formula_change.add_cl)))
        # formula.clauses = clauses_after_change
        # log.info(f"Changing hard weight from {formula.hard_weight} to "
        #          f"{formula.hard_weight + hard_weight_change}")
        # formula.hard_weight += hard_weight_change
    else:
        log.info("No improvement, leaving formula unchanged")
        log.info("Increase in clauses would have been: "
                 + str(len(formula_change.add_cl)
                       - len(formula_change.remove_cl_indices)))
        formula_change.add_var.clear()
        formula_change.add_cl.clear()
        formula_change.remove_cl_indices.clear()
        # XXX remove following log entry
        # cores = ""
        # for core in table.unsat_cores():
        #     cores += str(core) + '; '
        # log.info(f"Cores: {cores}")

    return formula_change

def apply_changes(formula, change):
    add_weight = sum(c.weight for c in change.add_cl
                     if c.weight < formula.hard_weight)
    subtract_weight = sum(formula.clauses[i].weight
                          for i in change.remove_cl_indices
                          if formula.clauses[i].weight < formula.hard_weight)
    new_hard_weight = formula.hard_weight + add_weight - subtract_weight

    # Remove and add clauses
    formula.clauses = [c for i, c in enumerate(formula.clauses)
                       if i not in change.remove_cl_indices]
    formula.clauses += change.add_cl

    # Change weights of hard clauses
    updated_clauses = []
    for c in formula.clauses:
        if c.weight >= formula.hard_weight:
            updated_clauses.append(Clause(weight=new_hard_weight,
                                          literals=c.literals))
        else:
            updated_clauses.append(Clause(weight=c.weight,
                                          literals=c.literals))
    formula.clauses = updated_clauses
    formula.hard_weight = new_hard_weight

    formula.num_vars += len(change.add_var)


parser = argparse.ArgumentParser(
        description="TD-based preprocessor for Weighted MaxSAT")
parser.add_argument("file")
parser.add_argument("--log", default="warning")
parser.add_argument("--max-width", type=int)
parser.add_argument("--heuristic", choices=["min-degree", "min-fill"],
                    default="min-degree")
parser.add_argument("--minimize-roots",
                    action="store_true",
                    help="Make sure roots are subsets of the remainder")
parser.add_argument("--simplify-clauses",
                    action="store_true",
                    help="Simplify the clauses added to the formula")
parser.add_argument("--td-time-limit",
                    type=int,
                    help="Abort decomposing after the given number of seconds "
                         "and use TD so far")
parser.add_argument("--dp-time-limit",
                    type=int,
                    help="Abort dynamic programming after the given number of "
                         "seconds and use tables so far")
args = parser.parse_args()

log_level_number = getattr(logging, args.log.upper(), None)
if not isinstance(log_level_number, int):
    raise ValueError(f"Invalid log level: {loglevel}")
logging.basicConfig(level=log_level_number)

if args.heuristic == "min-degree":
    heuristic = Graph.min_degree_vertex
elif args.heuristic == "min-fill":
    heuristic = Graph.min_fill_vertex

with open(args.file) as f:
    formula = Formula(f)
    log.info(f"Formula:\n{formula}")
    g = formula.primal_graph()
    log.info(f"Primal graph:\n{g}")
    log.info("Decomposing")
    decomposer = Decomposer(g, heuristic,
                     max_width=args.max_width,
                     time_limit=args.td_time_limit,
                     normalize=TD.weakly_normalize,
                     minimize_roots=args.minimize_roots)
    tds = decomposer.decompose()
    for td in tds:
        log.debug(f"Partial TD:\n{td}")

    log.info("Solving...")
    formula_change = FormulaChange(add_var=[],
                                   add_cl=[],
                                   remove_cl_indices=set())

    # XXX SIGALRM works only on some platforms
    if args.dp_time_limit:
        signal.signal(signal.SIGALRM, on_timeout)
        signal.alarm(args.dp_time_limit)

    try:
        greatest_var = formula.num_vars
        for td in tds:
            if not td.children:
                continue # maybe not so interesting...?
            # if not td.long_clause_forgotten(formula):
            #     continue # maybe it's useful to only look at TDs that potentially get rid of "long" clauses

            log.info(f"Processing partial TD:\n{td}")
            table = Table(td, formula)
            table.compute()

            # Print table to log
            str_io = io.StringIO()
            str_io.write("Table:\n")
            table.write_recursively(str_io)
            log.info(str_io.getvalue())

            this_change = process_table(table, td, formula, greatest_var, args.simplify_clauses)
            formula_change = FormulaChange(
                add_var=formula_change.add_var + this_change.add_var,
                add_cl=formula_change.add_cl + this_change.add_cl,
                remove_cl_indices=(formula_change.remove_cl_indices
                                | this_change.remove_cl_indices))
            greatest_var += len(this_change.add_var)
    except Exception:
        log.debug("Dynamic programming aborted due to timeout")

    if args.dp_time_limit:
        signal.alarm(0)

    log.info(f"Applying changes to formula...")
    apply_changes(formula, formula_change)

    log.info(f"Formula before removing gaps between variables: {formula}")
    formula.remove_variable_gaps()
    log.info(f"Resulting formula: {formula}")
    formula.rewrite_empty_clauses()
    log.info(f"Formula after rewriting empty clauses: {formula}")
    formula.write_wcnf()
