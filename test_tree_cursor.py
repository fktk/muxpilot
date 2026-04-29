from textual.app import App
from textual.widgets import Tree

class CursorTreeApp(App):
    def compose(self):
        yield Tree("Root", id="my-tree")

    def on_mount(self):
        tree = self.query_one("#my-tree", Tree)
        
        tree.clear()
        node1 = tree.root.add("Node 1", expand=True)
        node1.add_leaf("Leaf 1-1")
        leaf12 = node1.add_leaf("Leaf 1-2")
        node2 = tree.root.add("Node 2", expand=True)
        leaf21 = node2.add_leaf("Leaf 2-1")
        leaf22 = node2.add_leaf("Leaf 2-2")
        
        def restore():
            with open("output.txt", "w") as f:
                f.write(f"leaf22.line in timer: {leaf22.line}\n")
                f.write(f"leaf22._line in timer: {leaf22._line}\n")
                tree.move_cursor(leaf22)
                f.write(f"tree.cursor_line after move: {tree.cursor_line}\n")
            self.exit()
            
        self.set_timer(0.1, restore)

if __name__ == "__main__":
    CursorTreeApp().run()
