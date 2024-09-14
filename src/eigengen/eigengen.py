from typing import Dict, List, Optional, Tuple
import argparse
import os
import sys
import difflib
import colorama
import tempfile
import re
import subprocess

from eigengen.prompts import PROMPTS, MAGIC_STRINGS, wrap_file
from eigengen.providers import create_provider, Provider, get_model_config, MODEL_CONFIGS
from eigengen.gitfiles import get_filtered_git_files

def extract_filename(tag: str) -> Optional[str]:
    pattern = r'<eigengen_file\s+name="([^"]*)">'
    match = re.search(pattern, tag)
    if match:
        return match.group(1)
    return None

def extract_file_content(output: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    file_content: List[str] = []
    file_started: bool = False
    file_name: Optional[str] = None
    for line in output.splitlines():
        if not file_started and line.strip().startswith(MAGIC_STRINGS["file_start"]):
            file_started = True
            file_name = extract_filename(line.strip())
        elif file_started:
            if line == MAGIC_STRINGS["file_end"]:
                # file is complete
                if file_name is not None:
                    files[file_name] = "\n".join(file_content) + "\n"
                file_content = []
                file_started = False
                file_name = None
            else:
                # Strip trailing whitespace from each line
                file_content.append(line.rstrip())
    return files

def generate_diff(original_content: str, new_content: str, file_name: str, use_color: bool = True) -> str:
    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(original_lines, new_lines, fromfile=f"a/{file_name}", tofile=f"b/{file_name}")

    if not use_color:
        return ''.join(diff)

    colored_diff: List[str] = []
    for line in diff:
        if line.startswith('---') or line.startswith('+++'):
            colored_diff.append(colorama.Fore.CYAN + line + colorama.Fore.RESET)
        elif line.startswith('@@'):
            colored_diff.append(colorama.Fore.CYAN + line + colorama.Fore.RESET)
        elif line.startswith('-'):
            colored_diff.append(colorama.Fore.RED + line + colorama.Fore.RESET)
        elif line.startswith('+'):
            colored_diff.append(colorama.Fore.GREEN + line + colorama.Fore.RESET)
        else:
            colored_diff.append(line)

    return ''.join(colored_diff)

def is_output_to_terminal() -> bool:
    return sys.stdout.isatty()

def apply_patch(diff: str, auto_apply: bool = False) -> None:
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp_diff_file:
        temp_diff_file.write(diff)
        temp_diff_file_path = temp_diff_file.name

    if not auto_apply:
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, temp_diff_file_path], check=True)

        apply = input("Do you want to apply the changes? (Y/n): ").strip().lower()
        if apply != 'y' and apply != '':
            print("Changes not applied.")
            os.remove(temp_diff_file_path)
            return

    try:
        subprocess.run(['patch', '-p1', '-i', temp_diff_file_path], check=True)
        print("Changes applied successfully.")
    except subprocess.CalledProcessError:
        print("Failed to apply changes. Please check the patch file and try again.")

    os.remove(temp_diff_file_path)

def process_request(model: str, messages: List[Dict[str, str]], mode: str = "default") -> Tuple[str, Dict[str, str]]:
    provider_instance: Provider = create_provider(model)
    model_config = get_model_config(model)

    system: str = PROMPTS["system"]
    if mode == "default":
        system += PROMPTS["non_diff"]
    elif mode == "diff":
        system += PROMPTS["diff"]
    elif mode == "code_review":
        system += PROMPTS["code_review"]

    final_answer: str = provider_instance.make_request(system, messages, model_config.max_tokens, model_config.temperature)
    new_files: Dict[str, str] = extract_file_content(final_answer) if mode == "diff" or mode == "code_review" else {}

    return final_answer, new_files

def code_review(model: str, files: Optional[List[str]], prompt: str) -> None:
    system_prompt_mode = "diff"
    review_messages = []
    while True:
        messages: List[Dict[str, str]] = []
        if files:
            for fname in files:
                with open(fname, "r") as f:
                    original_content = f.read()
                messages += [{"role": "user", "content": wrap_file(fname, original_content)},
                             {"role": "assistant", "content": "ok"}]
        messages.append({"role": "user", "content": prompt})
        messages += review_messages

        final_answer, new_files = process_request(model, messages, system_prompt_mode)
        # switch to review mode for later rounds
        system_prompt_mode = "code_review"
        print(final_answer)
        diff = ""
        for fname in new_files.keys():
            original_content = ""
            if files and fname in files:
                with open(fname, "r") as f:
                    original_content = f.read()
            diff += generate_diff(original_content, new_files[fname], fname, False)

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
                apply_patch(diff, auto_apply=True)
            break
        else:
            # Changes made, continue the review process
            review_messages = [{"role": "assistant", "content": diff},
                               {"role": "user", "content": review_content}]

def diff_mode(model: str, files: Optional[List[str]], prompt: str, use_color: bool, interactive: bool, debug: bool) -> None:
    messages: List[Dict[str, str]] = []
    if files:
        for fname in files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]
    messages.append({"role": "user", "content": prompt})

    final_answer, new_files = process_request(model, messages, "diff")

    diff: str = ""
    if new_files:
        for fname in new_files.keys():
            original_content: str = ""
            if files and fname in files:
                with open(fname, "r") as f:
                    original_content = f.read()
            diff += generate_diff(original_content, new_files[fname], fname, use_color)
        if debug:
            print(diff)
        if interactive:
            apply_patch(diff)
    else:
        print("Error: Unable to generate diff. Make sure both original and new file contents are available.")

def default_mode(model: str, files: Optional[List[str]], prompt: str) -> None:
    messages: List[Dict[str, str]] = []
    if files:
        for fname in files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]
    messages.append({"role": "user", "content": prompt})

    final_answer, _ = process_request(model, messages, "default")
    print(final_answer)

def main() -> None:
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true", help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--diff", "-d", action="store_true", help="Enable diff output mode")
    parser.add_argument("--code-review", "-r", action="store_true", help="Enable code review mode")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enable interactive mode (only used with --diff, not with --code-review)")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    args = parser.parse_args()
    # Initialize colorama for cross-platform color support
    colorama.init()

    try:
        files_set = set(args.files) if args.files else set()

        if args.git_files:
            git_files = set(get_filtered_git_files())
            files_set.update(git_files)

        files_list = list(files_set) if files_set else None

        if args.code_review:
            if args.interactive:
                print("Warning: --interactive mode is not supported with --code-review. Ignoring --interactive flag.")
            code_review(args.model, files_list, args.prompt)
        elif args.diff:
            use_color = (args.color == "always") or (args.color == "auto" and is_output_to_terminal())
            diff_mode(args.model, files_list, args.prompt, use_color, args.interactive, args.debug)
        else:
            default_mode(args.model, files_list, args.prompt)

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

