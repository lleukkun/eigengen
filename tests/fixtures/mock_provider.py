from typing import List, Dict
from eigengen.providers import Provider

class MockProvider(Provider):
    def __init__(self, canned_responses=None):
        self.canned_responses = canned_responses or {
            "Hello, world": "Hello! I'm a mock provider.",
            "What is your name?": "My name is MockProvider.",
            "Tell me a joke": "Why don't scientists trust atoms? Because they make up everything!",
        }

    def make_request(self, messages: List[Dict[str, str]], max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> str:
        last_user_message = next((msg['content'] for msg in reversed(messages) if msg['role'] == 'user'), '')
        response = self.canned_responses.get(last_user_message, "I don't have a canned response for that prompt.")
        if mode in ["default", "code_review_start", "code_review_continue"]:
            print(response)
        return response
