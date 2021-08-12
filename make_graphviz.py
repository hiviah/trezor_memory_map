#!/usr/bin/env python3

import sys
import json

class Node:

    def __init__(self, object):
        self.object = object
        self.children = set()

    def __str__(self):
        return "Node(%s, %d children)" % (self.object["ptr"], len(self.children))

    def __eq__(self, other):
        if self.object["ptr"] == "(nil)":
            return False # nil addr object we declare by definition never match
        return self.object["ptr"] == other.object["ptr"]

    def __hash__(self):
        # children can have nil address, but we don't want to clump them together in one hash bin
        if self.object["ptr"] == "(nil)":
            return hash(str(self.object))  # this is fucking stupid, but we don't have frozendict
        else:
            return hash(self.object["ptr"])


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
        node = obj_map[addr]  # do not create again, lookup existing
        children = object.get("children")  # need to do recursively?
        if children:
            pass
        elif object.get("items"):
            children = object.get("items")
            for child in children:
                if isinstance(child, dict):
                    if child["ptr"] == "(nil)":
                        node.children.add(Node(child))
                    else:
                        try:
                            node.children.add(obj_map[child["ptr"]])
                        except KeyError:
                            if child["type"] != "romdata":  # romdata not in garbage collector
                                print("Missing address", child["ptr"])
                elif isinstance(child, str):
                    node.children.add(Node({"ptr": child}))  # jesus fuck


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

print("Done")
