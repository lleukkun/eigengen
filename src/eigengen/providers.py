import dataclasses
import json
import logging
import os
import random
import re
import time
from abc import abstractmethod
from enum import Enum
from typing import Any, Generator, Protocol, cast

import anthropic
import openai
import requests
from mistralai import (
    AssistantMessage,
    ChatCompletionStreamRequestMessages,
    Mistral,
    SystemMessage,
    TextChunkType,
    UserMessage,
)
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from eigengen import config, log

logger = logging.getLogger(__name__)


class ReasoningAmount(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelType(Enum):
    LARGE = "large"
    SMALL = "small"


@dataclasses.dataclass
class ModelSpec:
    provider: str
    large_name: str
    large_temperature: float
    small_name: str
    small_temperature: float


@dataclasses.dataclass
class ModelParams:
    name: str
    temperature: float


class Provider(Protocol):
    model_spec: ModelSpec

    def __init__(self, model_spec: ModelSpec) -> None:
        self.model_spec = model_spec

    def get_model_params(self, model_type: ModelType) -> ModelParams:
        if model_type == ModelType.LARGE:
            return ModelParams(name=self.model_spec.large_name, temperature=self.model_spec.large_temperature)
        else:
            return ModelParams(name=self.model_spec.small_name, temperature=self.model_spec.small_temperature)

    @abstractmethod
    def make_request(
        self,
        model_type: ModelType,
        messages: list[tuple[str, str]],
        system_message: str,
        reasoning_effort: ReasoningAmount = ReasoningAmount.MEDIUM,
    ) -> Generator[str, None, None]: ...


@dataclasses.dataclass
class ProviderParams:
    large_model: ModelParams
    small_model: ModelParams


def parse_model_spec(input_str: str) -> ModelSpec:
    """
    Parses model string using regex with strict format validation.
    Format: provider:large_name@temperature:small_name@temperature
    """
    pattern = r"^([^;]+);([^;@]+)@(\d+\.?\d*|\.\d+);([^;@]+)@(\d+\.?\d*|\.\d+)$"
    match = re.fullmatch(pattern, input_str)

    if not match:
        raise ValueError("Invalid format. Expected: provider:name@num:name@num")

    return (ModelSpec(provider=match.group(1), large_name=match.group(2), large_temperature=float(match.group(3)),
            small_name=match.group(4), small_temperature=float(match.group(5))))



class ProviderManager:
    def __init__(self, model_identifier: str, config: config.EggConfig):
        self.spec = parse_model_spec(model_identifier)
        self.config = config
        self.provider = create_provider(self.spec, self.config)

    def process_request(
        self,
        model_type: ModelType,
        reasoning_effort: ReasoningAmount,
        system_message: str,
        messages: list[tuple[str, str]],
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

        final_answer: str = ""
        for chunk in self.provider.make_request(model_type, messages, system_message, reasoning_effort):
            final_answer += chunk
            yield chunk

        # Log the request and response
        log.log_request_response(self.spec.large_name, messages, final_answer)


class AnthropicProvider(Provider):
    def __init__(self, client: anthropic.Anthropic, model_spec: ModelSpec):
        super().__init__(model_spec)
        self.client: anthropic.Anthropic = client

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str, str]],
        system_message: str,
        reasoning_effort=ReasoningAmount.MEDIUM
    ) -> Generator[str, None, None]:
        if len(messages) < 1:
            return

        anthropic_messages: list[anthropic.types.MessageParam] = []
        for message in messages:
            if message[0] == "user":
                anthropic_messages.append(anthropic.types.MessageParam(role="user", content=message[1]))
            else:
                anthropic_messages.append(anthropic.types.MessageParam(role="assistant", content=message[1]))
        max_retries = 5
        base_delay = 1
        model_params = self.get_model_params(model_type)
        extra_params = {}
        if model_params.name.startswith("claude-3.7"):
            if reasoning_effort == ReasoningAmount.LOW:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 2000 }
            elif reasoning_effort == ReasoningAmount.MEDIUM:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 8000 }
            elif reasoning_effort == ReasoningAmount.HIGH:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 24000 }
        max_tokens = 8192
        if "thinking" in extra_params:
            max_tokens += extra_params["thinking"]["budget_tokens"]

        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=model_params.name,
                    temperature=model_params.temperature,
                    messages=anthropic_messages,
                    max_tokens=max_tokens,
                    system=system_message,
                    **extra_params,
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


class OpenAIProvider(Provider):
    def __init__(self, client: openai.OpenAI, model_spec: ModelSpec):
        super().__init__(model_spec)
        self.client: openai.OpenAI = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str,str]],
        system_message: str,
        reasoning_effort: ReasoningAmount = ReasoningAmount.MEDIUM
    ) -> Generator[str, None, None]:
        model_params = self.get_model_params(model_type)

        # map to openai specifics
        openai_messages: list[ChatCompletionMessageParam] = []
        # we integrate the system message into the user message for deepseek-reasoner
        if model_params.name not in ["deepseek-reasoner"]:
            openai_messages.append(ChatCompletionSystemMessageParam(role="system", content=system_message))

        for index, message in enumerate(messages):
            if message[0] == "user":
                content = message[1]
                if index == len(messages) - 1 and model_params.name in ["deepseek-reasoner"]:
                    content += f"\n{system_message}"
                openai_messages.append(ChatCompletionUserMessageParam(role="user", content=content))
            else:
                openai_messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=message[1]))

        for attempt in range(self.max_retries):
            try:
                params = {}

                use_stream = True if model_params.name not in ["o1", "o1-mini", "o3", "o3-mini", "o4-mini"] else False

                if model_params.name in ["o4-mini", "o3", "o3-mini", "deepseek-reasoner"]:
                    if reasoning_effort == ReasoningAmount.LOW:
                        params["reasoning_effort"] = "low"
                    elif reasoning_effort == ReasoningAmount.MEDIUM:
                        params["reasoning_effort"] = "medium"
                    elif reasoning_effort == ReasoningAmount.HIGH:
                        params["reasoning_effort"] = "high"
                if model_params.name not in ["o1", "o3-mini", "o3", "o4-mini"]:
                    params["temperature"] = model_params.temperature

                response = self.client.chat.completions.create(
                    model=model_params.name, messages=cast(list, openai_messages), stream=use_stream, **params
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


class MistralProvider(Provider):
    def __init__(self, client: Mistral, model_spec: ModelSpec):
        super().__init__(model_spec)
        self.client: Mistral = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str, str]], system_message: str, reasoning_effort=None
    ) -> Generator[str, None, None]:

        model_params = self.get_model_params(model_type)

        mistral_messages: list[ChatCompletionStreamRequestMessages] = []
        mistral_messages.append(SystemMessage(role="system", content=system_message))
        for message in messages:
            if message[0] == "user":
                mistral_messages.append(UserMessage(role="user", content=message[1]))
            else:
                mistral_messages.append(AssistantMessage(role="assistant", content=message[1]))

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.stream(
                    model=model_params.name, messages=mistral_messages, temperature=model_params.temperature
                )
                if response is None:
                    return

                for event in response:
                    content = event.data.choices[0].delta.content
                    if content:
                        if isinstance(content, list):
                            for chunk in content:
                                if chunk is TextChunkType:
                                    yield chunk.text
                        else:
                            yield content
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise e
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Error occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise IOError(f"Unable to complete API call in {self.max_retries} retries")



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


def create_provider(model_spec: ModelSpec,
                    config: config.EggConfig) -> Provider:
    if model_spec.provider == "ollama":
        api_key="ollama"
        client = openai.OpenAI(api_key=api_key, base_url="http://localhost:11434/v1")
        return OpenAIProvider(client, model_spec=model_spec)
    elif model_spec.provider == "anthropic":
        api_key = get_api_key("anthropic", config)
        client = anthropic.Anthropic(api_key=api_key)
        return AnthropicProvider(client, model_spec)
    elif model_spec.provider == "groq":
        api_key = get_api_key("groq", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        return OpenAIProvider(client, model_spec)
    elif model_spec.provider == "openai":
        api_key = get_api_key("openai", config)
        client = openai.OpenAI(api_key=api_key)
        return OpenAIProvider(client, model_spec)
    elif model_spec.provider == "google":
        api_key = get_api_key("google", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        return OpenAIProvider(client, model_spec)
    elif model_spec.provider == "mistral":
        api_key = get_api_key("mistral", config)
        client = Mistral(api_key=api_key)
        return MistralProvider(client, model_spec)
    elif model_spec.provider == "deepseek":
        api_key = get_api_key("deepseek", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        return OpenAIProvider(client, model_spec)
    elif model_spec.provider == "xai":
        api_key = get_api_key("xai", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        return OpenAIProvider(client, model_spec)
    else:
        raise ValueError(f"Invalid provider name: {model_spec.provider}")
