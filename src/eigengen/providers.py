"""Provider module for wrapping multiple LLM backends behind a unified interface."""

import dataclasses
import logging
import os
import random
import re
import time
from abc import abstractmethod
from enum import Enum
from typing import Generator, Protocol, cast

import anthropic
import openai
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
    """
    Enumeration for controlling the amount of reasoning effort applied.

    LOW:   Use minimal reasoning to maximize speed.
    MEDIUM: Balanced reasoning depth and latency.
    HIGH:  Maximum reasoning depth at the cost of increased latency.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelType(Enum):
    """
    Enumeration for selecting a model size profile.

    LARGE: Use the larger, more capable model.
    SMALL: Use the smaller, faster model.
    """
    LARGE = "large"
    SMALL = "small"


@dataclasses.dataclass
class ModelSpec:
    """
    Specification of a pair of models (large and small) for a given provider.

    Attributes:
        provider: Name of the backend provider (e.g., "openai", "anthropic").
        large_name: Identifier of the large model.
        large_temperature: Sampling temperature for the large model.
        small_name: Identifier of the small model.
        small_temperature: Sampling temperature for the small model.
    """
    provider: str
    large_name: str
    large_temperature: float
    small_name: str
    small_temperature: float


@dataclasses.dataclass
class ModelParams:
    """
    Runtime parameters for selecting a specific model instance.

    Attributes:
        name: Model identifier to send to the backend.
        temperature: Sampling temperature for generation.
    """
    name: str
    temperature: float


class Provider(Protocol):
    """
    Protocol for providers implementing a unified chat interface.

    Methods:
        get_model_params: Return the desired model settings (name and temperature).
        make_request: Stream tokens from the backend given a conversation.
    """
    model_spec: ModelSpec

    def __init__(self, model_spec: ModelSpec) -> None:
        self.model_spec = model_spec

    def get_model_params(self, model_type: ModelType) -> ModelParams:
        """
        Return the ModelParams for the requested ModelType.
        """
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
    """
    Convenience container for the two ModelParams (large and small) of a provider.
    """
    large_model: ModelParams
    small_model: ModelParams


def parse_model_spec(input_str: str) -> ModelSpec:
    """
    Parse a model specification string of the form:
        provider;large_name@temp;small_name@temp

    Args:
        input_str: A string matching the pattern
            provider;large_model_name@temperature;small_model_name@temperature

    Returns:
        A ModelSpec instance.

    Raises:
        ValueError: If the input_str does not conform to the required format.
    """
    pattern = r"^([^;]+);([^;@]+)@(\d+\.?\d*|\.\d+);([^;@]+)@(\d+\.?\d*|\.\d+)$"
    match = re.fullmatch(pattern, input_str)

    if not match:
        raise ValueError("Invalid format. Expected: provider:name@num:name@num")

    return (ModelSpec(provider=match.group(1), large_name=match.group(2), large_temperature=float(match.group(3)),
            small_name=match.group(4), small_temperature=float(match.group(5))))



class ProviderManager:
    def __init__(self, model_identifier: str, config: config.EggConfig):
        """
        Initialize the ProviderManager.

        Args:
            model_identifier: A spec string parsed by parse_model_spec.
            config: Global EggConfig containing API keys and settings.
        """
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
        Make a streaming request to the configured provider and yield response chunks.

        Args:
            model_type: Whether to use LARGE or SMALL model.
            reasoning_effort: Degree of reasoning to apply.
            system_message: The system-level prompt.
            messages: Sequence of (“role”, “content”) tuples for conversation.

        Yields:
            Response text in incremental chunks.
        """

        final_answer: str = ""
        for chunk in self.provider.make_request(model_type, messages, system_message, reasoning_effort):
            final_answer += chunk
            yield chunk

        # Log the request and response
        log.log_request_response(self.spec.large_name, messages, final_answer)


class AnthropicProvider(Provider):
    def __init__(self, client: anthropic.Anthropic, model_spec: ModelSpec):
        """
        Provider for Anthropic Claude endpoints.

        Args:
            client: Configured Anthropich client instance.
            model_spec: Specification of Claude model names and temperatures.
        """
        super().__init__(model_spec)
        self.client: anthropic.Anthropic = client

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str, str]],
        system_message: str,
        reasoning_effort=ReasoningAmount.MEDIUM
    ) -> Generator[str, None, None]:
        """
        Stream responses from Anthropic Claude models with optional thinking budgets.

        Args:
            model_type: LARGE or SMALL model selection.
            messages: Conversation history as (role, content).
            system_message: System prompt to prepend.
            reasoning_effort: How much internal thinking tokens to budget.

        Yields:
            Text chunks as received from the stream.

        Raises:
            IOError: If the request fails after retrying.
        """
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
        if model_params.name in ["claude-opus-4-20250514", "claude-sonnet-4-20250514"] :
            extra_params["max_tokens"] = 32000
            if reasoning_effort == ReasoningAmount.LOW:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 2000 }
            elif reasoning_effort == ReasoningAmount.MEDIUM:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 8000 }
            elif reasoning_effort == ReasoningAmount.HIGH:
                extra_params["thinking"] = { "type": "enabled",
                                             "budget_tokens": 24000 }
        else:
            extra_params["max_tokens"] = 8192

        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=model_params.name,
                    temperature=model_params.temperature,
                    messages=anthropic_messages,
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
        """
        Provider for OpenAI (and compatible) chat endpoints.

        Args:
            client: An OpenAI-compatible client instance.
            model_spec: Specification of model names and temperatures.
        """
        super().__init__(model_spec)
        self.client: openai.OpenAI = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str,str]],
        system_message: str,
        reasoning_effort: ReasoningAmount = ReasoningAmount.MEDIUM
    ) -> Generator[str, None, None]:
        """
        Stream or single-shot chat completions from OpenAI-like models.

        Applies provider-specific parameter mapping and retry logic.

        Args:
            model_type: LARGE or SMALL to choose the correct model parameters.
            messages: History as (role, content).
            system_message: System-level prompt.
            reasoning_effort: Adjusts parameters for applicable model families.

        Yields:
            Generated tokens or full response when streaming is disabled.

        Raises:
            IOError: When retries are exhausted.
        """
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

                use_stream = True if model_params.name not in ["o1", "o1-mini", "o3", "o3-mini", "o4-mini", "grok-3-mini-latest"] else False

                if model_params.name in ["o4-mini", "o3", "o3-mini", "deepseek-reasoner", "grok-3-mini-latest"]:
                    if reasoning_effort == ReasoningAmount.LOW:
                        params["reasoning_effort"] = "low"
                    elif reasoning_effort == ReasoningAmount.MEDIUM:
                        params["reasoning_effort"] = "medium"
                    elif reasoning_effort == ReasoningAmount.HIGH:
                        params["reasoning_effort"] = "high"
                if model_params.name not in ["o1", "o3-mini", "o3", "o4-mini", "claude-opus-4-20250514", "claude-sonnet-4-20250514"]:
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
        """
        Provider for Mistral AI chat API.

        Args:
            client: Authenticated Mistral client.
            model_spec: Names and temperatures for Mistral models.
        """
        super().__init__(model_spec)
        self.client: Mistral = client
        self.max_retries = 5
        self.base_delay = 1

    def make_request(
        self, model_type: ModelType, messages: list[tuple[str, str]], system_message: str, reasoning_effort=None
    ) -> Generator[str, None, None]:
        """
        Stream chat completions from a Mistral endpoint with retry logic.

        Args:
            model_type: Which model variant to call.
            messages: A list of (role, content) pairs.
            system_message: The system-level instruction.
            reasoning_effort: Currently not used by Mistral; reserved.

        Yields:
            Partial text segments from the Mistral stream.

        Raises:
            IOError: If the maximum number of retries is reached.
        """
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
    """
    Resolve an API key by checking environment first, then config object.

    Args:
        provider_name: The lowercase name of the provider (e.g., "openai").
        config: EggConfig containing any fallback API keys.

    Returns:
        The API key string.

    Raises:
        ValueError: When no API key is found in env or config.
    """
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
    """
    Factory to build the appropriate Provider instance based on ModelSpec.provider.

    Args:
        model_spec: Parsed model specification.
        config: Configuration holding API credentials.

    Returns:
        A concrete Provider implementation.

    Raises:
        ValueError: If the provider name is unrecognized.
    """
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
    elif model_spec.provider == "cerebras":
        api_key = get_api_key("cerebras", config)
        client = openai.OpenAI(api_key=api_key, base_url="https://api.cerebras.ai/v1")
        return OpenAIProvider(client, model_spec)
    else:
        raise ValueError(f"Invalid provider name: {model_spec.provider}")
