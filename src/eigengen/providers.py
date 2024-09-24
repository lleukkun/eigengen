from abc import ABC, abstractmethod
import requests
import json
import time
import random
import os
from typing import List, Dict, Any, Optional, Union

from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError
from groq import Groq, RateLimitError as GroqRateLimitError
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
import google.generativeai as google_genai

OLLAMA_BASE_URL: str = "http://localhost:11434"

class ModelConfig:
    def __init__(self, provider: str, model: str, max_tokens: int, temperature: float):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "claude-sonnet": ModelConfig("anthropic", "claude-3-5-sonnet-20240620", 8192, 0.7),
    "gemma2": ModelConfig("ollama", "gemma2:27b", 128000, 0.5),
    "groq": ModelConfig("groq", "llama-3.1-70b-versatile", 8000, 0.5),
    "gpt4": ModelConfig("openai", "gpt-4o-2024-08-06", 128000, 0.7),
    "o1-preview": ModelConfig("openai", "o1-preview", 8000, 0.7),
    "o1-mini": ModelConfig("openai", "o1-mini", 4000, 0.7),
    "gemini": ModelConfig("google", "gemini-1.5-pro-002", 32768, 0.7)
}

class Provider(ABC):
    @abstractmethod
    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str) -> str:
        pass

class OllamaProvider(Provider):
    def __init__(self, model: str):
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str) -> str:
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

        streamed_content = ""
        for line in response.iter_lines():
            if line:
                content = json.loads(line)["message"]["content"]
                streamed_content += content
                if mode in ["default", "code_review"]:
                    print(content, end="")

        return streamed_content

class AnthropicProvider(Provider):
    def __init__(self, client: Anthropic, model: str):
        self.client: Anthropic = client
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> str:
        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages
                ) as stream:
                    streamed_content = ""
                    for text in stream.text_stream:
                        streamed_content += text
                        if mode in ["default", "code_review_start", "code_review_continue"]:
                            print(text, end="", flush=True)

                return streamed_content
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
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )

                streamed_content = ""
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        streamed_content += content
                        if mode in ["default", "code_review_start", "code_review_continue"]:
                            print(content, end="")

                return streamed_content
            except GroqRateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class OpenAIProvider(Provider):
    def __init__(self, client: OpenAI, model: str):
        self.client: OpenAI = client
        self.model: str = model

    def make_request(self, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> str:
        for attempt in range(max_retries):
            try:
                params = { }
                if not self.model.startswith("o1"):
                    params["temperature"] = temperature

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    **params
                )

                streamed_content = ""
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        streamed_content += content
                        if mode in ["default", "code_review_start", "code_review_continue"]:
                            print(content, end="")

                return streamed_content
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
                     max_tokens: int, temperature: float, mode: str, max_retries: int = 5, base_delay: int = 1) -> str:
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

                streamed_content = ""
                for chunk in response:
                    if chunk.text is not None:
                        streamed_content += chunk.text
                        if mode in ["default", "code_review_start", "code_review_continue"]:
                            print(chunk.text, end="")

                return streamed_content
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
        return OpenAIProvider(client, config.model)
    elif config.provider == "google":
        api_key = get_api_key("google")
        google_genai.configure(api_key=api_key)
        return GoogleProvider(config.model)
    else:
        raise ValueError(f"Invalid provider specified: {config.provider}")

def get_model_config(model_name: str) -> ModelConfig:
    if model_name not in MODEL_CONFIGS:
        raise ValueError(f"Invalid model name: {model_name}")
    return MODEL_CONFIGS[model_name]

