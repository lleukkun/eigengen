from typing import List, Optional
import argparse
import cProfile
import sys
import os
import tempfile
import subprocess

import colorama

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, log, indexing, gitfiles, chat


def is_output_to_terminal() -> bool:
    return sys.stdout.isatty()


def get_prompt_from_editor_with_prefill(prefill_content: str) -> Optional[str]:
    prefill_content += "\n"
    prompt_content = ""
    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(prefill_content)

    try:
        editor = os.environ.get("EDITOR", "nano")
        command = editor + " " + temp_file_path
        subprocess.run([command], shell=True, check=True)

        with open(temp_file_path, 'r') as file:
            prompt_content = file.read()

        if prefill_content == prompt_content:
            print("No prompt entered. Exiting.")
            return None

        return prompt_content
    finally:
        os.remove(temp_file_path)


def get_prompt_from_editor() -> Optional[str]:
    prefill_content = "# Enter your prompt here. These first two lines will be ignored.\n# Save and close the editor when you're done.\n"
    return get_prompt_from_editor_with_prefill(prefill_content)


def get_prompt_from_editor_for_review() -> Optional[str]:
    prefill_content = "# Code Review Workflow: Enter your prompt here. Lines starting with # will be ignored.\n# Save and close the editor when you're done.\n"
    return get_prompt_from_editor_with_prefill(prefill_content)


def get_prompt_from_editor_with_quoted_file(file_path: str) -> Optional[str]:
    try:
        with open(file_path, 'r') as file:
            file_content = file.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except IOError:
        print(f"Error: Unable to read file '{file_path}'.")
        return None

    quoted_content = f"quoted file: {file_path}\n> " + '\n> '.join(file_content.splitlines())
    prefill_content = f"Hello,\nPlease see inline comments for details on what must be changed.\nBe sure to change all other files that may be affected.\n\n{quoted_content}"
    return get_prompt_from_editor_with_prefill(prefill_content)



def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true", help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use (if not provided, opens editor)")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--quote", "-q", metavar="FILE", help="Quote the content of the specified file in the prompt")
    parser.add_argument("--index", action="store_true", help="Index the files for future use")
    parser.add_argument("--test-cache-loading", action="store_true", help="Test cache loading")
    parser.add_argument("--profile", action="store_true", help="Profile cache loading")
    # Add the --chat (-c) argument
    parser.add_argument("--chat", "-c", action="store_true", help="Enable chat mode")
    return parser.parse_args()


def initialize_environment() -> None:
    # Initialize colorama for cross-platform color support
    colorama.init()


def handle_modes(args: argparse.Namespace) -> None:
    if args.test_cache_loading:
        test_cache_loading(args.profile)
        return

    if args.list_history is not None:
        log.list_prompt_history(args.list_history)
        return

    user_files = args.files
    git_files = None
    if args.git_files:
        git_files = gitfiles.get_filtered_git_files()
        if args.files:
            user_files = set([gitfiles.make_relative_to_git_root(x) for x in args.files])

    combined_files = set()
    if user_files:
        combined_files.update(user_files)
    if git_files:
        combined_files.update(git_files)

    if args.index:
        index_files(args.git_files)
        return

    if args.git_files:
        index_files(args.git_files)

    if args.chat:
        chat.chat_mode(args.model, git_files, user_files)
        return

    prompt = prepare_prompt(args)
    if not prompt:
        return

    log.log_prompt(prompt)

    execute_mode(args, prompt, git_files, user_files)


def prepare_prompt(args: argparse.Namespace) -> Optional[str]:
    if args.prompt:
        return args.prompt

    if args.quote:
        return get_prompt_from_editor_with_quoted_file(args.quote)

    return get_prompt_from_editor()


def execute_mode(args: argparse.Namespace, prompt: str, git_files: List[str], user_files: Optional[List[str]]) -> None:
    operations.default_mode(args.model, git_files, user_files, prompt)


def main() -> None:
    args = parse_arguments()
    try:
        initialize_environment()
        handle_modes(args)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)


def test_cache_loading(profile: bool) -> None:
    if profile:
        cProfile.run("from eigengen import indexing\n_ = indexing.read_cache_state()")
    else:
        _ = indexing.read_cache_state()


def index_files(use_git_files: bool) -> None:
    git_files = operations.gitfiles.get_filtered_git_files() if use_git_files else []
    indexing.index_files(git_files)


if __name__ == "__main__":
    main()
