import argparse
import subprocess
import os
import json
from eigengen.rag.file_parser import FileParser
from eigengen.rag.inverted_index import InvertedIndexBuilder
from eigengen.rag.context_extractor import ContextExtractor

def get_python_files() -> list:
    """
    Runs 'git ls-files "*.py"' to get a list of Python files tracked by git.
    """
    try:
        result = subprocess.check_output(['git', 'ls-files', '*.py'], text=True)
        files = result.strip().splitlines()
        return files
    except subprocess.CalledProcessError as error:
        print("Error running git ls-files:", error)
        return []

def build_inverted_index(python_files: list, rarity_threshold: int) -> dict:
    all_tokens = []
    for file_path in python_files:
        if os.path.exists(file_path):
            print(f"Processing file: {file_path}")
            tokens = FileParser.parse_file(file_path)
            all_tokens.extend(tokens)
        else:
            print(f"File does not exist: {file_path}")

    if not all_tokens:
        print("No tokens extracted from any files.")
        return {}

    index_builder = InvertedIndexBuilder(all_tokens)
    filtered_index = index_builder.get_filtered_index(threshold=rarity_threshold)
    return filtered_index

def main():
    parser = argparse.ArgumentParser(
        description="Build inverted index from git-tracked Python files and extract context for a target file."
    )
    parser.add_argument(
        "--target",
        type=str,
        help="Path to the target file for which to build context."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=10,
        help="Rarity threshold: only tokens appearing in fewer than this many files will be used."
    )
    parser.add_argument(
        "--context_lines",
        type=int,
        default=2,
        help="Number of context lines to extract before and after a matching token."
    )
    args = parser.parse_args()

    python_files = get_python_files()
    if not python_files:
        print("No Python files found via git ls-files. Exiting.")
        return

    filtered_index = build_inverted_index(python_files, args.threshold)
    if not filtered_index:
        print("Filtered index is empty. Exiting.")
        return

    if args.target:
        if not os.path.exists(args.target):
            print(f"Target file {args.target} does not exist.")
            return

        # Instantiate ContextExtractor and extract context for the target file.
        extractor = ContextExtractor(filtered_index=filtered_index, context_lines=args.context_lines)
        context = extractor.extract_context(args.target)

        print("\nExtracted Context:")
        print(json.dumps(context, indent=2))
    else:
        print("\nNo target file specified. Inverted index build complete.")

if __name__ == "__main__":
    main()
