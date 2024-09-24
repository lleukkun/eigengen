import pytest
from eigengen.providers import ModelConfig, MODEL_CONFIGS


@pytest.fixture(autouse=True)
def mock_model_config(monkeypatch):
    mock_config = ModelConfig("mock", "mock-model", 1000, 0.5)
    monkeypatch.setitem(MODEL_CONFIGS, "mock-model", mock_config)
    yield mock_config
    monkeypatch.delitem(MODEL_CONFIGS, "mock-model")


def pytest_addoption(parser):
    # Add a command-line option for enabling slow tests
    parser.addoption(
        "--enable-slow", action="store_true", default=False, help="Run slow tests"
    )

def pytest_collection_modifyitems(config, items):
    # Check if the --enable-slow option was given
    if config.getoption("--enable-slow"):
        # If --enable-slow is provided, do nothing (run all tests)
        return

    # Otherwise, skip tests marked as slow
    skip_slow = pytest.mark.skip(reason="Need --enable-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
