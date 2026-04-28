from textual.app import App
from textual.widgets import Tree

class UpdateTreeApp(App):
    def compose(self):
        yield Tree("Root", id="my-tree")

    def on_mount(self):
        tree = self.query_one("#my-tree", Tree)
        node1 = tree.root.add("Node 1")
        
        with open("output.txt", "w") as f:
            try:
                node1.set_label("Node 1 Updated")
                f.write("set_label worked!\n")
            except Exception as e:
                f.write(f"set_label failed: {e}\n")
                
            try:
                node1.label = "Node 1 Updated Prop"
                f.write("label property worked!\n")
            except Exception as e:
                f.write(f"label prop failed: {e}\n")
            
        self.exit()

if __name__ == "__main__":
    UpdateTreeApp().run()
