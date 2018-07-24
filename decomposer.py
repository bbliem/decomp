#!/usr/bin/env python

import copy
import random
from signal import signal, SIGPIPE, SIG_DFL

from graph import Graph
from td import TD

class Decomposer(object):
    """The method is a function returning the next vertex to eliminate. If
    max_width is given, only produce bags of at most the given width and then
    put all remaining vertices into a big bag at the root."""
    def __init__(self, graph, method, **kwargs):
        self.graph = copy.deepcopy(graph)
        self.method = method
        self.max_width = kwargs.get("max_width")
        self.normalize = kwargs.get("normalize")
        self.minimize_roots = kwargs.get("minimize_roots")
        if self.normalize is None:
            self.normalize = lambda td: None

        self.bags_containing = {}
        for v in self.graph.vertices:
            self.bags_containing[v] = []
        self.td_roots = []

    def eliminate(self, vertex):
        new_bag = frozenset(self.graph.neighborhood(vertex))
        new_subtree = TD(new_bag)

        # Eliminate vertex and connect neighbors
        for (x,y) in [(x,y) for x in self.graph.neighbors[vertex]
                            for y in self.graph.neighbors[vertex]
                            if x < y]:
            self.graph.add_edge(x,y)
        self.graph.remove_vertex(vertex)

        # Add children to this new subtree
        for subtree in self.bags_containing[vertex]:
            if not subtree.parent:
                new_subtree.add_child(subtree)
                self.td_roots.remove(subtree)

        # The new subtree has no parent yet
        self.td_roots.append(new_subtree)

        # For each bag element, remember it's contained in this new node
        for x in new_bag:
            self.bags_containing[x].append(new_subtree)

    def add_parent_to_roots(self, bag):
        new_root = TD(bag)
        for node in self.td_roots:
            new_root.add_child(node)
        self.td_roots = [new_root]

    def connect_roots(self, remainder=set()):
        """Connect parentless nodes that are disjoint from 'remainder'."""
        connect, ignore = [], []
        for td in self.td_roots:
            if td.node.isdisjoint(remainder):
                connect.append(td)
            else:
                ignore.append(td)
        if not connect:
            return
        for x, y in zip(connect, connect[1:]):
            x.add_child(y)
        self.td_roots = [connect[0]] + ignore

    def do_eliminations(self):
        """Eliminate vertices as long as possible within bag size limit."""
        while True:
            # Determine vertex to eliminate, as long as we get a bag of width
            # at most max_width
            v = self.method(self.graph, self.max_width)
            if v:
                self.eliminate(v)
            else:
                break

    def decompose(self):
        """Return a list of partial decompositions using parameters given in
        the constructor."""
        self.do_eliminations()

        for td in self.td_roots:
            td.remove_subset_children()
        self.td_roots = [td.move_superset_children() for td in self.td_roots]
        self.connect_roots(self.graph.vertices)
        for i, td in enumerate(self.td_roots):
            self.normalize(td)
            if self.minimize_roots:
                intersection_with_remainder = td.node & self.remainder()
                if len(intersection_with_remainder) < len(td.node):
                    new_root = TD(intersection_with_remainder)
                    new_root.add_child(td)
                    self.td_roots[i] = new_root

        # TD.canonize_root()?
        # TD.sort()?
        return self.td_roots

    def remainder(self):
        """Return the remaining part that has not been decomposed."""
        return self.graph.vertices


if __name__ == "__main__":
    signal(SIGPIPE, SIG_DFL)

    # The following graph results in TDs of different width for min-fill (3)
    # and min-degree (4)
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

    min_fill_td = Decomposer(g, Graph.min_fill_vertex).decompose()[0]
    min_degree_td = Decomposer(g, Graph.min_degree_vertex).decompose()[0]

    print(f"Graph:\n{g}")
    print()
    print(f"Min-fill TD (width {min_fill_td.width()}):\n{min_fill_td}")
    print()
    print(f"Min-degree TD (width {min_degree_td.width()}):\n{min_degree_td}")
    print()

    print("Trying to find a TD where min-fill and min-degree produce different"
          "widths...")

    # Seems unlikely we can find an example with less than 6 vertices
    for iteration in range(10000):
        num_vertices = 5
        num_edges = random.randint(0, num_vertices * (num_vertices-1) / 2)
        g = Graph(num_vertices)
        for (x,y) in random.sample([(x,y) for x in g.vertices
                                          for y in g.vertices
                                          if x < y], num_edges):
            g.add_edge(x,y)

        min_fill_td = Decomposer(g, Graph.min_degree_vertex).decompose()[0]
        min_degree_td = Decomposer(g, Graph.min_degree_vertex).decompose()[0]

        if min_fill_td.width() != min_degree_td.width():
            print()
            print(f"Graph:\n{g}")
            print()
            print(f"Min-fill TD (width {min_fill_td.width()}):\n{min_fill_td}")
            print()
            print(f"Min-degree TD (width {min_degree_td.width()}):\n"
                  f"{min_degree_td}")
            exit()

    print("Giving up.")
