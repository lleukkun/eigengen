from typing import Dict, List
from prompt_toolkit.key_binding import KeyBindings


class ChatKeyBindingsManager:
    def __init__(self, quoting_state: Dict, messages: List):
        super().__init__()
        self.kb = KeyBindings()
        self.quoting_state = quoting_state
        self.messages = messages

        self._register_bindings()

    def get_kb(self):
        return self.kb

    def _register_bindings(self):
        @self.kb.add("c-down")
        def _(event):
            # Get the last system response to process
            last_system_message = next((msg["content"] for msg in reversed(self.messages) if msg["role"] == "assistant"), "")

            if self.quoting_state["code_blocks"] is None:
                # Extract code blocks for the first time
                self.quoting_state["code_blocks"] = extract_code_blocks(last_system_message)
                self.quoting_state["cycle_iterator"] = cycle(quoting_state["code_blocks"]) if quoting_state["code_blocks"] else None

            if self.quoting_state["cycle_iterator"]:
                # There are code blocks, cycle through them
                block_to_quote = next(self.quoting_state["cycle_iterator"])
            else:
                # No code blocks, quote entire message
                block_to_quote = last_system_message

            # Prepend '> ' to each line in the block
            quoted_block = "\n".join(f"> {line}" for line in block_to_quote.splitlines())
            event.app.current_buffer.text = quoted_block

        @self.kb.add("c-j")
        def _(event):
            self.quoting_state["code_blocks"] = None
            self.quoting_state["cycle_iterator"] = None
            self.quoting_state["current_index"] = -1
            event.app.exit(result=event.app.current_buffer.text)

        @self.kb.add("enter")
        def _(event):
            if len(event.app.current_buffer.text) > 0 and event.app.current_buffer.text[0] == "/":
                event.app.exit(result=event.app.current_buffer.text)
            else:
                event.app.current_buffer.insert_text("\n")

        @self.kb.add("c-x", "e")
        def _(event):
            # Open current buffer content in external editor
            current_text = event.app.current_buffer.text
            new_text = get_prompt_from_editor_with_prefill(current_text)
            if new_text is not None:
                event.app.current_buffer.text = new_text

        @self.kb.add("c-x", "y")
        def _(event):
            # Copy the conversation to the system clipboard
            copy_messages = [msg for msg in self.messages if not (msg["role"] == "user" and msg["content"].startswith("<eigengen_file"))]
            conversation = "\n\n".join([f"[{'User' if msg['role'] == 'user' else 'System'}] [{datetime.now().strftime('%I:%M:%S %p')}]\n{msg['content']}" for msg in copy_messages])
            event.app.clipboard.set_text(conversation)
