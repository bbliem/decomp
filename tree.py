class Tree(object):
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []

    def to_str(self, indent = ""):
        s = indent + str(self.node) + '\n'
        indent += "  "
        for child in self.children:
            s += child.to_str(indent)
        return s

    def __str__(self):
        return self.to_str()

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.node == other.node) and (self.children == other.children)
        return NotImplemented

    # Size of largest bag minus one
    def width(self):
        widths = [child.width() for child in self.children]
        widths.append(len(self.node) - 1)
        return max(widths)

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    # Recursively remove all children that are subsets
    def remove_subset_children(self):
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

    # Returns new root
    def move_superset_children(self):
        # If a child is a superset, move it up
        for child in self.children:
            if child.node.issuperset(self.node):
                # print(f"Child {child.node} is superset of {self.node}")
                # Transfer all other children of self to that child
                for other_child in self.children:
                    if other_child is not child:
                        # print(f"Moving child {other_child.node} to new parent {child.node}")
                        child.add_child(other_child)
                self.children.clear()
                self.parent = None
                child.parent = None

                # self should now become child -- and we continue with removing further down
                return child.move_superset_children()

        # Recurse
        new_children = []
        for child in self.children:
            new_children.append(child.move_superset_children())
        #self.children = new_children
        self.children.clear()
        #map(self.add_child, new_children)
        for child in new_children:
            self.add_child(child)
        return self

    # Returns node with the lexicographically smallest bag
    def canonical_root(self):
        smallest = self
        for child in self.children:
            x = child.canonical_root()
            if list(x.node) < list(smallest.node):
                smallest = x
        return smallest

    # Flip a subtree around so that this node becomes the root
    def become_root(self):
        if self.parent:
            self.parent.become_root()
            self.parent.children.remove(self)
            self.add_child(self.parent)
            self.parent = None

    # Returns new root, which is the node having the lexicographically smallest bag
    def canonize_root(self):
        new_root = self.canonical_root()
        new_root.become_root()
        return new_root

    # Recursively sorts children lexicographically
    def sort(self):
        self.children = sorted(self.children, key=lambda child: list(child.node))
        for child in self.children:
            child.sort()
