import os
import tempfile
import subprocess
from typing import Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard

from eigengen import operations, code


def get_prompt_from_editor_with_prefill(prefill_content: str) -> Optional[str]:
    prompt_content = ""
    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(prefill_content)

    try:
        editor = os.environ.get("EDITOR", "nano")
        command = editor + " " + temp_file_path
        subprocess.run(command, shell=True, check=True)

        with open(temp_file_path, 'r') as file:
            prompt_content = file.read()

        return prompt_content
    finally:
        os.remove(temp_file_path)


def chat_mode(model: str, git_files: Optional[List[str]], user_files: Optional[List[str]]) -> None:

    messages: List[Dict[str, str]] = []

    # Implement the chat interface using prompt_toolkit
    kb = KeyBindings()

    @kb.add("c-j")
    def _(event):
        event.app.exit(result=event.app.current_buffer.text)

    @kb.add("enter")
    def _(event):
        if len(event.app.current_buffer.text) > 0 and event.app.current_buffer.text[0] == "/":
            event.app.exit(result=event.app.current_buffer.text)
        else:
            event.app.current_buffer.insert_text("\n")

    @kb.add("c-t")
    def _(event):
        # Open current buffer content in external editor
        current_text = event.app.current_buffer.text
        new_text = get_prompt_from_editor_with_prefill(current_text)
        if new_text is not None:
            event.app.current_buffer.text = new_text

    @kb.add("c-b")
    def _(event):
        nonlocal messages
        # Copy the conversation to the system clipboard
        copy_messages = [msg for msg in messages if not (msg["role"] == "user" and msg["content"].startswith("<eigengen_file"))]
        conversation = "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in copy_messages])
        event.app.clipboard.set_text(conversation)
        print("Conversation copied to clipboard.\n")

    session = PromptSession(key_bindings=kb, clipboard=PyperclipClipboard())
    print("Entering Chat Mode. Type '/help' for available commands.\n"
          "Ctrl-j submits your message.\n"
          "Ctrl-t opens prompt in $EDITOR.\n"
          "Ctrl-b copies conversation to clipboard.\n"
          "Type your messages below.\n(Type 'exit' to quit.)")
    relevant_files = operations.get_context_aware_files(git_files, user_files)

    if relevant_files:
        for fname in relevant_files:
            if os.path.exists(fname):
                with open(fname, 'r') as f:
                    content = f.read()
                messages.extend([
                    {"role": "user", "content": f"<eigengen_file name=\"{fname}\">\n{content}\n</eigengen_file>"},
                    {"role": "assistant", "content": "ok"}
                ])

    while True:
        try:
            prompt_input = session.prompt('You: ', multiline=True, enable_history_search=True)

            if prompt_input.startswith("/"):
                # input is supposed to be a command
                if prompt_input.strip() == '/help':
                    print("Available commands:\n"
                          "/attach <filename> - Load a file into context\n"
                          "/code [message]- Start code review flow with current conversation\n"
                          "/reset - Clear chat messages but keep file context\n"
                          "/help - Show this help message\n\n"
                          "Ctrl-j submits your message.\n"
                          "Ctrl-t opens prompt in $EDITOR\n"
                          "Ctrl-b copies conversation to clipboard\n")
                    continue

                if prompt_input.startswith('/attach '):
                    # Handle the /load command
                    file_to_load = prompt_input[len('/attach '):].strip()
                    if os.path.exists(file_to_load):
                        with open(file_to_load, 'r') as f:
                            content = f.read()
                        messages.extend([
                            {"role": "user", "content": f"<eigengen_file name=\"{file_to_load}\">\n{content}\n</eigengen_file>"},
                            {"role": "assistant", "content": "ok"}
                        ])
                        print(f"File '{file_to_load}' loaded into context.\n")
                    else:
                        print(f"File '{file_to_load}' not found.\n")
                    continue

                if prompt_input.startswith("/code "):
                    supplementary = prompt_input[6:].strip()
                    if supplementary == "":
                        supplementary = "Please write the code that implements the discussed changes, thank you!"
                    messages += [{"role": "user", "content": supplementary}]
                    # Initiate code_review flow with current messages
                    code.code_review(model, [], None, messages)
                    continue

                if prompt_input.strip() == '/reset':
                    # Reset the session messages, maintaining file contexts
                    messages = [msg for msg in messages if msg["role"] == "user" and msg["content"].startswith("<eigengen_file")]
                    print("Chat messages cleared, existing file context retained.\n")
                    continue
            if prompt_input.strip().lower() == 'exit':
                break
            if prompt_input.strip() == '':
                continue

            # Process the user's input
            prompt = prompt_input

            messages.append({"role": "user", "content": prompt})

            answer, _ = operations.process_request(model, messages, "chat")
            print("")
            messages.append({"role": "assistant", "content": answer})

        except KeyboardInterrupt:
            # Handle Ctrl+C to cancel the current input
            continue
        except EOFError:
            # Handle Ctrl+D to exit
            break

