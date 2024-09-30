import os
import tempfile
import subprocess

from typing import List, Dict, Optional

from eigengen import operations, gitfiles, indexing


def code_review(model: str, git_files: Optional[List[str]], user_files: Optional[List[str]], messages: List[Dict[str, str]]) -> None:
    messages = messages.copy()
    # Add the final user message if not already present
    if not messages or messages[-1]["role"] == "assistant":
        messages.append({"role": "user", "content": "Please write the code that implements the discussed changes"})

    # Prepare context messages
    relevant_files = operations.get_context_aware_files(git_files, user_files)
    context_messages: List[Dict[str, str]] = []
    if relevant_files:
        project_root = gitfiles.find_git_root() if git_files else os.getcwd()
        with operations.open_fd(project_root, os.O_RDONLY) as dir_fd:
            for fname in relevant_files:
                with os.fdopen(os.open(fname, os.O_RDONLY, dir_fd=dir_fd), 'r') as f:
                    original_content = f.read()
                context_messages += [
                    {"role": "user", "content": operations.prompts.wrap_file(fname, original_content)},
                    {"role": "assistant", "content": "ok"}
                ]

    # Insert context messages before the conversation messages
    messages = context_messages + messages

    while True:
        review_messages: List[Dict[str, str]] = []
        is_first_round = True
        current_git_files = git_files
        while True:
            full_answer, _, diff, _ = operations.do_code_review_round(
                model, True if current_git_files else False, messages, review_messages, is_first_round
            )

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
                review_messages = [
                    {"role": "assistant", "content": diff},
                    {"role": "user", "content": review_content}
                ]
                is_first_round = False

        # After completing a review round, ask if the user wants to continue
        continue_review = input("\nDo you want to start a new code review cycle? (y/N): ").strip().lower()
        if continue_review != 'y':
            break

        # If continuing, re-prompt for a new review cycle
        print("\nStarting a new code review cycle.")
        new_prompt = get_prompt_from_editor_for_review() or ""
        if not new_prompt or new_prompt == "":
            break
        # Update messages with the new prompt
        messages.append({"role": "user", "content": new_prompt})
