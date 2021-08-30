#!/usr/bin/env python3

import sys
import json
import math

from pygraphviz import AGraph

# global counter for making keys for nil nodes
node_idx = 0


class Node:

    def __init__(self, object):
        self.object = object
        self.children = set()
        self.synthetic_id = None  # made up identifier for nil nodes

    def __str__(self):
        return "Node(%s, type %s, %d children)" % (self.object["ptr"], self.object["type"], len(self.children))

    def __eq__(self, other):
        if self.is_nil():
            return False # nil addr object we declare by definition never match
        return self.object["ptr"] == other.object["ptr"]

    def __hash__(self):
        # children can have nil address, but we don't want to clump them together in one hash bin
        if self.is_nil():
            return hash(str(self.object))  # this is fucking stupid, but we don't have frozendict
        else:
            return hash(self.object["ptr"])

    @property
    def address(self):
        return self.object["ptr"]

    def is_nil(self):
        return self.object["ptr"] == "(nil)"

    @property
    def graph_id(self):
        if self.is_nil():
            if self.synthetic_id is None:
                self.synthetic_id = "%s-%d" % (self.object["type"], self.get_new_node_num())
            return self.synthetic_id
        else:
            return self.address

    @staticmethod
    def get_new_node_num():
        global node_idx
        node_idx += 1
        return node_idx



def get_global_node(child):
    """Return a node object existing or new for a child object"""
    if isinstance(child, dict):
        if child["ptr"] == "(nil)":
            return Node(child)
        else:
            try:
                return obj_map[child["ptr"]]
            except KeyError:
                if child["type"] != "romdata":  # romdata not in garbage collector
                    print("Missing address", child["ptr"])
    elif isinstance(child, str):
        # indirect by address - seen in dict values
        try:
            return obj_map[child]  # let's hope addr is in the global map
        except KeyError:
            print("Unmapped node - ", child)
            return Node({
                "ptr": child,
                "type": "unmapped"
            })

    return None


with open(sys.argv[1]) as f:
    j = json.load(f)

obj_map = {}

# see dict_main for dict items, mp_sys_path_obj for list items
for obj in j:
    if not isinstance(obj, dict):
        print("skipping:", obj)
        continue
    addr = obj.get("ptr", "(nil)")
    if addr != "(nil)":
        node = Node(obj)
        obj_map[addr] = node

for object in j:
    if not isinstance(object, dict):
        print("skipping:", object)
        continue
    addr = object.get("ptr", "(nil)")
    if addr != "(nil)":
        node = obj_map.get(addr)  # do not create again, lookup existing
        children = object.get("children")  # need to do recursively?
        child_nodes = set()
        if children:
            for child in children:
                key_node = get_global_node(child["key"])
                if key_node is not None:
                    child_nodes.add(key_node)
                value_node = get_global_node(child["value"])
                if value_node is not None:
                    child_nodes.add(value_node)
        elif object.get("items"):
            children = object.get("items")
            for child in children:
                item_node = get_global_node(child)
                if item_node is not None:
                    child_nodes.add(item_node)
        elif object.get("globals"):
            globals_node = get_global_node(object.get("globals"))
            child_nodes.add(globals_node)
        elif object.get("locals"):
            locals_node = get_global_node(object.get("locals"))
            child_nodes.add(locals_node)
        elif object.get("function"):
            function_node = get_global_node(object.get("function"))
            child_nodes.add(function_node)

        # missing:
        # closed list from closures
        # parents - not found (in romdata?)


        node.children.update(child_nodes)


for obj in j:
    if not isinstance(obj, dict):
        continue
    owner = obj.get("owner")
    if owner is not None:
        owner_node = obj_map[owner]
        if obj.get("ptr") != "(nil)":
            this_child_node = obj_map[obj["ptr"]]
            owner_node.children.add(this_child_node)
        else:
            print("Nil node with owner:", obj)

for addr, node in obj_map.items():
    children_count = len(node.children)
    if children_count >= 1:
        print(children_count, addr, node)

dot_graph = AGraph(directed=True)
dot_graph.node_attr.update(shape="rectangle", style="filled")

some_nodes = [node for node in obj_map.values() if len(node.children) >= 0] #and node.object["type"] != "function"]
# some_nodes = some_nodes[:20]

for idx, node in enumerate(some_nodes):
    dot_graph.add_node(node.graph_id,
        URL=node.graph_id,
        label=node.object["type"]+" "+node.object["ptr"] + "\\n" + "%d chld" % len(node.children) +
            "\\n%d alloc" % node.object["alloc"] +
              ("\\n%s" % node.object["shortval"] if node.object["shortval"] else ""),
        fillcolor="%.3f 0.19 %.3f" % (max(0.529-math.log2(node.object["alloc"]+1)/20.0, 0),
            1-min(len(node.children)/50.0, 0.5))
       )
    for child in (child for child in node.children if (not child.is_nil() or len(child.children) > 0)): #node.children:
        dot_graph.add_node(child.graph_id)

for idx, node in enumerate(some_nodes):
    for child in (child for child in node.children if not child.is_nil()): #node.children:
        dot_graph.add_edge(node.graph_id, child.graph_id)

dot_graph.write("tjost.dot")
#dot_graph.draw("tjost.png", prog="fdp")

nodes = list(obj_map.values())
nodes.sort(key=lambda n:n.object["alloc"])
for n in nodes:
    print(n.object["alloc"], n)

print("Done, number of nodes: %d, number of edges: %d" % (dot_graph.number_of_nodes(), dot_graph.number_of_edges()))
