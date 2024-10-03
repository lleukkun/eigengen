import os
import tempfile
import subprocess
from typing import Dict, List, Optional
from datetime import datetime
from itertools import cycle

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from colorama import Fore, Style as ColoramaStyle

from eigengen import operations, utils


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

    # Maintain current quoting state
    quoting_state = {
        "current_index": -1,
        "code_blocks": None,
        "cycle_iterator": None
    }

    # Function to extract code blocks from a response
    def extract_code_blocks(response: str) -> List[str]:
        code_blocks = []
        lines = response.splitlines()
        in_block = False
        block_content = []
        for line in lines:
            if line.strip().startswith("```"):
                if not in_block:
                    in_block = True
                else:
                    # Closing block, add to list and reset
                    in_block = False
                    code_blocks.append("\n".join(block_content))
                    block_content = []
            elif in_block:
                block_content.append(line)
        return code_blocks

    @kb.add("c-q")
    def _(event):
        nonlocal quoting_state
        # Get the last system message to process
        last_system_message = next((msg["content"] for msg in reversed(messages) if msg["role"] == "assistant"), "")

        if quoting_state["code_blocks"] is None:
            # Extract code blocks for the first time
            quoting_state["code_blocks"] = extract_code_blocks(last_system_message)
            quoting_state["cycle_iterator"] = cycle(quoting_state["code_blocks"]) if quoting_state["code_blocks"] else None

        if quoting_state["cycle_iterator"]:
            # There are code blocks, cycle through them
            block_to_quote = next(quoting_state["cycle_iterator"])
        else:
            # No code blocks, quote entire message
            block_to_quote = last_system_message

        # Prepend '> ' to each line in the block
        quoted_block = "\n".join(f"> {line}" for line in block_to_quote.splitlines())
        event.app.current_buffer.text = quoted_block

    @kb.add("c-j")
    def _(event):
        quoting_state["code_blocks"] = None
        quoting_state["cycle_iterator"] = None
        quoting_state["current_index"] = -1
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
        conversation = "\n\n".join([f"[{'User' if msg['role'] == 'user' else 'System'}] [{datetime.now().strftime('%I:%M:%S %p')}]\n{msg['content']}" for msg in copy_messages])
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
            style = Style.from_dict({
                "user": "ansicyan",
                "system": "blue"
            })
            def custom_prompt():
                return [("class:user", f"\n[User][{datetime.now().strftime('%I:%M:%S %p')}]\n")]

            prompt_input = session.prompt(custom_prompt, style=style, multiline=True, enable_history_search=True, refresh_interval=5)

            if prompt_input.startswith("/"):
                # input is supposed to be a command
                if prompt_input.strip() == '/help':
                    print("Available commands:\n"
                          "/attach <filename> - Load a file into context\n"
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
                            {"role": "user", "content": utils.encode_code_block(content, file_to_load)},
                            {"role": "assistant", "content": "ok"}
                        ])
                        print(f"File '{file_to_load}' loaded into context.\n")
                    else:
                        print(f"File '{file_to_load}' not found.\n")
                    continue

                if prompt_input.strip() == '/reset':
                    # Reset the session messages, maintaining file contexts
                    messages = [msg for msg in messages if msg["role"] == "user" and msg["content"].startswith("```")]
                    print("Chat messages cleared, existing file context retained.\n")
                    continue
            if prompt_input.strip().lower() == 'exit':
                break
            if prompt_input.strip() == '':
                continue

            # Process the user's input
            prompt = prompt_input

            messages.append({"role": "user", "content": prompt})

            answer = ""

            chunk_iterator = operations.process_request(model, messages, "chat")
            try:
                # Get the first chunk
                first_chunk = next(chunk_iterator)
                # Capture the timestamp after receiving the first chunk
                timestamp = datetime.now().strftime('%I:%M:%S %p')
                # Print the timestamp before the first chunk
                print(Fore.GREEN + f"\n[System] [{timestamp}]" + ColoramaStyle.RESET_ALL)
                # Print the first chunk
                print(first_chunk, end="", flush=True)
                answer += first_chunk
            except StopIteration:
                # No content generated
                continue

            # Continue with the remaining chunks
            for chunk in chunk_iterator:
                print(chunk, end="", flush=True)
                answer += chunk

            print("")
            messages.append({"role": "assistant", "content": answer})

        except KeyboardInterrupt:
            # Handle Ctrl+C to cancel the current input
            continue
        except EOFError:
            # Handle Ctrl+D to exit
            break
