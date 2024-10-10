import os
from typing import Dict, List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard

from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles.pygments import style_from_pygments_cls
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.token import Token
from pygments.styles import get_style_by_name

import pygments.style

from colorama import Fore, Style as ColoramaStyle

from eigengen import operations, utils, keybindings, meld
from eigengen.progress import ProgressIndicator  # Added import


class CustomStyle(pygments.style.Style):
    default_style = ""
    styles = {
        Token.Keyword: 'ansigreen',
        Token.String: 'ansiyellow',
        Token.Comment: 'ansiblue',
        Token.Name: '',
        # Add more token styles as desired
    }


def display_response_with_syntax_highlighting(response: str) -> None:
    """
    Displays the response with syntax-highlighted code blocks,
    utilizing the extract_code_blocks function from utils.py to parse code blocks.
    """
    last_end = 0

    # Extract code blocks along with their positions and fences
    code_blocks = utils.extract_code_blocks(response)

    for fence, actual_lang, actual_path, code, start, end in code_blocks:
        # Print text before the code block
        print(response[last_end:start], end='')

        # Reconstruct the opening fence with optional language and path
        lang_path = ';'.join(filter(None, [actual_lang, actual_path]))
        print(f"{fence}{lang_path}")

        # Determine the lexer to use for syntax highlighting
        if actual_lang:
            try:
                lexer = get_lexer_by_name(actual_lang.lower())
            except Exception:
                lexer = guess_lexer(code)
        else:
            try:
                lexer = guess_lexer(code)
            except Exception:
                lexer = TextLexer()

        # Syntax-highlight the code content
        tokens = list(pygments.lex(code, lexer=lexer))
        formatted_code = PygmentsTokens(tokens)
        print_formatted_text(formatted_code, end='',
                             style=style_from_pygments_cls(get_style_by_name("solarized-dark")))

        # Print the closing fence
        print(f"\n{fence}")

        last_end = end

    # Print any remaining text after the last code block
    print(response[last_end:], end='')


CHAT_HELP = (
    "Available commands:\n\n"
    "/help  Print this help text\n"
    "/attach <path>  Attach file to context.\n"
    "/quote <path>  Read and quote a file into the buffer.\n"
    "/clear  Clears messages from context. Leaves files intact.\n"
    "/meld [<path1>, ...]  Merge changes from the latest assistant message to the given paths. "
    "If no paths are provided, applies changes to all files with code blocks in the latest assistant message.\n"
    "/reset  Clears messages and files from context.\n"
    "/exit  Exits chat.\n"
    "Ctrl-j  submits your message.\n"
    "Ctrl-x e  opens prompt in $EDITOR.\n"
    "Ctrl-x y  copies conversation to clipboard.\n"
    "Ctrl-x Up  cycles through response code blocks and quotes them in the buffer.\n"
)


class EggChat:
    def __init__(self):
        super().__init__()

        self.quoting_state = {
            "current_index": -1,
            "code_blocks": None,
            "cycle_iterator": None
        }

        self.messages: List[Dict[str, str]] = []
        self.file_context_indices: List[int] = []  # New attribute to track file context message indices
        self.attached_files: List[str] = []  # List to track attached files

        self.kbm = keybindings.ChatKeyBindingsManager(self.quoting_state, self.messages)

    def chat_mode(
        self,
        model: str,
        git_files: Optional[List[str]],
        user_files: Optional[List[str]],
        initial_prompt: Optional[str] = None
    ) -> None:

        session = PromptSession(key_bindings=self.kbm.get_kb(), clipboard=PyperclipClipboard())
        print(
            "Entering Chat Mode. Type '/help' for available commands.\n"
            "Type your messages below.\n(Type '/exit' to quit.)"
        )
        relevant_files = operations.get_context_aware_files(git_files, user_files)

        if relevant_files:
            for fname in relevant_files:
                if os.path.exists(fname):
                    with open(fname, 'r') as f:
                        content = f.read()
                    # Record the starting index
                    start_index = len(self.messages)
                    self.messages.extend([
                        {"role": "user", "content": utils.encode_code_block(content, fname)},
                        {"role": "assistant", "content": "ok"}
                    ])
                    # Record the indices of the file context messages
                    self.file_context_indices.extend([start_index, start_index + 1])
                    # Add the file to the list of attached files
                    self.attached_files.append(fname)

        pre_fill = initial_prompt
        while True:
            try:
                # Refresh the file context messages before processing user input
                self.refresh_file_context_messages()

                style = Style.from_dict({
                    "user": "ansicyan",
                    "assistant": "blue"
                })

                def custom_prompt():
                    return [("class:user", f"\n[User][{datetime.now().strftime('%I:%M:%S %p')}] >\n")]

                prompt_input = session.prompt(
                    custom_prompt,
                    style=style,
                    multiline=True,
                    enable_history_search=True,
                    refresh_interval=5,
                    default=pre_fill or ""
                )
                pre_fill = ""  # Reset pre_fill after use

                if prompt_input.startswith("/"):
                    # Input is a command
                    if prompt_input.strip() == '/help':
                        print(CHAT_HELP)
                        continue

                    elif prompt_input.startswith('/attach '):
                        # Handle the /attach command
                        file_to_load = prompt_input[len('/attach '):].strip()
                        if os.path.exists(file_to_load):
                            with open(file_to_load, 'r') as f:
                                content = f.read()
                            # Record the starting index
                            start_index = len(self.messages)
                            self.messages.extend([
                                {"role": "user", "content": utils.encode_code_block(content, file_to_load)},
                                {"role": "assistant", "content": "ok"}
                            ])
                            # Record the indices of the file context messages
                            self.file_context_indices.extend([start_index, start_index + 1])
                            # Add the file to the list of attached files
                            self.attached_files.append(file_to_load)
                            print(f"File '{file_to_load}' loaded into context.\n")
                        else:
                            print(f"File '{file_to_load}' not found.\n")
                        continue

                    elif prompt_input.startswith('/quote '):
                        # Handle the '/quote' command
                        file_to_quote = prompt_input[len('/quote '):].strip()
                        if os.path.exists(file_to_quote):
                            with open(file_to_quote, 'r') as f:
                                content = f.read()
                            # Prefix each line with '> '
                            quoted_content = '\n'.join(f'> {line}' for line in content.splitlines())
                            pre_fill = quoted_content  # Pre-fill the next prompt with quoted content
                            continue
                        else:
                            print(f"File '{file_to_quote}' not found.\n")
                            continue

                    elif prompt_input.strip() == '/clear':
                        # Clears messages from context, leaves files intact
                        # Retain messages whose indices are in self.file_context_indices
                        self.messages = [
                            msg for idx, msg in enumerate(self.messages)
                            if idx in self.file_context_indices
                        ]
                        print("Chat messages cleared, existing file context retained.\n")
                        continue

                    elif prompt_input.strip() == '/reset':
                        # Clears messages and files from context
                        self.messages = []
                        self.file_context_indices = []  # Clear the file context indices
                        self.attached_files = []        # Clear the list of attached files
                        print("Chat messages and file context cleared.\n")
                        continue

                    elif prompt_input.startswith("/meld"):
                        # Handle the /meld command
                        paths_input = prompt_input[len("/meld"):].strip()
                        last_assistant_message = next(
                            (msg["content"] for msg in reversed(self.messages) if msg["role"] == "assistant"), ""
                        )

                        if not paths_input:
                            # No paths provided, extract file paths from the last assistant message's code blocks
                            code_blocks = utils.extract_code_blocks(last_assistant_message)
                            paths = set()
                            for fence, lang, path, code, start, end in code_blocks:
                                if path:
                                    paths.add(path)
                            if not paths:
                                print("No file paths found in the latest assistant message.\n")
                                continue
                        else:
                            paths = set(paths_input.split())

                        for filepath in paths:
                            meld.meld_changes(model, filepath, last_assistant_message)

                        # Refresh file contents in the chat context
                        self.refresh_file_context_messages()
                        continue

                    elif prompt_input.strip().lower() == '/exit':
                        break

                    else:
                        print(f"Unknown command: {prompt_input}\n")
                        continue

                if prompt_input.strip() == '':
                    continue

                # Process the user's input
                prompt = prompt_input

                self.messages.append({"role": "user", "content": prompt})

                answer = ""

                # Initialize and start the progress indicator
                indicator = ProgressIndicator()
                indicator.start()

                chunk_iterator = operations.process_request(model, self.messages, "chat")
                for chunk in chunk_iterator:
                    answer += chunk

                # Stop the progress indicator after response is complete
                indicator.stop()

                # print assistant response heading + timestamp
                timestamp = datetime.now().strftime('%I:%M:%S %p')
                print(Fore.GREEN + f"\n[Assistant][{timestamp}] >" + ColoramaStyle.RESET_ALL)

                display_response_with_syntax_highlighting(answer)
                print("")  # empty line to create a bit of separation
                
                self.messages.append({"role": "assistant", "content": answer})

            except KeyboardInterrupt:
                # Handle Ctrl+C to cancel the current input
                pre_fill = ""  # Reset pre_fill after Ctrl-C
                continue
            except EOFError:
                # Handle Ctrl+D to exit
                break

    def refresh_file_context_messages(self) -> None:
        """
        Refreshes all file content messages in the chat context.
        """
        # Create a mapping from file path to content
        file_contents = {}
        for filepath in self.attached_files:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = f.read()
                file_contents[filepath] = utils.encode_code_block(content, filepath)
            else:
                print(f"File '{filepath}' not found. Skipping refresh for this file.\n")

        # Update the messages in self.messages at the recorded indices
        for index in range(0, len(self.file_context_indices), 2):
            user_msg_index = self.file_context_indices[index]
            user_msg = self.messages[user_msg_index]
            # Extract the file path from the message content
            parsed_code_blocks = utils.extract_code_blocks(user_msg["content"])
            if parsed_code_blocks:
                _, _, path, _, _, _ = parsed_code_blocks[0]
                if path in file_contents:
                    # Update the user message with the new file content
                    self.messages[user_msg_index]["content"] = file_contents[path]
