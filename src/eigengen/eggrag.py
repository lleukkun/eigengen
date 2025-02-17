from logging import getLogger
from typing import List, Tuple

from eigengen import utils

logger = getLogger(__name__)


class EggRag:
    def __init__(self):
        """
        Initializes the EggRag semantic storage.

        Args:
        """
        # construct the index based on git files
        _ = utils.get_git_files("*.py")

    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        """
        Adds a file to the EggRag index.

        Args:
            file_path (str): The path to the file.
            modification_time (int): The modification time of the file.
            content (str): The content of the file.

        Returns:
            None
        """
        logger.info(f"Adding file '{file_path}' to EggRag index.")

    def retrieve(self, target_files: list[str]) -> List[Tuple[str, int, str]]:
        return []


class NoOpEggRag:
    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        logger.info(f"RAG is disabled. Skipping indexing for '{file_path}'.")

    def retrieve(self, target_files: list[str]) -> list[tuple[str, int, str]]:
        return []
