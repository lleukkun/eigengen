from typing import Dict
import re


def extract_file_content(output: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    index = 0
    output_length = len(output)

    while index < output_length:
        # Search for the next code block starting from the current index
        fence_pattern = r'(`{3,})([^\n]*)\n'
        fence_regex = re.compile(fence_pattern)
        fence_match = fence_regex.search(output, index)

        if not fence_match:
            break  # No more code blocks found

        # Update the index to the start of the found code block
        index = fence_match.start()

        try:
            code_block_content, file_path, next_index = decode_code_block(output, index)
            index = next_index  # Move index to the end of the current code block

            if file_path:
                # Strip trailing whitespace from each line
                code_content_lines = [line.rstrip() for line in code_block_content.splitlines()]
                code_content = "\n".join(code_content_lines) + "\n"
                files[file_path] = code_content
        except ValueError:
            # If decoding fails, skip past the current fence to avoid an infinite loop
            index = fence_match.end()

    return files



def encode_code_block(code_content, file_path=''):
    """
    Encapsulates the code content in a Markdown code block,
    using an appropriate number of backticks to avoid conflicts.
    Optionally includes a file path after the opening backticks.
    """
    # Find the maximum number of consecutive backticks in the code content

    backtick_sequences = re.findall(r'`+', code_content)
    if backtick_sequences:
        max_backticks = max(len(seq) for seq in backtick_sequences)
    else:
        max_backticks = 0

    # Use one more backtick for fencing
    fence = '`' * (max_backticks + 1)

    # Prepare the opening line with file path if provided
    if file_path:
        opening_line = f"{fence}{file_path}\n"
    else:
        opening_line = f"{fence}\n"

    return f"{opening_line}{code_content}\n{fence}"

def decode_code_block(markdown_text, start_index=0):
    """
    Decodes a Markdown code block starting from start_index.
    Returns a tuple of (code_block_content, file_path, index_after_code_block_end).
    """

    # Find the opening fence and file path
    fence_pattern = r'(`{3,})([^\n]*)\n'
    fence_regex = re.compile(fence_pattern)
    fence_match = fence_regex.match(markdown_text, start_index)
    if not fence_match:
        raise ValueError("No code block found at the specified start_index.")

    opening_fence = fence_match.group(1)
    fence_length = len(opening_fence)
    file_path = fence_match.group(2).strip()
    code_start = fence_match.end()

    # Prepare the closing fence pattern
    closing_fence_pattern = rf'(^|\n)(`{{{fence_length}}})\s*(\n|$)'
    closing_fence_regex = re.compile(closing_fence_pattern, re.MULTILINE)

    # Search for the closing fence
    closing_fence_match = closing_fence_regex.search(markdown_text, code_start)
    if not closing_fence_match:
        raise ValueError("Closing fence not found for the code block.")

    code_end = closing_fence_match.start()
    code_block_content = markdown_text[code_start:code_end]

    # Index after the closing fence
    index_after_code_block_end = closing_fence_match.end()

    return code_block_content, file_path, index_after_code_block_end
