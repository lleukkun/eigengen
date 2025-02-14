import logging
import os
import re
from typing import Dict, List, Set

from eigengen.rag.file_parser import FileParser


class ContextExtractor:
    def __init__(self, filtered_index: Dict[str, Set[str]], context_lines: int = 2):
        """
        filtered_index: The dictionary mapping token to a set of file paths (tokens that occur in fewer than N files).
        context_lines: Number of lines of context to extract before and after a matching token.
        """
        self.filtered_index = filtered_index
        self.context_lines = context_lines
        # Cache file contents to avoid repeated I/O.
        self._file_content_cache: Dict[str, List[str]] = {}

    def _get_file_lines(self, file_path: str) -> List[str]:
        """
        Reads file content and caches it. Returns a list of lines.
        """
        if file_path in self._file_content_cache:
            return self._file_content_cache[file_path]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self._file_content_cache[file_path] = lines
            return lines
        except Exception as ex:
            logging.error(f"Error reading file {file_path}: {ex}")
            return []

    def _extract_snippet(self, file_path: str, token: str) -> str:
        """
        Searches for the token (as a whole word) in the file and extracts a
        snippet with self.context_lines before and after.
        Returns the snippet as a string. If not found, returns an empty string.
        """
        lines = self._get_file_lines(file_path)
        token_regex = re.compile(r"\b" + re.escape(token) + r"\b")
        for i, line in enumerate(lines):
            if token_regex.search(line):
                start = max(0, i - self.context_lines)
                end = min(len(lines), i + self.context_lines + 1)
                snippet = "".join(lines[start:end])
                return snippet.strip()
        return ""

    def extract_context(self, target_file: str) -> Dict[str, List[Dict]]:
        """
        Constructs a context by:
         - Tokenizing the target file via FileParser.
         - For each token that is in the filtered_index and also appears in other
           files (ignoring tokens unique in target_file), extracts a code snippet
           from each related file.

        Returns a dictionary mapping each qualifying token to a list of dictionaries:
           {
               "file": related file path,
               "snippet": the extracted snippet from that file
           }
        """
        # Parse the target file to get a list of tokens.
        target_tokens_data = FileParser.parse_file(target_file)
        # Create a set of tokens present in the target file.
        target_tokens = {token_data.get("token") for token_data in target_tokens_data if token_data.get("token")}

        context = {}
        for token in target_tokens:
            # Ignore tokens that are not in the filtered index or appear only in the target file.
            if token not in self.filtered_index:
                continue
            related_files = self.filtered_index[token]
            # Remove the target file from the related files.
            related_files = {f for f in related_files if os.path.abspath(f) != os.path.abspath(target_file)}
            if not related_files:
                continue
            token_contexts = []
            for file_path in related_files:
                # Try to extract a snippet from this file.
                snippet = self._extract_snippet(file_path, token)
                if snippet:
                    token_contexts.append({"file": file_path, "snippet": snippet})
            if token_contexts:
                context[token] = token_contexts
        return context
