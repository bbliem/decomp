import copy
from tree import Tree

class Graph(object):
    def __init__(self, num_vertices):
        self.num_vertices = num_vertices
        self.vertices = set(range(1,num_vertices+1))
        self.neighbors = {}
        self.bags_containing = {}
        for v in self.vertices:
            self.neighbors[v] = set()
            self.bags_containing[v] = []
        self.td_roots = []

    def __str__(self):
        pairs = []
        for x in self.vertices:
            for y in self.neighbors[x]:
                if x < y:
                    pairs.append((x,y))
        return f"V = {self.vertices}\nE = {str(pairs)}"

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def add_edge(self, x, y):
        assert x in self.vertices
        assert y in self.vertices
        assert x != y
        self.neighbors[x].add(y)
        self.neighbors[y].add(x)

    def remove_vertex(self, v):
        self.vertices.remove(v)
        for x in self.neighbors[v]:
            self.neighbors[x].remove(v)
        del self.neighbors[v]
        #del self.bags_containing[v]
        self.num_vertices -= 1

    def neighborhood(self, vertex):
        return {vertex} | self.neighbors[vertex]

    def eliminate(self, vertex):
        new_bag = self.neighborhood(vertex)
        new_subtree = Tree(new_bag)

        # Eliminate vertex and connect neighbors
        for (x,y) in [(x,y) for x in self.neighbors[vertex] for y in self.neighbors[vertex] if x < y]:
            self.add_edge(x,y)
        self.remove_vertex(vertex)

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

    # Connect the parentless nodes in an arbitrary way and return a TD
    def connect_roots(self):
        assert self.td_roots, "No bags have been created"
        for x,y in zip(self.td_roots, self.td_roots[1:]):
            x.add_child(y)
        return self.td_roots[0]

    def min_degree_vertex(self, max_width=None):
        result = None
        min_degree = self.num_vertices
        for v in self.vertices:
            if not max_width or len(self.neighborhood(v)) - 1 <= max_width:
                if len(self.neighbors[v]) < min_degree:
                    min_degree = len(self.neighbors[v])
                    result = v
        return result

    def num_unconnected_neighbor_pairs(self, v):
        result = 0
        for (x,y) in [(x,y) for x in self.neighbors[v] for y in self.neighbors[v] if x < y]:
            if y not in self.neighbors[x]:
                result += 1
        return result

    # Returns a vertex with minimum fill-in value such that a bag with width at most max_width results; if there is no such vertex, returns None
    def min_fill_vertex(self, max_width=None):
        result = None
        min_fill = self.num_vertices * self.num_vertices
        for v in self.vertices:
            if not max_width or len(self.neighborhood(v)) - 1 <= max_width:
                fill = self.num_unconnected_neighbor_pairs(v)
                if fill < min_fill:
                    min_fill = fill
                    result = v
        return result

    # Returns the decomposition using the specified method (function returning next vertex to eliminate), without changing this object.
    def decomposition(self, method, max_width=None):
        g = copy.deepcopy(self)
        #while g.num_vertices > 0:
        while True:
            # Determine vertex to eliminate, as long as we get a bag of width at most max_width
            v = method(g, max_width)
            if v:
                g.eliminate(v)
            else:
                break

        # Put all the remaining vertices into a single bag
        if g.vertices:
            g.add_parent_to_roots(g.vertices)

        td = g.connect_roots()
        # print(f"TD:\n{td}")
        td.remove_subset_children()
        # print(f"Removing subset children:\n{td}")
        td = td.move_superset_children()
        # print(f"Moving superset children:\n{td}")
        #td = td.canonize_root()
        #td.sort()
        return td
