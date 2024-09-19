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


def do_code_review_round(model: str, files: Optional[List[str]], prompt: str,
                         review_messages: List[Dict[str, str]],
                         is_first_round: bool) -> Tuple[str, Dict[str, str], str, List[Dict[str, str]]]:
    system_prompt_mode = "diff" if is_first_round else "code_review"
    messages: List[Dict[str, str]] = []

    relevant_files = get_context_aware_files(model, prompt, files)

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


def diff_mode(model: str, files: Optional[List[str]], prompt: str, use_color: bool, debug: bool) -> None:
    messages: List[Dict[str, str]] = []
    relevant_files = get_context_aware_files(model, prompt, files)

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


def default_mode(model: str, files: Optional[List[str]], prompt: str) -> None:
    messages: List[Dict[str, str]] = []

    # Get context-aware file selection
    relevant_files = get_context_aware_files(model, prompt, files)

    if relevant_files:
        for fname in relevant_files:
            with open(fname, "r") as f:
                original_content = f.read()
            messages += [{"role": "user", "content": prompts.wrap_file(fname, original_content)},
                         {"role": "assistant", "content": "ok"}]
    messages.append({"role": "user", "content": prompt})

    final_answer, _ = process_request(model, messages, "default")
    print(final_answer)


def get_file_list(use_git_files: bool=True, extra_files: List[str]=[]) -> List[str]:
    file_set = set(extra_files) if extra_files else set()

    if use_git_files:
        git_files = set(gitfiles.get_filtered_git_files())
        file_set.update(git_files)

    file_list = list(file_set) if file_set else []
    return file_list


def index_files_mode(model: str, files: List[str]) -> None:
    indexing.index_files(files)
    print(f"Indexed {len(files)} files.")


def get_context_aware_files(model: str, prompt: str, all_files: Optional[List[str]]) -> List[str]:
    if not all_files:
        return []

    # Check if the cache directory exists
    if not os.path.exists(indexing.CACHE_DIR):
        print("Cache directory doesn't exist. Returning all files without filtering.")
        return all_files

    # Use whatever summaries are available in the cache
    available_summaries = indexing.get_summaries(all_files)
    if not available_summaries:
        print("No summaries available in the cache. Returning all files without filtering.")
        return all_files

    all_summaries = json.dumps(available_summaries, indent=2)
    messages = [
        {"role": "user", "content": f"<eigengen_file name=\"summaries\">\n{all_summaries}\n</eigengen_file>"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": f"Based on the following prompt, list the relevant files:\n{prompt}"}
    ]

    relevant_files, _ = process_request(model, messages, "get_context")
    relevant_files_list = [file.strip() for file in relevant_files.split('\n') if file.strip()]
    print(f"All files: {all_files}")
    print(f"Relevant files: {relevant_files_list}")
    return [file for file in relevant_files_list if file in all_files]

