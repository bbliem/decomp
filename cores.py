#!/usr/bin/env python

import argparse
from signal import signal, SIGPIPE, SIG_DFL

from decomposer import Decomposer
from dp import Table
from formula import Formula
from graph import Graph

signal(SIGPIPE, SIG_DFL)

parser = argparse.ArgumentParser(
        description="Dynamic programming on a TD of a MaxSAT instance")
parser.add_argument("file")
args = parser.parse_args()

with open(args.file) as f:
    print("Parsing...")
    formula = Formula(f)
    print(formula)
    print("Constructing primal graph...")
    g = formula.primal_graph()
    print(g)
    #td = Decomposer(g, Graph.min_degree_vertex, max_width=8).decompose()
    print("Decomposing...")
    tds = Decomposer(g, Graph.min_degree_vertex,
                     max_width=5).decompose_partially()
    #td.weakly_normalize()
    for td in tds:
        print(td)
        print()
        td.weakly_normalize()

    print("Solving...")
    for td in tds:
        if not td.children:
            continue # maybe not so interesting...?
        print(td)
        table = Table(td, formula)
        table.compute()
        print()
        table.write_recursively()
        if table.unsat():
            print("Unsat.")
            print("Some cores:")
            for core in table.unsat_cores():
                print(core)
        print()
