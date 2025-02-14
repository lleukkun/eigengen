import pytest

from eigengen import operations, prompts, providers
from tests.fixtures.mock_provider import create_mock_model_pair


def test_mock_provider_default_mode(monkeypatch):
    # Create a MockProvider with custom canned responses
    custom_responses = {
        "Hello, world": "Hello! I'm a custom mock provider.",
        "What's the weather like?": "It's always sunny in the world of mock providers!",
    }

    def patch_create_model_pair(name: str):
        return create_mock_model_pair(custom_responses)

    monkeypatch.setattr(providers, "create_model_pair", patch_create_model_pair)

    # Test the default mode with a known prompt
    model_nick = "mock-model"
    prompt = "Hello, world"
    messages = [{"role": "user", "content": prompt}]
    model_pair = providers.create_model_pair(model_nick)
    final_answer = "".join(operations.process_request(model_pair.large, messages, prompts.PROMPTS["general"]))

    assert final_answer == "Hello! I'm a custom mock provider."


def test_mock_provider_unknown_prompt(monkeypatch):
    # Create a MockProvider with custom canned responses
    custom_responses = {
        "Hello, world": "Hello! I'm a custom mock provider.",
        "What's the weather like?": "It's always sunny in the world of mock providers!",
    }

    def patch_create_model_pair(name: str):
        return create_mock_model_pair(custom_responses)

    monkeypatch.setattr(providers, "create_model_pair", patch_create_model_pair)

    # Test the default mode with an unknown prompt
    model_nick = "mock-model"
    prompt = "What's the meaning of life?"
    messages = [{"role": "user", "content": prompt}]
    model_pair = providers.create_model_pair(model_nick)
    final_answer = "".join(operations.process_request(model_pair.large, messages, prompts.PROMPTS["general"]))

    assert final_answer == "I don't have a canned response for that prompt."


if __name__ == "__main__":
    pytest.main([__file__])
