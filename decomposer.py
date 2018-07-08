import copy
from tree import Tree

class Decomposer(object):
    def __init__(self, graph):
        self.graph = copy.deepcopy(graph)
        self.bags_containing = {}
        for v in self.graph.vertices:
            self.bags_containing[v] = []
        self.td_roots = []

    def eliminate(self, vertex):
        new_bag = frozenset(self.graph.neighborhood(vertex))
        new_subtree = Tree(new_bag)

        # Eliminate vertex and connect neighbors
        for (x,y) in [(x,y) for x in self.graph.neighbors[vertex] for y in self.graph.neighbors[vertex] if x < y]:
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
        new_root = Tree(bag)
        for node in self.td_roots:
            new_root.add_child(node)
        self.td_roots = [new_root]

    # Connect the parentless nodes in an arbitrary way
    def connect_roots(self):
        assert self.td_roots, "No bags have been created"
        for x,y in zip(self.td_roots, self.td_roots[1:]):
            x.add_child(y)
        self.td_roots = [self.td_roots[0]]

    # Returns the decomposition using the specified method (function returning
    # next vertex to eliminate). If max_width is given, only produce bags of at
    # most the given width and then put all remaining vertices into a big bag
    # at the root.
    def decompose(self, method, max_width=None):
        while True:
            # Determine vertex to eliminate, as long as we get a bag of width at most max_width
            v = method(self.graph, max_width)
            if v:
                self.eliminate(v)
            else:
                break

        # Put all the remaining vertices into a single bag
        if self.graph.vertices:
            self.add_parent_to_roots(self.graph.vertices)

        map(Tree.remove_subset_children, self.td_roots)
        self.td_roots = [td.move_superset_children() for td in self.td_roots]
        self.connect_roots()
        # Tree.canonize_root()?
        # Tree.sort()?
        return self.td_roots[0]
