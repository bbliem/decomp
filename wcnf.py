#!/usr/bin/env python
import argparse
import sys
import warnings

from graph import Graph
from decomposer import Decomposer

parser = argparse.ArgumentParser(description = "Convert a WCNF formula to a graph")
parser.add_argument('file')
args = parser.parse_args()

def read_file():
    with open(args.file) as f:
        clauses_read = 0
        num_clauses = None

        for line in f:
            fields = line.split()
            if not fields or fields[0] == 'c':
                # empty or comment line
                pass

            elif fields[0] == 'p':
                # parameters line
                assert len(fields) == 5 and fields[1] == "wcnf", "Unexpected file format"
                num_vars = int(fields[2])
                num_clauses = int(fields[3])
                hard_weight = int(fields[3])
                graph = Graph(num_vars)

            else:
                # clause
                assert graph
                assert fields[-1] == '0'
                clause = list({ abs(int(x)) for x in fields[0:-1] })
                assert all([1 <= i <= num_vars for i in clause]), "Invalid variable number"
                # make clique
                for (x,y) in [(x,y) for x in clause for y in clause if x < y]:
                    graph.add_edge(x,y)
                clauses_read += 1

        if num_clauses != clauses_read:
            warnings.warn("Read {} clauses, but {} were declared".format(clauses_read, num_clauses))

        return graph

graph = read_file()
#graph.write()
d = Decomposer(graph)
d.decompose(Graph.min_degree_vertex, 5)
