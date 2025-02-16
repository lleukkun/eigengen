import dataclasses
import json
import logging
import os
import random
import time
from abc import abstractmethod
from enum import Enum
from typing import Any, Generator, Iterable, Protocol, cast

import anthropic
import groq
import openai
import requests
from google import genai
from google.genai import types
from mistralai import Mistral

from eigengen import config, log

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = "http://localhost:11434"


class Provider(Protocol):
    @abstractmethod
    def make_request(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        prediction: str | None,
        reasoning_effort: str | None,
    ) -> Generator[str, None, None]: ...

@dataclasses.dataclass
class ModelParams:
    name: str
    temperature: float


@dataclasses.dataclass
class ProviderParams:
    large_model: ModelParams
    small_model: ModelParams

class ModelType(Enum):
    LARGE = "large"
    SMALL = "small"

class ReasoningAmount(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ProviderManager:
    def __init__(self, provider_name: str, config: config.EggConfig):
        self.provider_name = provider_name
        self.config = config
        self.provider_params = PROVIDER_ALIASES[provider_name]
        self.provider = create_provider(self.provider_name, self.config)

    def process_request(
        self,
        model_type: ModelType,
        reasoning_effort: ReasoningAmount,
        system_message: str,
        messages: list[dict[str, str]],
    ) -> Generator[str, None, None]:
        """
        Processes a request by interfacing with the specified model and handling the conversation flow.
        Args:
            model (providers.Model): The Model instance to use.
            messages (list[dict[str, str]]): The list of messages in the conversation.
            system_message (str): The system message to use.
        Yields:
            str: Chunks of the final answer as they are generated.
        """

        steering_messages = []
        steering_role = "system"
        steering_messages = [{"role": steering_role, "content": system_message}]

        combined_messages = steering_messages + messages
        model = self.provider_params.large_model if model_type == ModelType.LARGE else self.provider_params.small_model
        final_answer: str = ""
        for chunk in self.provider.make_request(model.name,
                                                combined_messages,
                                                model.temperature,
                                                reasoning_effort):
            final_answer += chunk
            yield chunk

        # Log the request and response
        log.log_request_response(model.name, messages, final_answer)


class OllamaProvider(Provider):
    def __init__(self):
        super().__init__()

    def make_request(
        self, model_name: str, messages: list[dict[str, str]], temperature: float, reasoning_effort=None
    ) -> Generator[str, None, None]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        data: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
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

    def make_request(
        self, model_name: str, messages: list[dict[str, str]], temperature: float, reasoning_effort=None
    ) -> Generator[str, None, None]:
        if len(messages) < 1:
            return

        system_message = messages[0]["content"]
        messages = messages[1:]
        max_retries = 5
        base_delay = 1

        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=model_name,
                    temperature=temperature,
                    messages=cast(Iterable[anthropic.types.MessageParam], messages),
                    max_tokens=8192,
                    system=system_message,
                ) as stream:
                    for text in stream.text_stream:
                        yield text
                return
            except anthropic.RateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {max_retries} retries")


class GroqProvider(Provider):
    def __init__(self, client: groq.Groq):
        super().__init__()
        self.client: groq.Groq = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model: str, messages: list[dict[str, str]], temperature: float, reasoning_effort=None
    ) -> Generator[str, None, None]:
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=cast(list, messages), model=model, temperature=temperature, stream=True
                )

                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content
                return
            except groq.RateLimitError as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


class OpenAIProvider(Provider):
    def __init__(self, client: openai.OpenAI):
        super().__init__()
        self.client: openai.OpenAI = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_name: str, messages: list[dict[str, str]], temperature: float, reasoning_effort: str = "medium"
    ) -> Generator[str, None, None]:
        # map to openai specifics
        openai_messages: list[openai.types.chat.ChatCompletionMessageParam] = []
        if model_name.startswith("deepseek-") or model_name in ["o1-preview", "o1-mini"]:
            # deepseek models prefer no system messages, so we integrate the
            # system message into the user message
            system_instruction = messages[0]["content"]

            openai_messages.extend(messages[1:])
            openai_messages[-1]["content"] += f"\n{system_instruction}"
        else:
            for message in messages:
                role = message["role"]
                openai_messages.append({"role": role, "content": message["content"]})

        for attempt in range(self.max_retries):
            try:
                params = {}

                use_stream = True if model_name not in ["o1", "o1-mini"] else False

                if model_name in ["o3-mini"]:
                    params["reasoning_effort"] = "high"
                if model_name not in ["o1", "o3-mini"]:
                    params["temperature"] = temperature

                response = self.client.chat.completions.create(
                    model=model_name, messages=cast(list, openai_messages), stream=use_stream, **params
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
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


class GoogleProvider(Provider):
    def __init__(self, client: genai.Client):
        super().__init__()
        self.client = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_name: str, messages: list[dict[str, str]], temperature: float, reasoning_effort=None
    ) -> Generator[str, None, None]:
        if len(messages) < 1:
            return

        system_message = messages[0]["content"]

        for attempt in range(self.max_retries):
            try:
                chat = self.client.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_message,
                        candidate_count=1,
                        temperature=temperature,
                    ),
                    history=cast(
                        list[types.Content],
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
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Error occurred. Retrying in {delay:.2f} seconds...")
                if attempt == self.max_retries - 1:
                    raise e
                logger.warning(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


class MistralProvider(Provider):
    def __init__(self, client: Mistral):
        super().__init__()
        self.client: Mistral = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_name: str, messages: list[dict[str, str]], temperature: float, reasoning_effort=None
    ) -> Generator[str, None, None]:
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.stream(model=model_name,
                                                   messages=cast(list, messages),
                                                   temperature=temperature)
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
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")


PROVIDER_ALIASES: dict[str, ProviderParams] = {
    "anthropic": ProviderParams(
        large_model=ModelParams("claude-3-5-sonnet-latest", 0.7),
        small_model=ModelParams("claude-3-5-sonnet-latest", 0.7),
    ),
    "ollama": ProviderParams(
        large_model=ModelParams("deepseek-r1:14b", 0.6), small_model=ModelParams("deepseek-r1:14b", 0.6)
    ),
    "deepseek": ProviderParams(
        large_model=ModelParams("deepseek-reasoner", 0.6), small_model=ModelParams("deepseek-chat", 0.6)
    ),
    "groq": ProviderParams(
        large_model=ModelParams("deepseek-r1-distill-llama-70b", 0.6),
        small_model=ModelParams("llama3.1-70b-versatile", 0.6),
    ),
    "openai-o1": ProviderParams(large_model=ModelParams("o1", 0.7),
                                small_model=ModelParams("gpt-4o-mini", 0.5)),
    "openai-o3-mini": ProviderParams(large_model=ModelParams("o3-mini", 0.7),
                                     small_model=ModelParams("gpt-4o-mini", 0.5)),
    "google": ProviderParams(large_model=ModelParams("gemini-2.0-pro-exp-02-05", 0.7),
                             small_model=ModelParams("gemini-2.0-flash", 0.7)),
    "mistral": ProviderParams(large_model=ModelParams("mistral-large-latest", 0.5),
                              small_model=ModelParams("mistral-codestral-latest", 0.5)),
}


def get_api_key(provider_name: str, config: config.EggConfig) -> str:
    env_var_name = f"{provider_name.upper()}_API_KEY"
    api_key = os.environ.get(env_var_name, None)
    if api_key:
        # we use environment variable if it is set
        return api_key

    config_file_key = getattr(config, f"{provider_name.lower()}_api_key")

    if not config_file_key:
        raise ValueError(f"{env_var_name} environment variable is not set")

    return config_file_key


def create_provider(provider_name: str, config: config.EggConfig) -> Provider:
    if provider_name == "ollama":
        return OllamaProvider()
    elif provider_name == "anthropic":
        api_key = get_api_key("anthropic", config)
        client = anthropic.Anthropic(api_key=api_key)
        return AnthropicProvider(client)
    elif provider_name == "groq":
        api_key = get_api_key("groq", config)
        client = groq.Groq(api_key=api_key)
        return GroqProvider(client)
    elif provider_name == "openai-o3-mini":
        api_key = get_api_key("openai", config)
        client = openai.OpenAI(api_key=api_key)
        return OpenAIProvider(client)
    elif provider_name == "openai-o1":
        api_key = get_api_key("openai", config)
        client = openai.OpenAI(api_key=api_key)
        return OpenAIProvider(client)
    elif provider_name == "google":
        api_key = get_api_key("google", config)
        client = genai.Client(api_key=api_key)
        return GoogleProvider(client)
    elif provider_name == "mistral":
        api_key = get_api_key("mistral", config)
        client = Mistral(api_key=api_key)
        return MistralProvider(client)
    elif provider_name == "deepseek":
        api_key = get_api_key("deepseek", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        return OpenAIProvider(client)
    else:
        raise ValueError(f"Invalid provider name: {provider_name}")
