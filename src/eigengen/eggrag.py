from typing import List, Tuple

from eigengen import utils
from eigengen.rag.file_parser import FileParser
from eigengen.rag.inverted_index import InvertedIndexBuilder
from eigengen.rag.context_extractor import ContextExtractor


class EggRag:
    def __init__(self):
        """
        Initializes the EggRag semantic storage.

        Args:
        """
        # construct the index based on git files
        file_list = utils.get_git_files("*.py")
        all_tokens = []
        for file_path in file_list:
            tokens = FileParser.parse_file(file_path)
            all_tokens.extend(tokens)

        index_builder = InvertedIndexBuilder(all_tokens)
        self.filtered_index = index_builder.get_filtered_index(threshold=3)

    def retrieve(self, target_files: list[str]) -> List[Tuple[str, int, str]]:
        """
        Returns the top N best matches for the query content using hnswlib for nearest neighbour search.

        Args:
            query_content (str): The query text.
            top_n (int): Number of unique file matches to return.
            path_prefix (str | None): Optional prefix to filter file_path.
            target_files (list[str] | None): Optional list of target files for context construction.

        Returns:
            List[Tuple[str, int, str]]: A list of tuples containing file_path, modification_time, content.
        """
        # NEW: If target_files are provided, use the new context construction system
        if len(target_files) <= 0:
            return []

        context_extractor = ContextExtractor(self.filtered_index, context_lines=2)
        contexts = []
        for f in target_files:
            extracted = context_extractor.extract_context(f)
            for token, snippet_list in extracted.items():
                for snippet_info in snippet_list:
                    # quote snippet lines with a prefix '> '
                    snippet_info["snippet"] = "\n".join([f"> {line}" for line in snippet_info["snippet"].split("\n")])
                    contexts.append(
                        (snippet_info["file"], 0,
                            f"In file {snippet_info['file']} for token '{token}':\n{snippet_info['snippet']}")
                    )
        return contexts


class NoOpEggRag:
    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        print(f"RAG is disabled. Skipping indexing for '{file_path}'.")

    def retrieve(self, target_files: list[str]) -> list[tuple[str, int, str]]:
        return []
