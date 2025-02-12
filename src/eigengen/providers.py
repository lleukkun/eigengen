from abc import ABC, abstractmethod
import dataclasses
import requests
import json
import time
import random
import os
from typing import Any, Dict, Iterable, List, Generator, Optional, cast

import anthropic
import groq
import openai
from google import genai
from google.genai import types
from mistralai import Mistral

from eigengen import config

OLLAMA_BASE_URL: str = "http://localhost:11434"


class ProviderConfig:
    def __init__(self, provider: str, model: str,
                 max_tokens: int, temperature: float):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

PROVIDER_CONFIGS: Dict[str, ProviderConfig] = {
    "claude": ProviderConfig(
        "anthropic",
        "claude-3-5-sonnet-latest",
        8192,
        0.7,
    ),
    "deepseek-r1:32b": ProviderConfig(
        "ollama", "deepseek-r1:32b", 8192, 0.7
    ),
    "deepseek-r1": ProviderConfig(
        "deepseek", "deepseek-reasoner", 8192, 0.7
    ),
    "groq": ProviderConfig(
        "groq",
        "deepseek-r1-distill-llama-70b",
        32768,
        0.5,
    ),
    "o1": ProviderConfig("openai", "o1", 100000, 0.7),
    "o3-mini": ProviderConfig(
        "openai", "o3-mini",  100000, 0.7
    ),
    "gemini": ProviderConfig(
        "google",
        "gemini-2.0-flash-thinking-exp",
        8192,
        0.7,
    ),
    "mistral": ProviderConfig(
        "mistral",
        "mistral-large-latest",
        32768,
        0.7,
    ),
}

class Provider(ABC):
    @abstractmethod
    def make_request(self,
                     model: str,
                     messages: List[Dict[str, str]],
                     max_tokens: int,
                     temperature: float,
                     prediction: str|None) -> Generator[str, None, None]:
        pass


@dataclasses.dataclass
class Model:
    provider: Provider
    model_name: str
    temperature: float
    max_tokens: int


class OllamaProvider(Provider):
    def __init__(self):
        super().__init__()

    def make_request(self,
                     model: str,
                     messages: List[Dict[str, str]],
                     max_tokens: int,
                     temperature: float,
                     _=None) -> Generator[str, None, None]:
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        data: Dict[str, Any] = {
            "model": model,
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
    def __init__(self, client: anthropic.Anthropic):
        super().__init__()
        self.client: anthropic.Anthropic = client

    def make_request(self,
                     model: str,
                     messages: List[Dict[str, str]],
                     max_tokens: int,
                     temperature: float,
                     _=None) -> Generator[str, None, None]:

        if len(messages) < 1:
            return

        system_message = messages[0]["content"]
        messages = messages[1:]
        max_retries = 5
        base_delay = 1

        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=cast(Iterable[anthropic.types.MessageParam], messages),
                    system=system_message
                ) as stream:
                    for text in stream.text_stream:
                        yield text
                return
            except anthropic.RateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")

class GroqProvider(Provider):
    def __init__(self, client: groq.Groq):
        super().__init__()
        self.client: groq.Groq = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(self, model: str, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, _=None) -> Generator[str, None, None]:

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=cast(List, messages),
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )

                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content
                return
            except groq.RateLimitError as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


class OpenAIProvider(Provider):
    def __init__(self, client: openai.OpenAI):
        super().__init__()
        self.client: openai.OpenAI = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(self, model: str, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, max_retries: int = 5,
                     base_delay: int = 1, prediction: Optional[str] = None) -> Generator[str, None, None]:

        # map to openai specifics
        openai_messages: List[openai.types.chat.ChatCompletionMessageParam] = []

        for message in messages:
            role = message["role"]
            if role == "system" and model in ["o1-preview", "o1-mini"]:
                # need to pass the system message as a user message for these models
                openai_messages.extend([
                    { "role": "user", "content": message["content"] },
                    { "role": "assistant", "content": "Acknowledge." }
                ])
            else:
                openai_messages.append({ "role": role, "content": message["content"] })

        for attempt in range(max_retries):
            try:
                params = { }

                use_stream = True if model not in ["o1", "o1-mini"] else False

                if model not in ["o1", "o3-mini"]:
                    params["temperature"] = temperature
                    if prediction:
                        params["prediction"] = prediction

                response = self.client.chat.completions.create(
                    model=model,
                    messages=cast(List, openai_messages),
                    stream=use_stream,
                    **params
                )
                if isinstance(response, openai.Stream):
                    for chunk in response:
                        part = chunk.choices[0].delta.content
                        if part is not None:
                            yield part
                else:
                    content = response.choices[0].message.content
                    yield content or ""
                return
            except openai.RateLimitError as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


class GoogleProvider(Provider):
    def __init__(self, client: genai.Client):
        super().__init__()
        self.client = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(self, model: str, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, _=None) -> Generator[str, None, None]:
        if len(messages) < 1:
            return

        system_message = messages[0]["content"]

        for attempt in range(self.max_retries):
            try:
                chat = self.client.chats.create(
                    model=model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_message,
                        candidate_count=1,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                    history=cast(
                        List[types.Content],
                        [
                            {"role": "user", "parts": [{"text": message["content"]}]}
                            if message["role"] == "user"
                            else {"role": "model", "parts": [{"text": message["content"]}]}
                            for message in messages[1:-1]
                        ],
                    ),
                )
                response = chat.send_message(
                    messages[-1]["content"],
                )
                if response.candidates:
                    yield response.candidates[0].content.parts[0].text or ""
                else:
                    yield ""
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")



class MistralProvider(Provider):
    def __init__(self, client: Mistral):
        super().__init__()
        self.client: Mistral = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(self, model: str, messages: List[Dict[str, str]],
                     max_tokens: int, temperature: float, _=None) -> Generator[str, None, None]:
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.stream(
                    model=model,
                    messages=cast(List, messages),
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                if response is None:
                    return

                for event in response:
                    content = event.data.choices[0].delta.content
                    if content:
                        yield content
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


def get_api_key(provider: str, config: config.EggConfig) -> str:
    env_var_name = f"{provider.upper()}_API_KEY"
    api_key = os.environ.get(env_var_name, None)
    if api_key:
        # we use environment variable if it is set
        return api_key

    config_file_key = getattr(config, f"{provider.lower()}_api_key")

    if not config_file_key:
        raise ValueError(f"{env_var_name} environment variable is not set")

    return config_file_key


def create_model(nickname: str, config: config.EggConfig) -> Model:
    if nickname not in PROVIDER_CONFIGS:
        raise ValueError(f"Invalid model nickname: {nickname}")

    model_config = PROVIDER_CONFIGS[nickname]
    provider = None
    if model_config.provider == "ollama":
        provider = OllamaProvider()
    elif model_config.provider == "anthropic":
        api_key = get_api_key("anthropic", config)
        client = anthropic.Anthropic(api_key=api_key)
        provider =  AnthropicProvider(client)
    elif model_config.provider == "groq":
        api_key = get_api_key("groq", config)
        client = groq.Groq(api_key=api_key)
        provider = GroqProvider(client)
    elif model_config.provider == "openai":
        api_key = get_api_key("openai", config)
        client = openai.OpenAI(api_key=api_key)
        provider = OpenAIProvider(client)
    elif model_config.provider == "google":
        api_key = get_api_key("google", config)
        client = genai.Client(api_key=api_key)
        provider = GoogleProvider(client)
    elif model_config.provider == "mistral":
        api_key = get_api_key("mistral", config)
        client = Mistral(api_key=api_key)
        provider = MistralProvider(client)
    elif model_config.provider == "deepseek":
        api_key = get_api_key("deepseek", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        provider = OpenAIProvider(client)
    else:
        raise ValueError(f"Invalid provider specified: {model_config.provider}")
    return Model(provider=provider,
                 model_name=model_config.model,
                 temperature=model_config.temperature,
                 max_tokens=model_config.max_tokens)


def get_model_config(nickname: str) -> ProviderConfig:
    if nickname not in PROVIDER_CONFIGS:
        raise ValueError(f"Invalid model nickname: {nickname}")
    return PROVIDER_CONFIGS[nickname]
