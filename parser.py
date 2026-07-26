import re
from typing import List, Dict, Any, Optional

class ASTNode:
    """
    Represents a single node in the parsed Ren'Py AST.
    """
    def __init__(self, node_type: str, line_num: int, content: Optional[Dict[str, Any]] = None, indent: int = 0, filepath: str = ""):
        self.node_type = node_type
        self.line_num = line_num
        self.content = content or {}
        self.indent = indent
        self.filepath = filepath
        self.children: List['ASTNode'] = []

    def add_child(self, child: 'ASTNode'):
        self.children.append(child)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the node and its children to a dictionary format.
        """
        return {
            "type": self.node_type,
            "line_num": self.line_num,
            "indent": self.indent,
            "content": self.content,
            "children": [c.to_dict() for c in self.children]
        }

    def __repr__(self) -> str:
        return f"ASTNode({self.node_type}, line={self.line_num}, indent={self.indent}, content={self.content})"


class RPYParser:
    """
    A lightweight parser for DDLC/Ren'Py script files (.rpy).
    It parses indentation-based blocks, labels, dialogue, choices, control flow,
    and Python script blocks.
    """
    def __init__(self):
        # Regex patterns for matching common Ren'Py statements
        self.label_pattern = re.compile(r"^label\s+([a-zA-Z0-9_]+)(?:\((.*)\))?\s*:")
        self.call_expr_pattern = re.compile(r"^call\s+expression\s+(.+)")
        self.jump_expr_pattern = re.compile(r"^jump\s+expression\s+(.+)")
        self.call_screen_pattern = re.compile(r"^call\s+screen\s+([a-zA-Z0-9_]+)(?:\((.*)\))?")
        self.jump_pattern = re.compile(r"^jump\s+([a-zA-Z0-9_]+)")
        self.call_pattern = re.compile(r"^call\s+([a-zA-Z0-9_]+)(?:\((.*)\))?")
        self.define_pattern = re.compile(r"^define\s+([a-zA-Z0-9_\.]+)\s*=\s*(.+)")
        
        # Dialogue: e.g., mc "dialogue" or s 1a "dialogue" or "dialogue without character"
        # We look for a character tag (like 's' or 'mc' or 'narrator') optionally followed by transition/pose codes (like '1a', '4p zorder 2')
        # and then a quoted string. Or just a quoted string by itself.
        self.dialogue_pattern = re.compile(r'^([a-zA-Z0-9_]+)(?:\s+([^"]+))?\s+"([^"]*)"$')
        self.narration_pattern = re.compile(r'^"([^"]*)"$')
        
        # Single-line python: $ var = val
        self.python_line_pattern = re.compile(r"^\$\s*(.+)")
        
        # Control Flow: if, elif, else
        self.if_pattern = re.compile(r"^if\s+(.+)\s*:")
        self.elif_pattern = re.compile(r"^elif\s+(.+)\s*:")
        self.else_pattern = re.compile(r"^else\s*:")
        
        # Choice menus
        self.menu_pattern = re.compile(r"^menu\s*:")
        self.menu_choice_pattern = re.compile(r'^"([^"]+)"(?:\s+if\s+(.+))?\s*:')

    def parse_line(self, line: str, line_num: int, indent: int) -> ASTNode:
        """
        Parses a single line of text and returns a corresponding ASTNode.
        """
        stripped = line.strip()

        # 1. Label definition
        match = self.label_pattern.match(stripped)
        if match:
            return ASTNode("label", line_num, {"name": match.group(1), "args": match.group(2)}, indent)

        # 2. Dynamic Call/Jump expressions
        match = self.call_expr_pattern.match(stripped)
        if match:
            return ASTNode("call_expr", line_num, {"expr": match.group(1)}, indent)

        match = self.jump_expr_pattern.match(stripped)
        if match:
            return ASTNode("jump_expr", line_num, {"expr": match.group(1)}, indent)

        match = self.call_screen_pattern.match(stripped)
        if match:
            return ASTNode("call_screen", line_num, {"screen": match.group(1), "args": match.group(2)}, indent)

        # 3. Jump statement
        match = self.jump_pattern.match(stripped)
        if match:
            return ASTNode("jump", line_num, {"label": match.group(1)}, indent)

        # 4. Call statement
        match = self.call_pattern.match(stripped)
        if match:
            return ASTNode("call", line_num, {"label": match.group(1), "args": match.group(2)}, indent)


        # 4. Return statement
        if stripped == "return":
            return ASTNode("return", line_num, {}, indent)

        # 5. Define statement
        match = self.define_pattern.match(stripped)
        if match:
            return ASTNode("define", line_num, {"var": match.group(1), "expr": match.group(2)}, indent)

        # 6. Python block start (python:, init python:, init offset python:, etc.)
        if stripped == "python:" or stripped == "python early:" or stripped.endswith("python:") or "python:" in stripped:
            return ASTNode("python_block", line_num, {"lines": []}, indent)

        # 7. Single line Python execution
        match = self.python_line_pattern.match(stripped)
        if match:
            return ASTNode("python_line", line_num, {"code": match.group(1)}, indent)

        # 8. Menu definition
        match = self.menu_pattern.match(stripped)
        if match:
            return ASTNode("menu", line_num, {}, indent)

        # 9. Menu choice
        match = self.menu_choice_pattern.match(stripped)
        if match:
            return ASTNode("menu_choice", line_num, {"text": match.group(1), "condition": match.group(2)}, indent)

        # 10. Conditional structures
        match = self.if_pattern.match(stripped)
        if match:
            return ASTNode("if", line_num, {"condition": match.group(1)}, indent)

        match = self.elif_pattern.match(stripped)
        if match:
            return ASTNode("elif", line_num, {"condition": match.group(1)}, indent)

        match = self.else_pattern.match(stripped)
        if match:
            return ASTNode("else", line_num, {}, indent)

        # 11. Dialogue
        match = self.dialogue_pattern.match(stripped)
        if match:
            return ASTNode("dialogue", line_num, {
                "char": match.group(1),
                "attributes": match.group(2).strip() if match.group(2) else None,
                "text": match.group(3)
            }, indent)

        # 12. Narration (quoted string on its own)
        match = self.narration_pattern.match(stripped)
        if match:
            return ASTNode("narration", line_num, {"text": match.group(1)}, indent)

        # 13. General commands (play music, stop sound, show, hide, scene, with, play, stop)
        parts = stripped.split(None, 1)
        if parts and parts[0] in ("play", "stop", "show", "hide", "scene", "with"):
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            return ASTNode("command", line_num, {"cmd": cmd, "args": args}, indent)

        # 14. Fallback: Treat as a raw/unknown command or statement
        return ASTNode("unknown", line_num, {"raw": stripped}, indent)

    def parse_file(self, file_path: str) -> ASTNode:
        """
        Parses a Ren'Py file and returns the root ASTNode representing the script structure.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Root node of the file AST
        root = ASTNode("root", 0, {"file": file_path}, -1, filepath=file_path)
        
        # A stack to keep track of active parent nodes based on indentation levels.
        # Format of elements: (indentation_level, ASTNode)
        stack = [(-1, root)]

        in_python_block = False
        python_block_node = None
        python_block_indent = 0

        for idx, line in enumerate(lines):
            line_num = idx + 1
            stripped_line = line.strip()

            # Skip empty lines and comment lines (except inside multi-line python blocks, where they might be comments)
            if not stripped_line:
                continue
            
            # Count leading spaces for indentation level
            indent = len(line) - len(line.lstrip())

            # If we are parsing a python block:
            if in_python_block:
                if indent > python_block_indent:
                    # Collect lines inside the python block
                    python_block_node.content["lines"].append(line)
                    continue
                else:
                    # Indent is back to or less than the python block start level, exit python block parsing
                    in_python_block = False
                    python_block_node = None

            # Skip regular comment lines
            if stripped_line.startswith("#"):
                continue

            # Parse the line to get a new node
            node = self.parse_line(line, line_num, indent)
            node.filepath = file_path

            # Handle the transition to a python block
            if node.node_type == "python_block":
                in_python_block = True
                python_block_node = node
                python_block_indent = indent

            # Find the correct parent based on indentation stack
            while stack and stack[-1][0] >= indent:
                stack.pop()

            if not stack:
                # Fallback in case of indent mismatch, attach to root
                parent = root
            else:
                parent = stack[-1][1]

            parent.add_child(node)
            
            # Push this node onto the stack to act as a potential parent for subsequent lines
            stack.append((indent, node))

        return root


if __name__ == "__main__":
    # Quick self-test with a script-ch0 snippet or definitions snippet
    import sys
    import json
    
    parser = RPYParser()
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"Parsing {test_file}...")
        root_node = parser.parse_file(test_file)
        
        # Print top-level nodes for verification
        print(f"Top-level children found: {len(root_node.children)}")
        for child in root_node.children[:15]:
            print(f" - {child.node_type} at line {child.line_num}: {child.content}")
    else:
        print("Usage: python parser.py <rpy_file>")
