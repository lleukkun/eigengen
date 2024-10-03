from abc import ABC, abstractmethod
import requests
import json
import time
import random
import os
from typing import List, Dict, Any, Optional, Union, Generator

from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError
from groq import Groq, RateLimitError as GroqRateLimitError
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
import google.generativeai as google_genai
from mistralai import Mistral

OLLAMA_BASE_URL: str = "http://localhost:11434"

class ModelConfig:
    def __init__(self, provider: str, model: str, chat_model: str, max_tokens: int, temperature: float):
        self.provider = provider
        self.model = model
        self.chat_model = chat_model
        self.max_tokens = max_tokens
        self.temperature = temperature

MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "claude-sonnet": ModelConfig("anthropic", "claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20240620", 8192, 0.7),
    "gemma2": ModelConfig("ollama", "gemma2:27b", "gemma2:27b", 128000, 0.5),
    "groq": ModelConfig("groq", "llama-3.2-90b-text-preview", "llama-3.2-90b-text-preview", 8000, 0.5),
    "gpt4": ModelConfig("openai", "gpt-4o-2024-08-06", "gpt-4o-2024-08-06", 128000, 0.7),
    "o1-preview": ModelConfig("openai", "o1-preview", "o1-preview", 8000, 0.7),
    "o1-mini": ModelConfig("openai", "o1-mini", "o1-mini", 4000, 0.7),
    "gemini": ModelConfig("google", "gemini-1.5-pro-002", "gemini-1.5-pro-002", 32768, 0.7),
    "mistral": ModelConfig("mistral", "mistral-large-2407", "mistral-large-2407", 8192, 0.7)

}

class Provider(ABC):
    @abstractmethod
    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str) -> Generator[str, None, None]:
        pass

class OllamaProvider(Provider):
    def __init__(self, model: str):
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str) -> Generator[str, None, None]:
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        data: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        }
        response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", headers=headers, data=json.dumps(data), stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                content = json.loads(line)["message"]["content"]
                yield content

class AnthropicProvider(Provider):
    def __init__(self, client: Anthropic, model: str):
        self.client: Anthropic = client
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> Generator[str, None, None]:
        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages
                ) as stream:
                    for text in stream.text_stream:
                        yield text
                return
            except AnthropicRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class GroqProvider(Provider):
    def __init__(self, client: Groq, model: str):
        self.client: Groq = client
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> Generator[str, None, None]:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )

                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content
                return
            except GroqRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class OpenAIProvider(Provider):
    def __init__(self, client: OpenAI, model: str, chat_model: str):
        self.client: OpenAI = client
        self.model: str = model
        self.chat_model: str = chat_model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> Generator[str, None, None]:
        for attempt in range(max_retries):
            try:
                params = { }

                use_stream = True if self.model != "o1-preview" and self.model != "o1-mini" else False
                use_model = self.model
                if mode == "chat":
                    use_model = self.chat_model

                if not use_model.startswith("o1"):
                    params["temperature"] = temperature

                response = self.client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    stream=use_stream,
                    **params
                )
                if use_stream:
                    for chunk in response:
                        part = chunk.choices[0].delta.content
                        if part is not None:
                            yield part
                else:
                    content = response.choices[0].message.content
                    yield content
                return
            except OpenAIRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class GoogleProvider(Provider):
    def __init__(self, model: str):
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> Generator[str, None, None]:
        for attempt in range(max_retries):
            try:
                model = google_genai.GenerativeModel(self.model)
                chat = model.start_chat(
                    history=[
                        {"role": "user", "parts": message["content"]} if message["role"] == "user"
                        else {"role": "model", "parts": message["content"]}
                        for message in messages[:-1]
                    ]
                )
                response = chat.send_message(
                    messages[-1]["content"],
                    generation_config=google_genai.types.GenerationConfig(
                        candidate_count=1,
                        stop_sequences=[],
                        max_output_tokens=max_tokens,
                        temperature=temperature
                    ),
                    stream=True
                )

                for chunk in response:
                    if chunk.text is not None:
                        yield chunk.text
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")



class MistralProvider(Provider):
    def __init__(self, client: Mistral, model: str):
        self.client: Mistral = client
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> Generator[str, None, None]:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.stream(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                for event in response:
                    content = event.data.choices[0].delta.content
                    if content:
                        yield content
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")


def get_api_key(provider: str) -> str:
    env_var_name = f"{provider.upper()}_API_KEY"
    api_key = os.environ.get(env_var_name)
    if not api_key:
        raise ValueError(f"{env_var_name} environment variable is not set")
    return api_key

def create_provider(model_name: str) -> Provider:
    if model_name not in MODEL_CONFIGS:
        raise ValueError(f"Invalid model name: {model_name}")

    config = MODEL_CONFIGS[model_name]

    if config.provider == "ollama":
        return OllamaProvider(config.model)
    elif config.provider == "anthropic":
        api_key = get_api_key("anthropic")
        client = Anthropic(api_key=api_key)
        return AnthropicProvider(client, config.model)
    elif config.provider == "groq":
        api_key = get_api_key("groq")
        client = Groq(api_key=api_key)
        return GroqProvider(client, config.model)
    elif config.provider == "openai":
        api_key = get_api_key("openai")
        client = OpenAI(api_key=api_key)
        return OpenAIProvider(client, config.model, config.chat_model)
    elif config.provider == "google":
        api_key = get_api_key("google")
        google_genai.configure(api_key=api_key)
        return GoogleProvider(config.model)
    elif config.provider == "mistral":
        api_key = get_api_key("mistral")
        client = Mistral(api_key=api_key)
        return MistralProvider(client, config.model)
    else:
        raise ValueError(f"Invalid provider specified: {config.provider}")

def get_model_config(model_name: str) -> ModelConfig:
    if model_name not in MODEL_CONFIGS:
        raise ValueError(f"Invalid model name: {model_name}")
    return MODEL_CONFIGS[model_name]
