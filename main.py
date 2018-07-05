#!/usr/bin/env python

import random
from graph import Graph
from decomposer import Decomposer

# The following graph results in TDs of different width for min-fill (3) and min-degree (4)
g = Graph(6)
g.add_edge(1,2)
g.add_edge(1,3)
g.add_edge(1,4)
g.add_edge(2,5)
g.add_edge(2,6)
g.add_edge(3,5)
g.add_edge(3,6)
g.add_edge(4,5)
g.add_edge(4,6)
g.add_edge(5,6)

min_fill_td = Decomposer(g).decompose(Graph.min_fill_vertex)
min_degree_td = Decomposer(g).decompose(Graph.min_degree_vertex)

print(f"Graph:\n{g}")
print()
print(f"Min-fill TD (width {min_fill_td.width()}):\n{min_fill_td}")
print()
print(f"Min-degree TD (width {min_degree_td.width()}):\n{min_degree_td}")

print("Trying to find a TD where min-fill and min-degree produce different widths...")

# Seems unlikely we can find an example with less than 6 vertices
for iteration in range(10000):
    num_vertices = 5
    num_edges = random.randint(0, num_vertices * (num_vertices-1) / 2)
    graph = Graph(num_vertices)
    for (x,y) in random.sample([(x,y) for x in g.vertices for y in g.vertices if x < y], num_edges):
        g.add_edge(x,y)

    min_fill_td = Decomposer(g).decompose(Graph.min_fill_vertex)
    min_degree_td = Decomposer(g).decompose(Graph.min_degree_vertex)

    if min_fill_td.width() != min_degree_td.width():
        print(f"Graph:\n{g}")
        print()
        print(f"Min-fill TD (width {min_fill_td.width()}):\n{min_fill_td}")
        print()
        print(f"Min-degree TD (width {min_degree_td.width()}):\n{min_degree_td}")
        print()
        exit()

print("Giving up.")
