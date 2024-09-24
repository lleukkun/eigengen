from typing import Dict, List, Optional
import argparse
import cProfile
import sys
import os
import tempfile
import subprocess

import colorama

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, log, api, indexing, gitfiles


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


def code_review(model: str, git_files: Optional[List[str]], user_files: Optional[List[str]], prompt: str) -> None:
    while True:
        review_messages: List[Dict[str, str]] = []
        is_first_round = True
        current_git_files = git_files
        while True:
            full_answer, _, diff, _ = operations.do_code_review_round(model, current_git_files, user_files, prompt, review_messages, is_first_round)

            # Present the diff to the user for review
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_file.write("Hello, here are my code review comments in-line. Please address them and resubmit, thank you!\n\n")
                for line in diff.splitlines():
                    temp_file.write(f"> {line}\n")
                temp_file_path = temp_file.name

            with open(temp_file_path, 'r') as temp_file:
                original_review_content = temp_file.read()

            editor = os.environ.get("EDITOR", "nano")
            command = editor + " " + temp_file_path
            subprocess.run([command], shell=True, check=True)

            with open(temp_file_path, 'r') as temp_file:
                review_content = temp_file.read()

            os.remove(temp_file_path)

            if review_content.strip() == original_review_content.strip():
                # No changes made, ask if we should apply the diff
                apply = input("\n\nNo changes made to the review. Do you want to apply the changes? (Y/n): ").strip().lower()
                if apply == 'y' or apply == '':
                    operations.apply_patch(diff, auto_apply=True)
                    # Update index after applying changes, but only for git files
                    if git_files:
                        current_git_files = gitfiles.get_filtered_git_files()
                        indexing.index_files(current_git_files)
                break
            else:
                # Changes made, continue the review process
                review_messages = [{"role": "assistant", "content": diff},
                                   {"role": "user", "content": review_content}]
                is_first_round = False

        # After completing a review round, ask if the user wants to continue
        continue_review = input("\nDo you want to start a new code review cycle? (y/N): ").strip().lower()
        if continue_review != 'y':
            break

        # If continuing, re-prompt for a new review cycle
        print("\nStarting a new code review cycle.")
        prompt = get_prompt_from_editor_for_review()
        if not prompt:
            break


def main() -> None:
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true", help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use (if not provided, opens editor)")
    parser.add_argument("--diff", "-d", action="store_true", help="Enable diff output mode")
    parser.add_argument("--code-review", "-r", action="store_true", help="Enable code review mode")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--web", "-w", nargs="?", const="localhost:10366", metavar="HOST:PORT",
                        help="Start the API service (default: localhost:10366)")
    parser.add_argument("--quote", "-q", metavar="FILE", help="Quote the content of the specified file in the prompt")
    parser.add_argument("--index", action="store_true", help="Index the files for future use")
    parser.add_argument("--test-cache-loading", action="store_true", help="Test cache loading")
    parser.add_argument("--profile", action="store_true", help="Profile cache loading")
    args = parser.parse_args()

    # Initialize colorama for cross-platform color support
    colorama.init()

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

    if args.web:
        start_api_service(args.model, list(combined_files), args.web)
        return

    prompt = prepare_prompt(args)
    if not prompt:
        return

    log.log_prompt(prompt)

    execute_mode(args, prompt, git_files, user_files)


def test_cache_loading(profile: bool) -> None:
    if profile:
        cProfile.run("from eigengen import indexing\n_ = indexing.read_cache_state()")
    else:
        _ = indexing.read_cache_state()


def index_files(use_git_files: bool) -> None:
    git_files = operations.gitfiles.get_filtered_git_files() if use_git_files else []
    indexing.index_files(git_files)


def start_api_service(model: str, filenames: List[str], web_arg: str) -> None:
    host, port = web_arg.split(':') if ':' in web_arg else ("localhost", "10366")
    api.start_api(model, filenames, host, int(port))


def prepare_prompt(args: argparse.Namespace) -> Optional[str]:
    if args.prompt:
        return args.prompt

    if args.quote:
        return get_prompt_from_editor_with_quoted_file(args.quote)

    return get_prompt_from_editor()


def execute_mode(args: argparse.Namespace, prompt: str, git_files: List[str], user_files: Optional[List[str]]) -> None:
    if args.code_review:
        code_review(args.model, git_files, user_files, prompt)
    elif args.diff:
        use_color = (args.color == "always") or (args.color == "auto" and is_output_to_terminal())
        operations.diff_mode(args.model, git_files, user_files, prompt, use_color, args.debug)
    else:
        operations.default_mode(args.model, git_files, user_files, prompt)


if __name__ == "__main__":
    main()

