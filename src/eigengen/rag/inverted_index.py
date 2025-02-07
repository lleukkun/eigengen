from typing import List, Dict, Set

class InvertedIndexBuilder:
    def __init__(self, tokens: List[Dict]):
        """
        tokens: List of token dictionaries produced by file_parser.py.
        Each token dictionary must have at least:
         - "token": the token string,
         - "file": the source file path.
        """
        self.tokens = tokens
        self.index: Dict[str, Set[str]] = {}

    def build_index(self) -> Dict[str, Set[str]]:
        """
        Build the inverted index mapping each unique token to a set of file paths where it appears.
        Returns a dictionary where key: token, value: set of file paths.
        """
        for token_info in self.tokens:
            token = token_info.get("token")
            file_path = token_info.get("file")
            if token is None or file_path is None:
                continue
            if token not in self.index:
                self.index[token] = set()
            self.index[token].add(file_path)
        return self.index

    def get_filtered_index(self, threshold: int = 10) -> Dict[str, Set[str]]:
        """
        Returns a filtered inverted index, retaining only those tokens which appear in fewer than `threshold` files.
        For example, a threshold of 10 retains tokens that occur in 1-9 unique files.
        """
        if not self.index:
            self.build_index()

        filtered_index = {token: files for token, files in self.index.items() if len(files) < threshold}
        return filtered_index

# Example usage:
if __name__ == "__main__":
    # This is just an example, assuming tokens were obtained from file_parser.py
    # For actual integration, replace the following with a call to FileParser.parse_file(<path>).
    sample_tokens = [
        {"token": "MyClass", "line": 1, "column": 0, "file": "example.py"},
        {"token": "def", "line": 2, "column": 4, "file": "example.py"},
        {"token": "MyClass", "line": 5, "column": 0, "file": "example.ts"},
        {"token": "uniqueFunc", "line": 10, "column": 2, "file": "example2.py"},
        {"token": "def", "line": 11, "column": 4, "file": "example2.py"},
    ]

    builder = InvertedIndexBuilder(sample_tokens)
    index = builder.build_index()
    print("Full Inverted Index:")
    for token, files in index.items():
        print(f"  {token}: {list(files)}")

    filtered = builder.get_filtered_index(threshold=3)
    print("\nFiltered Inverted Index (tokens in fewer than 3 files):")
    for token, files in filtered.items():
        print(f"  {token}: {list(files)}")
