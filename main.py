import os
import shutil
import threading

import pyperclip
from pyperclip import paste

from pathlib import Path
from typing import Iterable
from os.path import abspath, basename, dirname
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from textual.binding import Binding
from textual.geometry import Offset
from textual.reactive import reactive
from textual.app import App, ComposeResult
from textual.selection import Selection
from textual.types import DirEntry
from textual.widgets import DirectoryTree, Footer, Input, Label, Log, TextArea, Tree
from textual.events import Key

class FilteredDirectoryTree(DirectoryTree):
	show_hidden = reactive(True)
	guide_depth = 1

	def __init__(self, *args, parent=None, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.selected_file = None
		self.parent_widget = parent
		self.pretty_path = basename(abspath(self.path))

	def compose(self) -> ComposeResult:
		self.label = Label(basename(abspath(self.path)))
		self.label.renderable = self.pretty_path
		yield from super().compose()
		yield self.label

	def _on_tree_node_selected(self, event: Tree.NodeSelected[DirEntry]) -> None:
		if event.node.data:
			self.selected_file = event.node.data.path
			if os.path.isdir(self.selected_file):
				return super()._on_tree_node_selected(event)
			self.parent_widget.current_file = self.selected_file # type: ignore
			self.parent_widget.select_file() # type: ignore
		return super()._on_tree_node_selected(event)

	def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
		if self.show_hidden:
			return paths
		return [path for path in paths if not path.name.startswith(".")]

	def watch_show_hidden(self, value: bool) -> None:
		# Rebuild tree when visibility changes
		self.path = self.path

	def refresh_tree(self):
		self.path = self.path  # Triggers re-evaluation

class DirWatcher(FileSystemEventHandler):
	def __init__(self, on_change):
		super().__init__()
		self.on_change = on_change

	def on_any_event(self, event):
		self.on_change()

class ExtendedTextArea(TextArea):
	def _on_key(self, event: Key) -> None: # type: ignore
		o = {
			"(": ")",
			"[": "]",
			"{": "}",
			'"': '"',
			"'": "'",
		}
		if event.character in ["(", "[", "{", '"', "'"]:
			self.insert(event.character)
			self.insert(o[event.character])
			self.move_cursor_relative(columns=-1)
			event.prevent_default()

class TerMan(App):
	CSS_PATH = "main.tcss"
	BINDINGS = [
		Binding("q", "quit", "Quit", show=False, priority=True)
	]
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.current_file = None
		self.saved = ""
	def compose(self) -> ComposeResult:
		self.fdt = FilteredDirectoryTree(Path("."), id="tree", parent=self)
		self.start_watcher()
		self.cmd = Input(id="cmd", placeholder="Enter command")
		self.text = ExtendedTextArea(id="text", tab_behavior="indent", show_line_numbers=True, line_number_start=1, language="python")
		yield self.fdt
		yield self.text
		yield self.cmd

	def action_select_all_text(self):
		self.text.select_all()

	def start_watcher(self):
		handler = DirWatcher(lambda: self.call_from_thread(self.fdt.refresh_tree))
		observer = Observer()
		observer.schedule(handler, ".", recursive=True)
		observer_thread = threading.Thread(target=observer.start, daemon=True)
		observer_thread.start()

	def select_file(self):
		if self.current_file:
			ext = os.path.splitext(self.current_file)[1]
			if ext == ".py":
				self.text.language = "python"
			elif ext == ".md":
				self.text.language = "markdown"
			else:
				self.text.language = None
			with open(self.current_file, "r") as f:
				self.text.text = f.read()

	async def on_key(self, event: Key) -> None:
		if event.key == "ctrl+h":
			self.fdt.show_hidden = not self.fdt.show_hidden
		elif event.key == "ctrl+c" and self.cmd.value:
			self.cmd.clear()
		elif event.key == "ctrl+e":
			self.cmd.focus()
		elif event.key == "ctrl+e":
			self.cmd.focus()
		elif event.key == "ctrl+a":
			self.text.select_all()
			event.prevent_default()
		elif event.key == "ctrl+v":
			clipboard = pyperclip.paste()
			if result := self.text._replace_via_keyboard(clipboard, *self.text.selection):
				self.text.move_cursor(result.end_location)
		elif event.key == "ctrl+s":
			if self.current_file:
				self.saved = self.text.text
				with open(self.current_file, "w") as f:
					f.truncate(0)
					f.write(self.text.text)
		elif event.key == "enter":
			text = self.cmd.value
			self.cmd.value = ""
			self.text.focus()
			self.cmd.clear()
			if text:
				self.run_command(text)

	def error(self, error: str, msg: str):
		self.notify(title=error, message=msg, severity="error", markup=True)

	def run_command(self, command):
		match command:
			case "q" | "Q" | "quit" | "exit":
				self.exit()
			case _:
				args = command.split(" ")
				command = args[0]
				if command == "touch":
					if len(args) > 1:
						file = args[1]
						if not os.path.exists(file):
							with open(file, "w") as f:
								f.write("")
						else: self.error("TerMan checked for you!", f"Error: File '{file}' already exists")
					else: self.error("TerMan is angry", "Error: Command 'touch' requires an argument")
				elif command == "rm":
					if len(args) > 1:
						file = args[1]
						if os.path.exists(file):
							os.remove(file)
						else: self.error("TerMan searched everywhere...", f"Error: File '{file}' does not exist")
					else: self.error("TerMan is angry", "Error: Command 'rm' requires an argument")
				elif command == "mkdir":
					if len(args) > 1:
						dir = args[1]
						if not os.path.exists(dir):
							os.mkdir(dir)
						else: self.error("TerMan checked for you!", f"Error: Directory '{dir}' already exists")
					else: self.error("TerMan is angry", "Error: Command 'mkdir' requires an argument")
				elif command == "rmdir":
					if len(args) > 1:
						dir = args[1]
						if os.path.exists(dir):
							os.rmdir(dir)
						else: self.error("TerMan searched everywhere...", f"Error: Directory '{dir}' does not exist")
					else: self.error("TerMan is angry", "Error: Command 'rmdir' requires an argument")
				elif command == "cd":
					if len(args) > 1:
						dir = args[1]
						dir = os.path.expanduser(dir)
						dir = os.path.expandvars(dir)
						dir = os.path.abspath(dir)
						if os.path.exists(dir):
							os.chdir(dir)
							self.fdt.label.update(basename(abspath(self.fdt.path)))
							self.fdt.refresh_tree()
						else: self.error("TerMan searched everywhere...", f"Error: Directory '{dir}' does not exist")
					else: self.error("TerMan is angry", "Error: Command 'cd' requires an argument")
				elif command == "cp":
					if len(args) > 2:
						src = args[1]
						dst = args[2]
						if os.path.exists(src):
							shutil.copyfile(src, dst)
						else: self.error("TerMan searched everywhere...", f"Error: File '{src}' does not exist")
					else: self.error("TerMan is angry", "Error: Command 'cp' requires two arguments")
				elif command == "mv":
					if len(args) > 2:
						src = args[1]
						dst = args[2]
						if os.path.exists(src):
							shutil.move(src, dst)
						else: self.error("TerMan searched everywhere...", f"Error: File '{src}' does not exist")
					else: self.error("TerMan is angry", "Error: Command 'mv' requires two arguments")
				elif command == "help":
					all_commands = [
						"- help",
						"- q/Q/quit/exit",
						"- touch <file>",
						"- rm <file>",
						"- mkdir <dir>",
						"- rmdir <dir>",
						"- cd <dir>",
						"- cp <src> <dst>",
						"- mv <src> <dst>",
					]
					self.notify(message="\n".join(all_commands), title="All Commands:", severity="information", markup=True)
				else: self.error("TerMan is shocked", f"Error: Command '{command}' not found")

if __name__ == "__main__":
	app = TerMan(watch_css=True)
	app.run()
