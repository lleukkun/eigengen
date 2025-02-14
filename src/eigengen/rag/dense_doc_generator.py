#!/usr/bin/env python3
"""
dense_doc_generator.py

This module scans source files to generate a dense text summary that lists
all public classes and methods/functions along with their input/output signatures.
Currently supports Python (.py), TypeScript (.ts), and C/C++ header files (.h, .hpp).
"""

import argparse
import ast
import logging
import os
import re
import warnings
from typing import Dict, List

import pathspec


############# Python Parsing using AST #############
class PythonDocVisitor(ast.NodeVisitor):
    def __init__(self):
        self.entries: List[str] = []

    def visit_module(self, node: ast.Module):
        # Look for top-level functions
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and not child.name.startswith("_"):
                signature = self._get_function_signature(child)
                doc = ast.get_docstring(child)
                doc_str = f" - Doc: {doc.splitlines()[0]}" if doc else ""
                self.entries.append(f"Function {child.name}{signature}{doc_str}")
        # Continue with classes
        self.generic_visit(node)

    def visit_classdef(self, node: ast.ClassDef):
        # Consider only public classes (not starting with underscore)
        if not node.name.startswith("_"):
            base_names = [self._format_expr(b) for b in node.bases]
            bases = f"({', '.join(base_names)})" if base_names else ""
            self.entries.append(f"Class {node.name}{bases}:")
            # Include class docstring if available
            class_doc = ast.get_docstring(node)
            if class_doc:
                self.entries.append(f"  Doc: {class_doc.splitlines()[0]}")
            # Process methods inside the class (always include __init__)
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and (item.name == "__init__" or not item.name.startswith("_")):
                    signature = self._get_function_signature(item)
                    doc = ast.get_docstring(item)
                    doc_str = f" - Doc: {doc.splitlines()[0]}" if doc else ""
                    if item.name == "__init__":
                        self.entries.append(f"  Constructor{signature}{doc_str}")
                    else:
                        self.entries.append(f"  Method {item.name}{signature}{doc_str}")
        # Do not recurse into inner classes (if not needed)

    def _format_expr(self, expr: ast.expr) -> str:
        # Helper to pretty-print base classes
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            return f"{self._format_expr(expr.value)}.{expr.attr}"
        return ast.dump(expr)

    def _get_function_signature(self, func_node: ast.FunctionDef) -> str:
        # Create a signature string: (arg1: type, arg2: type, ...) -> return_annotation
        arg_list = []
        for arg in func_node.args.args:
            # skip "self" for methods except for constructors
            if arg.arg == "self":
                continue
            if arg.annotation:
                annotation = self._get_annotation(arg.annotation)
                arg_list.append(f"{arg.arg}: {annotation}")
            else:
                arg_list.append(arg.arg)
        # Process possible varargs and kwargs with annotations if available
        if func_node.args.vararg:
            vararg = func_node.args.vararg
            if vararg.annotation:
                annotation = self._get_annotation(vararg.annotation)
                arg_list.append(f"*{vararg.arg}: {annotation}")
            else:
                arg_list.append(f"*{vararg.arg}")
        if func_node.args.kwarg:
            kwarg = func_node.args.kwarg
            if kwarg.annotation:
                annotation = self._get_annotation(kwarg.annotation)
                arg_list.append(f"**{kwarg.arg}: {annotation}")
            else:
                arg_list.append(f"**{kwarg.arg}")
        params = ", ".join(arg_list)
        ret = ""
        if func_node.returns:
            ret = " -> " + self._get_annotation(func_node.returns)
        return f"({params}){ret}"

    def _get_annotation(self, node: ast.expr) -> str:
        try:
            # ast.unparse is available in Python 3.9+
            return ast.unparse(node)
        except Exception:
            # Fallback for older versions
            return "<annotation>"


def parse_python_file(file_path: str) -> List[str]:
    """
    Parses a Python file and returns a list of documentation entries
    (public classes and functions with their signatures).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=file_path)
        visitor = PythonDocVisitor()
        visitor.visit(tree)
        return visitor.entries
    except Exception as ex:
        return [f"Error parsing {file_path}: {ex}"]


############# TypeScript Parsing using Regex #############
def parse_typescript_file(file_path: str) -> List[str]:
    """
    Performs a best-effort regex parsing for public classes and methods in a TypeScript file.
    Note: This is a simplified parser and may not handle all edge cases.
    """
    entries = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as ex:
        return [f"Error reading {file_path}: {ex}"]

    # Extract top-level functions
    func_pattern = re.compile(r"\bfunction\s+([A-Za-z]\w*)\s*\((.*?)\)\s*:\s*([\w<>\[\]\| ,]+)", re.DOTALL)
    for match in func_pattern.finditer(content):
        name, params, ret_type = match.groups()
        if name.startswith("_"):
            continue
        entries.append(f"Function {name}({params.strip()}) -> {ret_type.strip()}")

    # Extract classes
    # Capture class name and optionally the base class/implements clause. Then extract block.
    class_pattern = re.compile(
        r"\bclass\s+([A-Za-z]\w*)\s*(?:extends\s+([A-Za-z]\w*))?\s*(?:implements\s+([\w, ]+))?\s*\{(.*?)\n\}", re.DOTALL
    )
    method_pattern = re.compile(r"\b(public\s+)?([A-Za-z]\w*)\s*\((.*?)\)\s*:\s*([\w<>\[\]\| ,]+)", re.DOTALL)
    constructor_pattern = re.compile(r"\bconstructor\s*\((.*?)\)", re.DOTALL)
    for class_match in class_pattern.finditer(content):
        class_name, base, implements, class_body = class_match.groups()
        if class_name.startswith("_"):
            continue
        bases_parts = []
        if base:
            bases_parts.append(base)
        if implements:
            bases_parts.append("implements " + implements.replace(" ", ""))
        bases_str = f"({', '.join(bases_parts)})" if bases_parts else ""
        entries.append(f"Class {class_name}{bases_str}:")
        # Extract constructors
        for c_match in constructor_pattern.finditer(class_body):
            params = c_match.group(1).strip()
            entries.append(f"  Constructor({params})")
        # Find methods in class body
        for m in method_pattern.finditer(class_body):
            public_mod, method_name, params, ret_type = m.groups()
            if method_name.startswith("_"):
                continue
            entries.append(f"  Method {method_name}({params.strip()}) -> {ret_type.strip()}")
    return entries


############# C/C++ Header Parsing using Regex and Sanitization #############
def sanitize_header_content(content: str) -> str:
    """
    Sanitize header file content by doubling backslashes that lead to invalid escape sequences.
    This replaces a single backslash that is not followed by a valid escape character with two backslashes.
    """
    # Valid escapes in Python: \\, \', \", \a, \b, \f, \n, \r, \t, \v
    return re.sub(r'\\(?![\\\'"abfnrtv])', r"\\\\", content)


def parse_header_file(file_path: str) -> List[str]:
    """
    Performs a simplified regex parsing for C/C++ header files (.h, .hpp) to extract
    public classes (and their public method prototypes) as well as free function prototypes.
    """
    entries = []
    content = ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Sanitize header content to guard against invalid escape sequences from file content.
        # content = sanitize_header_content(content)
    except Exception as ex:
        return [f"Error reading {file_path}: {ex}"]

    # Remove multiline and single-line comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r"//.*", "", content)

    # Extract class definitions (C++ style only)
    class_pattern = re.compile(r"\bclass\s+(\w+).*?\{(.*?)\};", re.DOTALL)
    for class_match in class_pattern.finditer(content):
        class_name, class_body = class_match.groups()
        if class_name.startswith("_"):
            continue
        entries.append(f"Class {class_name}:")
        # Attempt to extract the public section within the class body
        public_match = re.search(r"public:\s*(.*?)(?=\n\s*(private:|protected:|$))", class_body, re.DOTALL)
        if public_match:
            public_section = public_match.group(1)
            # Regex for method prototypes in public section:
            method_pattern = re.compile(r"([^\s].*?[^\s])\s+(\w+)\s*\((.*?)\)\s*;", re.DOTALL)
            for m in method_pattern.finditer(public_section):
                ret_type, method_name, params = m.groups()
                if method_name.startswith("_"):
                    continue
                entries.append(f"  Method {method_name}({params.strip()}) -> {ret_type.strip()}")

    # Extract free function prototypes that are not inside classes
    free_func_pattern = re.compile(r"^\s*([^\s].*?[^\s])\s+(\w+)\s*\((.*?)\)\s*;\s*$", re.MULTILINE)
    for f_match in free_func_pattern.finditer(content):
        ret_type, func_name, params = f_match.groups()
        if func_name.startswith("_"):
            continue
        entries.append(f"Function {func_name}({params.strip()}) -> {ret_type.strip()}")
    return entries


############# Generator Function #############
def generate_dense_docs(target_directory: str, output_file: str) -> None:
    """
    Scans the target directory (recursively) for source code files (.py, .ts, .h, .hpp)
    and generates a dense text document listing public classes, methods, and functions
    with their signatures.
    """
    all_entries: Dict[str, List[str]] = {}
    # Load .gitignore rules if present in the target_directory
    gitignore_path = os.path.join(target_directory, ".gitignore")
    spec = None
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, "r", encoding="utf-8") as git_file:
                lines = git_file.read().splitlines()
            spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
        except Exception as ex:
            logging.warning(f"Unable to load .gitignore: {ex}")

    for root, _, files in os.walk(target_directory):
        for file in files:
            # Process Python, TypeScript, and now C/C++ header files
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                # Check against .gitignore patterns if available
                rel_for_gitignore = os.path.relpath(file_path, target_directory)
                if spec and spec.match_file(rel_for_gitignore):
                    continue
                entries = parse_python_file(file_path)
            elif file.endswith(".ts"):
                file_path = os.path.join(root, file)
                rel_for_gitignore = os.path.relpath(file_path, target_directory)
                if spec and spec.match_file(rel_for_gitignore):
                    continue
                entries = parse_typescript_file(file_path)
            elif file.endswith(".h") or file.endswith(".hpp"):
                file_path = os.path.join(root, file)
                rel_for_gitignore = os.path.relpath(file_path, target_directory)
                if spec and spec.match_file(rel_for_gitignore):
                    continue
                entries = parse_header_file(file_path)
            else:
                continue

            if entries:
                # Produce file paths relative to the current working directory
                rel_path = os.path.relpath(file_path, os.getcwd())
                all_entries[rel_path] = entries

    # Write to output file
    try:
        with open(output_file, "w", encoding="utf-8") as outf:
            for file, entries in all_entries.items():
                outf.write(f"File: {file}\n")
                for entry in entries:
                    outf.write(f"  {entry}\n")
                outf.write("\n")
        logging.info(f"Dense documentation generated and written to {output_file}")
    except Exception as ex:
        logging.error(f"Error writing to output file {output_file}: {ex}")


############# Command Line Interface #############
def main():
    parser = argparse.ArgumentParser(
        description="Generate a dense documentation file listing public methods and classes with signatures."
    )
    parser.add_argument("--dir", type=str, default=".", help="Target directory to scan (default is current directory).")
    parser.add_argument(
        "--output", type=str, default="dense_docs.txt", help="Output text file for the dense documentation."
    )
    args = parser.parse_args()
    generate_dense_docs(args.dir, args.output)


if __name__ == "__main__":
    main()
