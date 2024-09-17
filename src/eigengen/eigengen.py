from typing import Dict, List, Optional
import argparse
import sys
import os
import tempfile
import subprocess

import colorama

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, logging, api


def is_output_to_terminal() -> bool:
    return sys.stdout.isatty()


def get_prompt_from_editor() -> Optional[str]:
    editor = os.environ.get("EDITOR", "nano")

    # Define pre-fill content
    prefill_line1 = "# Enter your prompt here. These first two lines will be ignored."
    prefill_line2 = "# Save and close the editor when you're done."

    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(f"{prefill_line1}\n{prefill_line2}\n\n")

    try:
        subprocess.run([editor, temp_file_path], check=True)

        with open(temp_file_path, 'r') as file:
            lines = file.readlines()

        # Remove the first two lines if they match the pre-filled content
        if len(lines) >= 2 and lines[0].strip() == prefill_line1 and lines[1].strip() == prefill_line2:
            lines = lines[2:]

        # Keep all lines, including empty ones and lines starting with #
        prompt_lines = [line.rstrip('\n') for line in lines]

        if not ''.join(prompt_lines).strip():
            print("No prompt entered. Exiting.")
            return None

        return '\n'.join(prompt_lines)
    finally:
        os.unlink(temp_file_path)


def get_prompt_from_editor_for_review() -> Optional[str]:
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write("# Code Review Workflow: Enter your prompt here. Lines starting with # will be ignored.\n")
        temp_file.write("# Save and close the editor when you're done.\n\n")

    try:
        subprocess.run([editor, temp_file_path], check=True)

        with open(temp_file_path, 'r') as file:
            lines = file.readlines()

        # Filter out comments and empty lines
        prompt_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]

        if not prompt_lines:
            print("No prompt entered. Exiting.")
            return None

        return "\n".join(prompt_lines)
    finally:
        os.unlink(temp_file_path)


def code_review(model: str, files: Optional[List[str]], prompt: str) -> None:
    while True:
        review_messages: List[Dict[str, str]] = []
        is_first_round = True

        while True:
            full_answer, _, diff, _ = operations.do_code_review_round(model, files, prompt, review_messages, is_first_round)
            print(full_answer)

            # Present the diff to the user for review
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_file.write("Hello, here are my code review comments in-line. Please address them and resubmit, thank you!\n\n")
                for line in diff.splitlines():
                    temp_file.write(f"> {line}\n")
                temp_file_path = temp_file.name

            with open(temp_file_path, 'r') as temp_file:
                original_review_content = temp_file.read()

            editor = os.environ.get("EDITOR", "nano")
            subprocess.run([editor, temp_file_path], check=True)

            with open(temp_file_path, 'r') as temp_file:
                review_content = temp_file.read()

            os.unlink(temp_file_path)

            if review_content.strip() == original_review_content.strip():
                # No changes made, ask if we should apply the diff
                apply = input("No changes made to the review. Do you want to apply the changes? (Y/n): ").strip().lower()
                if apply == 'y' or apply == '':
                    operations.apply_patch(diff, auto_apply=True)
                break
            else:
                # Changes made, continue the review process
                review_messages = [{"role": "assistant", "content": diff},
                                   {"role": "user", "content": review_content}]
                is_first_round = False

        # After completing a review round, re-prompt for a new review cycle
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
    args = parser.parse_args()
    # Initialize colorama for cross-platform color support
    colorama.init()

    if args.list_history is not None:
        logging.list_prompt_history(args.list_history)
        return

    files_list = operations.get_file_list(args.git_files, args.files)
    if args.web:
        host, port = args.web.split(':') if ':' in args.web else ("localhost", "10366")
        api.start_api(args.model, files_list, host, int(port))
        return

    prompt = args.prompt
    if not prompt:
        prompt = get_prompt_from_editor()
        if not prompt:
            return

    logging.log_prompt(prompt)

    if args.code_review:
        code_review(args.model, files_list, prompt)
    elif args.diff:
        use_color = (args.color == "always") or (args.color == "auto" and is_output_to_terminal())
        operations.diff_mode(args.model, files_list, prompt, use_color, args.debug)
    else:
        operations.default_mode(args.model, files_list, prompt)


if __name__ == "__main__":
    main()


