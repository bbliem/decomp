class Graph(object):
    def __init__(self, num_vertices):
        self.num_vertices = num_vertices
        self.vertices = set(range(1,num_vertices+1))
        self.neighbors = {}
        for v in self.vertices:
            self.neighbors[v] = []

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
        if y not in self.neighbors[x]:
            assert x not in self.neighbors[y]
            self.neighbors[x].append(y)
            self.neighbors[y].append(x)
        else:
            assert x in self.neighbors[y]

    def remove_vertex(self, v):
        self.vertices.remove(v)
        for x in self.neighbors[v]:
            self.neighbors[x].remove(v)
        del self.neighbors[v]
        self.num_vertices -= 1

    def neighborhood(self, vertex):
        return [vertex] + self.neighbors[vertex]

    def min_degree_vertex(self, max_width=None):
        result = None
        min_degree = self.num_vertices
        for v in self.vertices:
            #if not max_width or len(self.neighborhood(v)) - 1 <= max_width:
            # Better performance:
            if not max_width or len(self.neighbors[v]) <= max_width:
                if len(self.neighbors[v]) < min_degree:
                    min_degree = len(self.neighbors[v])
                    result = v
        return result

    def num_unconnected_neighbor_pairs(self, v):
        result = 0
        for (x,y) in [(x,y) for x in self.neighbors[v]
                            for y in self.neighbors[v]
                            if x < y]:
            if y not in self.neighbors[x]:
                result += 1
        return result

    def min_fill_vertex(self, max_width=None):
        """Return a min-fill vertex that produces a bag of given maximum size.
        
        The result is a vertex of minimum fill-in value whose elimination would
        result in a bag with at most max_width elements, if there is such a
        vertex. Otherwise, return None.
        """
        result = None
        min_fill = self.num_vertices * self.num_vertices
        for v in self.vertices:
            #if not max_width or len(self.neighborhood(v)) - 1 <= max_width:
            # Better performance:
            if not max_width or len(self.neighbors[v]) <= max_width:
                fill = self.num_unconnected_neighbor_pairs(v)
                if fill < min_fill:
                    min_fill = fill
                    result = v
        return result
