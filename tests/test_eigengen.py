import pytest
from io import StringIO
import sys
from eigengen.eigengen import main

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
    assert "--model-alias" in captured.out
    assert "--files" in captured.out
    assert "--prompt" in captured.out
    assert "--diff" in captured.out
    assert "--interactive" in captured.out
    assert "--color" in captured.out
    assert "--debug" in captured.out
