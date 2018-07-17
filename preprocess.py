#!/usr/bin/env python

import argparse
import io
import logging
from signal import signal, SIGPIPE, SIG_DFL
from td import TD

from collections import namedtuple
from decomposer import Decomposer
from dp import Table
from formula import Formula, Clause
from graph import Graph

signal(SIGPIPE, SIG_DFL)

log = logging.getLogger(__name__)

FormulaChange = namedtuple("FormulaChange", "add remove_indices")
# Contains a list of clauses to add as well as a set of *indices* of clauses to
# remove

def process_table(table, td, formula):
    bag_union = td.union_of_bags()
    formula_change = FormulaChange(add=[], remove_indices=set())

    log.info(f"Processing table with hard weight {table.hard_weight}")
    for i, c in enumerate(formula.clauses):
        if c.induced_by(bag_union):
            # Remove clause
            formula_change.remove_indices.add(i)
            log.info(f"Found clause to be deleted {c}")

    for row in table:
        if row.cost > 0:
            if row.cost < table.hard_weight:
                new_cost = row.cost
            else:
                new_cost = formula.hard_weight
            new_clause = Clause(
                    new_cost,
                    [l.negate() for l in row.assignment.to_literals()])
            log.info(f"Found new clause {new_clause}")
            formula_change.add.append(new_clause)

    if len(formula_change.add) < len(formula_change.remove_indices):
        log.info("Decrease in clauses: "
                 + str(len(formula_change.remove_indices)
                       - len(formula_change.add)))
        # formula.clauses = clauses_after_change
        # log.info(f"Changing hard weight from {formula.hard_weight} to "
        #          f"{formula.hard_weight + hard_weight_change}")
        # formula.hard_weight += hard_weight_change
    else:
        log.info("No improvement, leaving formula unchanged")
        log.info("Increase in clauses would have been: "
                 + str(len(formula_change.add)
                       - len(formula_change.remove_indices)))
        formula_change.add.clear()
        formula_change.remove_indices.clear()
        # XXX remove following log entry
        cores = ""
        for core in table.unsat_cores():
            cores += str(core) + '; '
        log.info(f"Cores: {cores}")

    return formula_change

def apply_changes(formula, change):
    add_weight = sum(c.weight for c in change.add
                     if c.weight < formula.hard_weight)
    subtract_weight = sum(formula.clauses[i].weight
                          for i in change.remove_indices
                          if formula.clauses[i].weight < formula.hard_weight)
    new_hard_weight = formula.hard_weight + add_weight - subtract_weight

    # Remove and add clauses
    formula.clauses = [c for i, c in enumerate(formula.clauses)
                       if i not in change.remove_indices]
    formula.clauses += change.add

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


parser = argparse.ArgumentParser(
        description="TD-based preprocessor for Weighted MaxSAT")
parser.add_argument("file")
parser.add_argument("--log", default="warning")
parser.add_argument("--max-width", type=int)
parser.add_argument("--heuristic", choices=["min-degree", "min-fill"],
                    default="min-degree")
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
    tds = Decomposer(g, heuristic,
                     max_width=args.max_width,
                     normalize=TD.weakly_normalize).decompose()
    for td in tds:
        log.debug(f"Partial TD:\n{td}")

    log.info("Solving...")
    formula_change = FormulaChange(add=[], remove_indices=set())
    for td in tds:
        if not td.children:
            continue # maybe not so interesting...?
        log.info(f"Processing partial TD:\n{td}")
        table = Table(td, formula)
        table.compute()

        # Print table to log
        str_io = io.StringIO()
        str_io.write("Table:\n")
        table.write_recursively(str_io)
        log.info(str_io.getvalue())

        this_change = process_table(table, td, formula)
        formula_change = FormulaChange(
            add=formula_change.add + this_change.add,
            remove_indices=(formula_change.remove_indices
                            | this_change.remove_indices))

    log.info(f"Applying changes to formula...")
    apply_changes(formula, formula_change)

    log.info(f"Formula before removing gaps between variables: {formula}")
    formula.remove_variable_gaps()
    log.info(f"Resulting formula: {formula}")
    formula.write_wcnf()
