class TD(object):
    """A tree decomposition.

    The attributes represent a node of the decomposition, and the child nodes
    are stored in self.children."""

    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []

    def to_str(self, depth=0):
        s = depth * "  " + ','.join([str(i) for i in self.node])
        for child in self.children:
            s += '\n' + child.to_str(depth + 1)
        return s

    def __str__(self):
        return self.to_str()

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.node == other.node
                    and self.children == other.children)
        return NotImplemented

    def introduced(self):
        if self.children:
            child_elements = type(self.node).union(
                    *(c.node for c in self.children))
            return self.node - child_elements
        else:
            return self.node

    def shared(self):
        """Return a list of lists of shared elements.

        The result is a list containing, for each child, a list, which contains
        elements that are present in both this TD node and the child."""
        return [[x for x in self.node if x in c.node] for c in self.children]

    def width(self):
        """Return the size of the largest bag minus one."""
        widths = [child.width() for child in self.children]
        widths.append(len(self.node) - 1)
        return max(widths)

    def union_of_bags(self):
        """Return the union of all bags in the TD."""
        return frozenset.union(self.node,
                               *(c.union_of_bags() for c in self.children))

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def remove_subset_children(self):
        """Recursively remove all children that are subsets."""
        new_children = []
        for child in self.children:
            if child.node.issubset(self.node):
                # print(f"Child {child.node} is subset of {self.node}")
                # Remove child and adopt its children
                for grandchild in child.children:
                    self.add_child(grandchild)
                child.children.clear()
            else:
                new_children.append(child)
                child.remove_subset_children()
        self.children = new_children

    def move_superset_children(self):
        """Recursively remove nodes having a child that is a superset.

        Returns the new root."""

        # If a child is a superset, move it up
        superset_children = (c for c in self.children
                               if c.node.issuperset(self.node))
        for child in superset_children:
            # Transfer all other children of self to that child
            other_children = (c for c in self.children if c is not child)
            for other_child in other_children:
                child.add_child(other_child)
            self.children.clear()
            self.parent = None
            child.parent = None

            # self should now become child -- and we continue with removing
            # further down
            return child.move_superset_children()

        # Recurse
        new_children = []
        for child in self.children:
            new_children.append(child.move_superset_children())
        self.children.clear()
        for child in new_children:
            self.add_child(child)
        return self

    def canonical_root(self):
        """Return the node with the lexicographically smallest bag."""
        smallest = self
        for child in self.children:
            x = child.canonical_root()
            if list(x.node) < list(smallest.node):
                smallest = x
        return smallest

    def become_root(self):
        """Flip a subtree around so that this node becomes the root."""
        if self.parent:
            self.parent.become_root()
            self.parent.children.remove(self)
            self.add_child(self.parent)
            self.parent = None

    def canonize_root(self):
        """Make the node having the lexicographically smallest bag the root.

        Returns the new root."""
        new_root = self.canonical_root()
        new_root.become_root()
        return new_root

    def sort(self):
        """Recursively sort children lexicographically."""
        self.children = sorted(self.children, key=lambda c: list(c.node))
        for child in self.children:
            child.sort()

    def weakly_normalize(self):
        """Make this TD weakly normalized.

        That is, add nodes so that the following holds: If a node has more than
        one child, then its bag and the bags of all children are the same."""
        for child in self.children:
            child.weakly_normalize()

        if len(self.children) >= 2:
            # Add join node (as a child of this node) and its children (which
            # will be the new parents or this node's children).
            children = self.children.copy()
            self.children.clear()
            child_elements = type(self.node).union(*(c.node for c in children))
            join_elements = child_elements & self.node

            # Join node:
            if join_elements != self.node:
                join_node = TD(join_elements)
                self.add_child(join_node)
            else:
                join_node = self

            # Join node's children:
            for c in children:
                if c.node == join_elements:
                    join_node.add_child(c)
                else:
                    new_child = TD(join_elements)
                    new_child.add_child(c)
                    join_node.add_child(new_child)
