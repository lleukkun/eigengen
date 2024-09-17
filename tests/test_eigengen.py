import pytest
from io import StringIO
import sys
import os
from eigengen.eigengen import main
from eigengen.operations import generate_diff
import re

def test_main_prints_help(capsys):
    # Simulate command-line arguments
    sys.argv = ["eigengen", "--help"]

    # Call the main function
    with pytest.raises(SystemExit):
        main()

    # Capture the output
    captured = capsys.readouterr()

    # Check if help text is in the output
    assert "usage: eigengen" in captured.out
    assert "--model" in captured.out
    assert "-m" in captured.out
    assert "--files" in captured.out
    assert "--prompt" in captured.out
    assert "--diff" in captured.out
    assert "--color" in captured.out
    assert "--debug" in captured.out
    assert "--git-files" in captured.out
    assert "--code-review" in captured.out
    assert "--list-history" in captured.out
    assert "--web" in captured.out


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_claude_sonnet_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "claude-sonnet",
        "--prompt", "This is part of a system test. Write 'Hello, world.' as the only output."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-2] == 'Hello, world.'

@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_gpt4_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "gpt4",
        "--prompt", "This is part of a system test. Write 'Hello, world.' as the only output."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-2] == 'Hello, world.'

@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), reason="GROQ_API_KEY not set")
def test_groq_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "groq",
        "--prompt", "This is part of a system test. Write 'Hello, world.' as the only output."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-2] == 'Hello, world.'

def test_generate_diff():
    original_content = """This is a test file.
It has multiple lines.
Some lines will be changed.
Others will remain the same.
This line will be removed.
"""

    new_content = """This is a test file.
It has multiple lines.
Some lines have been modified.
Others will remain the same.
This is a new line.
"""

    file_name = "test_file.txt"

    # Test colored diff
    colored_diff = generate_diff(original_content, new_content, file_name, use_color=True)

    assert "--- a/test_file.txt" in colored_diff
    assert "+++ b/test_file.txt" in colored_diff
    assert "-Some lines will be changed." in colored_diff
    assert "+Some lines have been modified." in colored_diff
    assert "-This line will be removed." in colored_diff
    assert "+This is a new line." in colored_diff

    # Check for color codes
    assert re.search(r'\x1b\[\d+m', colored_diff) is not None

    # Test non-colored diff
    non_colored_diff = generate_diff(original_content, new_content, file_name, use_color=False)

    assert "--- a/test_file.txt" in non_colored_diff
    assert "+++ b/test_file.txt" in non_colored_diff
    assert "-Some lines will be changed." in non_colored_diff
    assert "+Some lines have been modified." in non_colored_diff
    assert "-This line will be removed." in non_colored_diff
    assert "+This is a new line." in non_colored_diff

    # Check that there are no color codes
    assert re.search(r'\x1b\[\d+m', non_colored_diff) is None

