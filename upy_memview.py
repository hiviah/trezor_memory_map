#!/usr/bin/env python3

import sys
import json
import math
import pprint

from pygraphviz import AGraph

import xdot
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


# global counter for making keys for nil nodes
node_idx = 0


class GraphWindow(xdot.DotWindow):

    ui = '''
    <ui>
        <toolbar name="ToolBar">
            <toolitem action="Open"/>
            <toolitem action="Reload"/>
            <toolitem action="Print"/>
            <separator/>
            <toolitem action="Back"/>
            <toolitem action="Forward"/>
            <separator/>
            <toolitem action="ZoomIn"/>
            <toolitem action="ZoomOut"/>
            <toolitem action="ZoomFit"/>
            <toolitem action="Zoom100"/>
            <separator/>
            <toolitem name="Find" action="Find"/>
        </toolbar>
    </ui>
    '''

    def __init__(self):
        Gtk.Window.__init__(self)
        # xdot.DotWindow.__init__(self)  # we are stealing and modifying DotWindow init

        window = self

        window.set_title("uPy Memory Viewer")
        window.set_default_size(800, 800)
        self.vbox = Gtk.VBox()
        window.add(self.vbox)

        self.dotwidget = xdot.DotWidget()
        self.dotwidget.connect("error", lambda e, m: self.error_dialog(m))
        self.dotwidget.connect("history", self.on_history)
        self.dotwidget.set_size_request(800, 400)

        # Create a UIManager instance
        uimanager = self.uimanager = Gtk.UIManager()

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = Gtk.ActionGroup('Actions')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions((
            ('Open', Gtk.STOCK_OPEN, None, None, None, self.on_open),
            ('Reload', Gtk.STOCK_REFRESH, None, None, None, self.on_reload),
            ('Print', Gtk.STOCK_PRINT, None, None,
             "Prints the currently visible part of the graph", self.dotwidget.on_print),
            ('ZoomIn', Gtk.STOCK_ZOOM_IN, None, None, None, self.dotwidget.on_zoom_in),
            ('ZoomOut', Gtk.STOCK_ZOOM_OUT, None, None, None, self.dotwidget.on_zoom_out),
            ('ZoomFit', Gtk.STOCK_ZOOM_FIT, None, None, None, self.dotwidget.on_zoom_fit),
            ('Zoom100', Gtk.STOCK_ZOOM_100, None, None, None, self.dotwidget.on_zoom_100),
        ))

        self.back_action = Gtk.Action('Back', None, None, Gtk.STOCK_GO_BACK)
        self.back_action.set_sensitive(False)
        self.back_action.connect("activate", self.dotwidget.on_go_back)
        actiongroup.add_action(self.back_action)

        self.forward_action = Gtk.Action('Forward', None, None, Gtk.STOCK_GO_FORWARD)
        self.forward_action.set_sensitive(False)
        self.forward_action.connect("activate", self.dotwidget.on_go_forward)
        actiongroup.add_action(self.forward_action)

        find_action = xdot.ui.window.FindMenuToolAction("Find", None,
                                         "Find a node by name", None)
        actiongroup.add_action(find_action)

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI descrption
        uimanager.add_ui_from_string(self.ui)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        self.vbox.pack_start(toolbar, False, False, 0)
        # self.vbox.pack_start(self.dotwidget, True, True, 0)
        self.vpaned = Gtk.VPaned()
        self.vpaned.add1(self.dotwidget)
        self.vbox.pack_start(self.vpaned, True, True, 0)


        self.last_open_dir = "."

        self.set_focus(self.dotwidget)

        # Add Find text search
        find_toolitem = uimanager.get_widget('/ToolBar/Find')
        self.textentry = Gtk.Entry(max_length=20)
        self.textentry.set_icon_from_stock(0, Gtk.STOCK_FIND)
        find_toolitem.add(self.textentry)

        self.textentry.set_activates_default(True)
        self.textentry.connect("activate", self.textentry_activate, self.textentry);
        self.textentry.connect("changed", self.textentry_changed, self.textentry);

        self.dotwidget.connect('clicked', self.on_url_clicked)

        sw = Gtk.ScrolledWindow()
        self.object_view = Gtk.TextView()
        self.text_buffer = self.object_view.get_buffer()
        self.vpaned.add2(sw)
        sw.add(self.object_view)
        self.object_view.set_size_request(400, 400)
        # self.object_view.set_default_size(200, 200)
        # sw.set_default_size(200, 200)

        self.show_all()

    def on_url_clicked(self, widget, url, event):
        # dialog = Gtk.MessageDialog(
        #     parent=self,
        #     buttons=Gtk.ButtonsType.OK,
        #     message_format="%s clicked" % obj_map[url])
        # dialog.connect('response', lambda dialog, response: dialog.destroy())
        # dialog.run()
        self.text_buffer.set_text(pprint.pformat(obj_map[url].object))
        return True

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

    @property
    def text_val(self):
        obj = self.object
        if obj.get("shortval"):
            return obj["shortval"]
        # elif obj.get("val"):  # do not use val currently, as it produces very long strings for display
        #     return obj["val"]
        elif obj.get("synthval"):  # synthetic value created by transfer to value from key in dict
            return obj["synthval"]

        return None

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
                    if key_node and key_node.object.get("shortval"):
                        value_node.object["synthval"] = key_node.object["shortval"]
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
        # elif object.get("locals"):
        #     locals_node = get_global_node(object.get("locals"))
        #     child_nodes.add(locals_node)
        # elif object.get("function"):
        #     function_node = get_global_node(object.get("function"))
        #     child_nodes.add(function_node)

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
              ("\\n%s" % node.text_val if node.text_val else ""),
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

window = GraphWindow()
window.connect('destroy', Gtk.main_quit)
window.open_file("tjost.dot")
Gtk.main()
