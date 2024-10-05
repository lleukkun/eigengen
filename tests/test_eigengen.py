import pytest
import sys
import os
from eigengen.eigengen import main
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
    assert "--color" in captured.out
    assert "--chat" in captured.out
    assert "--git-files" in captured.out
    assert "--list-history" in captured.out


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_claude_sonnet_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "claude-sonnet",
        "--prompt", "This is part of a system test. You must write on a separate line as the only content: Hello, world.\nYou must not write anything after that."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-1] == 'Hello, world.'

@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_gpt4_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "gpt4",
        "--prompt", "This is part of a system test. You must write on a separate line as the only content: Hello, world.\nYou must not write anything after that."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-1] == 'Hello, world.'

@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), reason="GROQ_API_KEY not set")
def test_groq_hello_world(capsys, monkeypatch):
    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "groq",
        "--prompt", "This is part of a system test. You must write on a separate line as the only content: Hello, world.\nYou must not write anything after that."
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Split the output into lines and remove empty lines
    output_lines = [line.strip() for line in captured.out.split('\n') if line.strip()]

    # Check if the last non-empty line is exactly 'hello, world.'
    assert output_lines[-1] == 'Hello, world.'


def test_mock_model(capsys, monkeypatch, mock_model_config):
    from tests.fixtures.mock_provider import MockProvider

    # Patch the create_provider function to return our MockProvider
    def mock_create_provider(model: str):
        return MockProvider()

    monkeypatch.setattr('eigengen.providers.create_provider', mock_create_provider)

    # Simulate command-line arguments
    monkeypatch.setattr(sys, 'argv', [
        "eigengen",
        "--model", "mock-model",
        "--prompt", "Hello, world"
    ])

    # Call the main function
    main()

    # Capture the output
    captured = capsys.readouterr()

    # Check if the output matches the expected response from MockProvider
    assert "Hello! I'm a mock provider." in captured.out

