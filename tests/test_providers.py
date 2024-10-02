import pytest
from typing import List, Dict
from eigengen import operations, providers
from tests.fixtures.mock_provider import MockProvider

def test_mock_provider_default_mode(monkeypatch):
    # Create a MockProvider with custom canned responses
    custom_responses = {
        "Hello, world": "Hello! I'm a custom mock provider.",
        "What's the weather like?": "It's always sunny in the world of mock providers!",
    }

    # Mock the create_provider function to return our MockProvider with custom responses
    def mock_create_provider(model: str) -> providers.Provider:
        return MockProvider(custom_responses)

    monkeypatch.setattr(providers, 'create_provider', mock_create_provider)

    # Test the default mode with a known prompt
    model = "mock-model"
    prompt = "Hello, world"
    messages = [{"role": "user", "content": prompt}]

    final_answer = "".join(operations.process_request(model, messages, "default"))

    assert final_answer == "Hello! I'm a custom mock provider."

def test_mock_provider_unknown_prompt(monkeypatch):
    # Create a MockProvider with custom canned responses
    custom_responses = {
        "Hello, world": "Hello! I'm a custom mock provider.",
        "What's the weather like?": "It's always sunny in the world of mock providers!",
    }

    # Mock the create_provider function to return our MockProvider with custom responses
    def mock_create_provider(model: str) -> providers.Provider:
        return MockProvider(custom_responses)

    monkeypatch.setattr(providers, 'create_provider', mock_create_provider)

    # Test the default mode with an unknown prompt
    model = "mock-model"
    prompt = "What's the meaning of life?"
    messages = [{"role": "user", "content": prompt}]

    final_answer = "".join(operations.process_request(model, messages, "default"))

    assert final_answer == "I don't have a canned response for that prompt."

if __name__ == "__main__":
    pytest.main([__file__])
