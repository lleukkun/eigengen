from typing import Dict, List, Optional, Tuple
import tempfile
import os
import subprocess
import json

import difflib
import colorama

from eigengen import log, providers, utils, prompts, gitfiles, indexing
from eigengen.prompts import PROMPTS as PROMPTS


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


def apply_patch(diff: str, auto_apply: bool = False) -> None:
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp_diff_file:
        temp_diff_file_path = temp_diff_file.name
        temp_diff_file.write(diff)

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
    provider_instance: providers.Provider = providers.create_provider(model)
    model_config = providers.get_model_config(model)

    system: str = PROMPTS["system"]
    if mode == "default":
        system += PROMPTS["non_diff"]
    elif mode == "diff":
        system += PROMPTS["diff"]
    elif mode == "code_review":
        system += PROMPTS["code_review"]
    elif mode == "indexing":
        system += PROMPTS["indexing"]
    elif mode == "get_context":
        system += PROMPTS["get_context"]

    steering_messages = [ {"role": "user", "content": f"Your operating instructions are here:\n {system}"},
                          {"role": "assistant", "content": "Understood. I now have my operating instructions."} ]
    combined_messages = steering_messages + messages

    final_answer: str = provider_instance.make_request(combined_messages, model_config.max_tokens, model_config.temperature)
    new_files: Dict[str, str] = utils.extract_file_content(final_answer) if mode == "diff" or mode == "code_review" else {}

    # Log the request and response
    log.log_request_response(model, messages, mode, final_answer, new_files)

    return final_answer, new_files


def do_code_review_round(model: str, files: Optional[List[str]], user_files: Optional[List[str]], prompt: str,
                         review_messages: List[Dict[str, str]],
                         is_first_round: bool) -> Tuple[str, Dict[str, str], str, List[Dict[str, str]]]:
    system_prompt_mode = "diff" if is_first_round else "code_review"
    messages: List[Dict[str, str]] = []

    relevant_files = get_context_aware_files(files, user_files)

    if relevant_files:
        for fname in relevant_files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": prompts.wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]

    messages.append({"role": "user", "content": prompt})
    messages += review_messages

    full_answer, new_files = process_request(model, messages, system_prompt_mode)

    diff = ""
    for fname in new_files.keys():
        original_content = ""
        if relevant_files and fname in relevant_files:
            with open(fname, "r") as f:
                original_content = f.read()
        diff += generate_diff(original_content, new_files[fname], fname, False)

    return full_answer, new_files, diff, messages


def diff_mode(model: str, files: Optional[List[str]], user_files: Optional[List[str]], prompt: str, use_color: bool, debug: bool) -> None:
    messages: List[Dict[str, str]] = []
    relevant_files = get_context_aware_files(files, user_files)

    if relevant_files:
        for fname in relevant_files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": prompts.wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]
    messages.append({"role": "user", "content": prompt})

    _, new_files = process_request(model, messages, "diff")

    diff: str = ""
    if new_files:
        for fname in new_files.keys():
            original_content: str = ""
            if relevant_files and fname in relevant_files:
                with open(fname, "r") as f:
                    original_content = f.read()
            diff += generate_diff(original_content, new_files[fname], fname, use_color)
        if debug:
            print(diff)
    else:
        print("Error: Unable to generate diff. Make sure both original and new file contents are available.")


def default_mode(model: str, files: Optional[List[str]], user_files: Optional[List[str]], prompt: str) -> None:
    messages: List[Dict[str, str]] = []

    relevant_files = get_context_aware_files(files, user_files)

    if relevant_files:
        for fname in relevant_files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": prompts.wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]
    messages.append({"role": "user", "content": prompt})

    final_answer, _ = process_request(model, messages, "default")
    print(final_answer)


def get_file_list(use_git_files: bool=True, user_files: Optional[List[str]]=None) -> Tuple[List[str], List[str]]:
    file_set = set(user_files) if user_files else set()

    if use_git_files:
        git_files = set(gitfiles.get_filtered_git_files())
        file_set.update(git_files)

    file_list = list(file_set) if file_set else []
    return file_list


def get_locally_modified_git_files() -> List[str]:
    try:
        # Get staged files
        staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only']).decode().splitlines()
        # Get unstaged files
        unstaged = subprocess.check_output(['git', 'diff', '--name-only']).decode().splitlines()

        # Combine and remove duplicates
        modified_files = list(set(staged + unstaged))

        # Filter using .eigengen_ignore
        return gitfiles.get_filtered_files(modified_files)
    except subprocess.CalledProcessError:
        print("Error: Unable to get locally modified git files. Are you in a git repository?")
        return []


def get_context_aware_files(all_files: Optional[List[str]], user_files: Optional[List[str]]) -> List[str]:
    if not all_files:
        return user_files or []

    # Ensure user_files are always included
    user_files = user_files or []
    relevant_files = set(user_files)

    # Get locally modified git files
    local_modifications = get_locally_modified_git_files()
    relevant_files.update(local_modifications)

    # If there are no user_files and no local modifications, add default context
    if not user_files and not local_modifications:
        # Get default context (top-3 files with highest total_refcount)
        default_context = indexing.get_default_context(all_files)
        relevant_files.update(default_context)

    # Read the cache state
    cache_state = indexing.read_cache_state()

    # Find files that use symbols defined in the relevant files
    files_using_relevant_symbols = {}
    for file in relevant_files:
        if file in cache_state.entries:
            entry = cache_state.entries[file]
            for symbol in entry.provides:
                for using_file, using_entry in cache_state.entries.items():
                    if symbol in using_entry.uses and using_file not in relevant_files:
                        files_using_relevant_symbols[using_file] = files_using_relevant_symbols.get(using_file, 0) + 1

    # Sort files by relevance (number of used symbols) and take the top 5
    sorted_files = sorted(files_using_relevant_symbols.items(), key=lambda x: x[1], reverse=True)
    top_5_relevant_files = [file for file, _ in sorted_files[:5]]

    # Add the top 5 most relevant files to the relevant_files set
    relevant_files.update(top_5_relevant_files)

    print(f"relevant files: {relevant_files}")
    return list(relevant_files)

