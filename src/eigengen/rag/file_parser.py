import os
import re
import tokenize
import keyword
import builtins
from typing import List, Dict


class BaseParser:
    def __init__(self, file_path: str, extract_comments_and_strings: bool = False):
        self.file_path = file_path
        self.extract_comments_and_strings = extract_comments_and_strings

    def parse(self) -> List[Dict]:
        """
        Returns a list of token dictionaries of the form:
        {
            "token": <str>,
            "line": <int>,           # Optional: the line number where token was found
            "column": <int>,         # Optional: the column number where token was found
            "file": <str>            # the source file
        }
        """
        raise NotImplementedError


class PythonParser(BaseParser):
    def __init__(self, file_path: str, extract_comments_and_strings: bool = False):
        super().__init__(file_path, extract_comments_and_strings)

    def parse(self) -> List[Dict]:
        tokens = []
        word_re = re.compile(r"\w+")
        # Prepare sets for filtering: keywords and built-in names.
        keyword_set = set(keyword.kwlist)
        builtin_set = set(dir(builtins))
        try:
            with open(self.file_path, "rb") as f:
                token_generator = tokenize.tokenize(f.readline)
                for tok in token_generator:
                    # Extract actual code names.
                    if tok.type == tokenize.NAME:
                        token_text = tok.string
                        # Skip if token_text is a Python keyword or built-in.
                        if token_text in keyword_set or token_text in builtin_set:
                            continue
                        tokens.append(
                            {
                                "token": token_text,
                                "line": tok.start[0],
                                "column": tok.start[1],
                                "file": self.file_path,
                            }
                        )
                    # Optionally extract tokens from strings and comments.
                    elif self.extract_comments_and_strings and tok.type in (tokenize.STRING, tokenize.COMMENT):
                        # For comment/string tokens, compare in lowercase.
                        for word in word_re.findall(tok.string):
                            if word.lower() in {w.lower() for w in keyword_set} or \
                               word.lower() in {w.lower() for w in builtin_set}:
                                continue
                            tokens.append(
                                {
                                    "token": word.lower(),  # convert to lowercase for natural language tokens
                                    "line": tok.start[0],
                                    "column": tok.start[1],
                                    "file": self.file_path,
                                }
                            )
        except Exception as ex:
            print(f"Error tokenizing Python file {self.file_path}: {ex}")
        return tokens


class TypeScriptParser(BaseParser):
    # Regular expressions to extract tokens.
    IDENTIFIER_RE = re.compile(r'\b[A-Za-z_]\w*\b')
    STRING_RE = re.compile(r'"(.*?)"|\'(.*?)\'|`(.*?)`')
    SINGLE_LINE_COMMENT_RE = re.compile(r'//(.*)')
    MULTI_LINE_COMMENT_RE = re.compile(r'/\*([\s\S]*?)\*/')
    WORD_RE = re.compile(r'\w+')

    def __init__(self, file_path: str, extract_comments_and_strings: bool = False):
        super().__init__(file_path, extract_comments_and_strings)

    def parse(self) -> List[Dict]:
        tokens = []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Always process code identifiers (case preserved)
            for match in self.IDENTIFIER_RE.finditer(content):
                token_text = match.group(0)
                tokens.append({
                    "token": token_text,
                    "line": content.count("\n", 0, match.start()) + 1,
                    "column": match.start() - content.rfind("\n", 0, match.start()),
                    "file": self.file_path
                })

            # Process string literals if enabled (convert extracted text to lowercase)
            if self.extract_comments_and_strings:
                for match in self.STRING_RE.finditer(content):
                    raw_text = match.group(1) or match.group(2) or match.group(3) or ""
                    for word in self.WORD_RE.findall(raw_text):
                        tokens.append({
                            "token": word.lower(),
                            "line": content.count("\n", 0, match.start()) + 1,
                            "column": match.start() - content.rfind("\n", 0, match.start()),
                            "file": self.file_path
                        })

                # Process single-line comments (convert tokens to lowercase)
                for match in self.SINGLE_LINE_COMMENT_RE.finditer(content):
                    comment_text = match.group(1).strip()
                    for word in self.WORD_RE.findall(comment_text):
                        tokens.append({
                            "token": word.lower(),
                            "line": content.count("\n", 0, match.start()) + 1,
                            "column": match.start() - content.rfind("\n", 0, match.start()),
                            "file": self.file_path
                        })

                # Process multi-line comments (convert tokens to lowercase)
                for match in self.MULTI_LINE_COMMENT_RE.finditer(content):
                    comment_text = match.group(1).strip()
                    for word in self.WORD_RE.findall(comment_text):
                        tokens.append({
                            "token": word.lower(),
                            "line": content.count("\n", 0, match.start()) + 1,
                            "column": match.start() - content.rfind("\n", 0, match.start()),
                            "file": self.file_path,
                        })
        except Exception as ex:
            print(f"Error tokenizing TypeScript file {self.file_path}: {ex}")
        return tokens


class FileParser:
    """
    High level interface that selects the appropriate parser based on file extension.
    Currently supports Python (.py) and TypeScript (.ts) files.
    """

    PARSER_MAP = {
        ".py": PythonParser,
        ".ts": TypeScriptParser
    }

    @staticmethod
    def parse_file(file_path: str, extract_comments_and_strings: bool = False) -> List[Dict]:
        _, ext = os.path.splitext(file_path)
        parser_cls = FileParser.PARSER_MAP.get(ext.lower())
        if not parser_cls:
            print(f"No parser implemented for extension: {ext} in file: {file_path}")
            return []
        parser = parser_cls(file_path, extract_comments_and_strings)
        return parser.parse()


# Example usage:
if __name__ == "__main__":
    # For demonstration, adjust the file paths as needed.
    sample_files = ["example.py", "example.ts"]
    all_tokens = []
    for file in sample_files:
        file_tokens = FileParser.parse_file(file)
        all_tokens.extend(file_tokens)
        print(f"Tokens from {file}:", file_tokens)

