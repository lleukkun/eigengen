from typing import Dict, List, Tuple, Optional
import re
import tempfile
import subprocess
import os


def encode_code_block(code_content, file_path=''):
    """
    Encapsulates the code content in a Markdown code block,
    using three backticks and including the file path after the backticks in both fences.
    """
    # Find all sequences of backticks in the code content
    backtick_sequences = re.findall(r'`+', code_content)
    if backtick_sequences:
        # Determine the maximum length of backtick sequences
        max_backticks = max(len(seq) for seq in backtick_sequences)
        # Fence length is one more than the maximum found, minimum of 3
        fence_length = max(max_backticks + 1, 3)
    else:
        # Default fence length
        fence_length = 3

    # Create the fence using the calculated fence length
    fence = '`' * fence_length
    opening_fence = f"{fence}{file_path}"
    closing_fence = fence

    return f"{opening_fence}\n{code_content}\n{closing_fence}"


# Function to extract code blocks from a response
def extract_code_blocks(response: str) -> List[Tuple[str, str, str, str, int, int]]:
    code_blocks = []

    # Regular expression pattern to match code blocks with variable-length fences and indentation
    code_block_pattern = re.compile(
        r'^(?P<indent>[ \t]*)'          # Leading indentation
        r'(?P<fence>`{3,}|~{3,})'       # Code fence (at least 3 backticks or tildes)
        r'[ \t]*(?P<lang_path>\S+)?'    # Optional language identifier and/or file path
        r'[ \t]*\n'                     # Trailing spaces and newline
        r'(?P<code>.*?)'                # Code content
        r'\n'                           # Newline before the closing fence
        r'(?P=indent)'                  # Matching indentation
        r'(?P=fence)'                   # Closing fence matching the opening
        r'[ \t]*\n?',                   # Trailing spaces and optional newline
        re.DOTALL | re.MULTILINE
    )

    for match in code_block_pattern.finditer(response):
        fence = match.group('fence')
        lang_path = match.group('lang_path') or ""
        code = match.group('code')
        start_index = match.start()
        end_index = match.end()

        # Split the language and path if both are provided
        actual_lang = ""
        actual_path = ""
        if lang_path:
            lang_parts = lang_path.split(";")
            actual_lang = lang_parts[0]
            if len(lang_parts) > 1:
                actual_path = lang_parts[1]

        code_blocks.append((fence, actual_lang, actual_path, code, start_index, end_index))

    return code_blocks


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
