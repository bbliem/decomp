#!/usr/bin/env python

import argparse
import io
import logging
from signal import signal, SIGPIPE, SIG_DFL
from td import TD

from decomposer import Decomposer
from dp import Table
from formula import Formula, Clause
from graph import Graph

signal(SIGPIPE, SIG_DFL)

log = logging.getLogger(__name__)

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

        bag_union = td.union_of_bags()
        new_clauses = [c for c in formula.clauses
                       if not c.induced_by(bag_union)]
        for row in table:
            if row.cost > 0:
                new_clause = Clause(
                        row.cost,
                        [l.negate() for l in row.assignment.to_literals()])
                log.info(f"Found new clause {new_clause}")
                new_clauses.append(new_clause)

        if len(new_clauses) < len(formula.clauses):
            log.info("Deleting clauses induced by union of all bags and "
                     "adding new clauses")
            formula.clauses = new_clauses
        else:
            log.info("No improvement, ignoring new clauses")

    log.info(f"Formula before removing gaps between variables: {formula}")
    formula.remove_variable_gaps()
    log.info(f"Resulting formula: {formula}")
    formula.write_wcnf()
