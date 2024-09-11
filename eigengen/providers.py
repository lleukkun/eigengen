from abc import ABC, abstractmethod
import requests
import json
import time
import random
from typing import List, Dict, Any, Optional, Union

from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError
from groq import Groq, RateLimitError as GroqRateLimitError
from openai import OpenAI, RateLimitError as OpenAIRateLimitError

OLLAMA_BASE_URL: str = "http://localhost:11434"

class Provider(ABC):
    @abstractmethod
    def make_request(self, system_prompt: str, messages: List[Dict[str, str]],
                     temperature: float = 0.7) -> str:
        pass

class OllamaProvider(Provider):
    def __init__(self, model: str = "llama3.1:latest"):
        self.model: str = model

    def make_request(self, system_prompt: str, messages: List[Dict[str, str]],
                     temperature: float = 0.7) -> str:
        full_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}] + messages
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        data: Dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "max_tokens": 128000
            }
        }
        response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", headers=headers, data=json.dumps(data))
        return response.json()["message"]["content"]

class AnthropicProvider(Provider):
    def __init__(self, client: Anthropic, model: str = "claude-3-haiku-20240307"):
        self.client: Anthropic = client
        self.model: str = model

    def make_request(self, system_prompt: str, messages: List[Dict[str, str]],
                     temperature: float = 0.7, max_retries: int = 5, base_delay: int = 1) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8000,
                    temperature=temperature,
                    system=system_prompt,
                    messages=messages
                )
                return response.content[0].text
            except AnthropicRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class GroqProvider(Provider):
    def __init__(self, client: Groq, model: str = "llama-3.1-70b-versatile"):
        self.client: Groq = client
        self.model: str = model

    def make_request(self, system_prompt: str, messages: List[Dict[str, str]],
                     temperature: float = 0.7, max_retries: int = 5, base_delay: int = 1) -> str:
        full_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}] + messages
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=full_messages,
                    model=self.model,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except GroqRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class OpenAIProvider(Provider):
    def __init__(self, client: OpenAI, model: str = "gpt-4-0613"):
        self.client: OpenAI = client
        self.model: str = model

    def make_request(self, system_prompt: str, messages: List[Dict[str, str]],
                     temperature: float = 0.7, max_retries: int = 5, base_delay: int = 1) -> str:
        full_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}] + messages
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except OpenAIRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

def create_provider(provider: str, model: str, client: Optional[Union[Anthropic, Groq, OpenAI]] = None) -> Provider:
    if provider == "ollama":
        return OllamaProvider(model)
    elif provider == "anthropic":
        if not isinstance(client, Anthropic):
            raise ValueError("Invalid client type for Anthropic provider")
        return AnthropicProvider(client, model)
    elif provider == "groq":
        if not isinstance(client, Groq):
            raise ValueError("Invalid client type for Groq provider")
        return GroqProvider(client, model)
    elif provider == "openai":
        if not isinstance(client, OpenAI):
            raise ValueError("Invalid client type for OpenAI provider")
        return OpenAIProvider(client, model)
    else:
        raise ValueError("Invalid provider specified. Choose 'ollama', 'anthropic', 'groq', or 'openai'.")
