#!/usr/bin/env python3

import sys
import json

from pygraphviz import AGraph

class Node:

    def __init__(self, object):
        self.object = object
        self.children = set()

    def __str__(self):
        return "Node(%s, %d children)" % (self.object["ptr"], len(self.children))

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
            return str(self.object)
        else:
            return self.address


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
        return Node({"ptr": child})  # jesus fuck

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
                    value_node = get_global_node(child["key"])
                    if value_node is not None:
                        child_nodes.add(value_node)
        elif object.get("items"):
            children = object.get("items")
            for child in children:
                item_node = get_global_node(child)
                if item_node is not None:
                    child_nodes.add(item_node)

        node.children.update(child_nodes)


for obj in j:
    if not isinstance(obj, dict):
        continue
    owner = obj.get("owner")
    if owner is not None:
        owner_node = obj_map[owner]
        owner_node.children.add(owner_node)

for addr, node in obj_map.items():
    children_count = len(node.children)
    if children_count >= 1:
        print(children_count, addr, node)

dot_graph = AGraph(directed=True)

some_nodes = [node for node in obj_map.values() if len(node.children) > 5]
some_nodes = some_nodes[:20]
for idx, node in enumerate(some_nodes):
    dot_graph.add_node(node.graph_id)
    for child in node.children:
        dot_graph.add_node(child.graph_id)

for idx, node in enumerate(some_nodes):
    for child in node.children:
        dot_graph.add_edge(node.graph_id, child.graph_id)

dot_graph.write("tjost.dot")
#dot_graph.draw("tjost.png", prog="circo")

print("Done")
