from collections import defaultdict

# This class represents a directed graph using
# adjacency list representation
class Graph:

    # Constructor
    def __init__(self):

        # Default dictionary to store graph
        self.edges = defaultdict(list)
        self.nodes = set()
        self.all_paths = []

    # Function to add an edge to graph
    def add_edge(self, u, v):
        self.edges[u].append(v)


    def add_node(self, u):
        self.nodes.add(u)


    # A function used by DFS
    def DFSUtil(self, v, visited):

        # Mark the current node as visited
        # and print it
        visited.add(v)
        print(v, end=' ')

        # Recur for all the vertices
        # adjacent to this vertex
        for neighbour in self.edges[v]:
            if neighbour not in visited:
                self.DFSUtil(neighbour, visited)


    # The function to do DFS traversal. 
    # It uses recursive DFSUtil()
    def DFS(self, v):

        # Create a set to store visited vertices
        visited = set()

        # Call the recursive helper function
        # to print DFS traversal
        self.DFSUtil(v, visited)


    # Function to find all paths starting from a given node
    def find_all_paths(self, start_node, max_paths=10, max_legs=5):
        def dfs(current_node, path, visited):
            # Add the current node to the path
            path.append(current_node)
            visited.add(current_node)

            next_legs[current_node] += 1

            # Recur for all neighbors
            for neighbor in self.edges[current_node]:
                # if neighbor not in visited and len(node_paths) < max_paths:
                if neighbor not in visited and len(node_paths) < max_paths \
                            and next_legs[neighbor] < max_legs:
                    yield from dfs(neighbor, path, visited)
                    # dfs(neighbor, path, visited)
                    # yield from g is equivalent to for v in g: yield v

            # Backtrack, store the current path
            self.all_paths.append(list(path))
            node_paths.append(list(path))
            path.pop()
            visited.remove(current_node)

        # Start DFS from the given node
        visited = set()
        node_paths = []
        path = []
        next_legs = defaultdict(int)
        yield from dfs(start_node, path, visited)
        # dfs(start_node, path, visited)


    # Function to find all valid paths starting from nodes in pre_bus
    def find_paths_from_buses(self, pre_bus, max_bus_paths=10, max_bus_legs=5):
        all_paths = []
        for bus in pre_bus:
            all_paths.extend(self.find_all_paths(bus, max_paths=max_bus_paths, max_legs=max_bus_legs))
            # yield from self.find_all_paths(bus)
        return self.all_paths
        # return all_paths
