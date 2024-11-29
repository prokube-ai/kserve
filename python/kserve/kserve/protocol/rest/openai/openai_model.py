# Copyright 2023 The KServe Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from abc import abstractmethod
from typing import Any, AsyncIterator, Callable, Dict, Optional, Union, List
import inspect

from pydantic import BaseModel, Field

from kserve.protocol.rest.openai.types import (
    ChatCompletion,
    ChatCompletionChunk,
    Completion,
    CreateChatCompletionRequest as BaseCreateChatCompletionRequest,
    CreateCompletionRequest as BaseCreateCompletionRequest,
)

from ....model import BaseKServeModel


class ChatPrompt(BaseModel):
    response_role: str = "assistant"
    prompt: str


class VLLMCreateCompletionRequest(BaseModel):
    """
    VLLM-specific extra completion params. Not a part of OpenAI API.
    """

    # https://github.com/vllm-project/vllm/blob/main/vllm/entrypoints/openai/protocol.py#L566
    # https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#extra-parameters
    guided_json: Optional[Union[str, dict, BaseModel]] = Field(
        default=None,
        description="If specified, the output will follow the JSON schema.",
    )
    guided_regex: Optional[str] = Field(
        default=None,
        description=("If specified, the output will follow the regex pattern."),
    )
    guided_choice: Optional[List[str]] = Field(
        default=None,
        description=("If specified, the output will be exactly one of the choices."),
    )
    guided_grammar: Optional[str] = Field(
        default=None,
        description=("If specified, the output will follow the context free grammar."),
    )
    guided_decoding_backend: Optional[str] = Field(
        default=None,
        description=(
            "If specified, will override the default guided decoding backend "
            "of the server for this specific request. If set, must be one of "
            "'outlines' / 'lm-format-enforcer'"
        ),
    )
    guided_whitespace_pattern: Optional[str] = Field(
        default=None,
        description=(
            "If specified, will override the default whitespace pattern "
            "for guided json decoding."
        ),
    )


class VLLMCreateChatCompletionRequest(BaseModel):
    """
    VLLM-specific extra chat completion params. Not a part of OpenAI API.
    """

    # https://github.com/vllm-project/vllm/blob/main/vllm/entrypoints/openai/protocol.py#L254
    # https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#extra-parameters
    guided_json: Optional[Union[str, dict, BaseModel]] = Field(
        default=None,
        description=("If specified, the output will follow the JSON schema."),
    )
    guided_regex: Optional[str] = Field(
        default=None,
        description=("If specified, the output will follow the regex pattern."),
    )
    guided_choice: Optional[List[str]] = Field(
        default=None,
        description=("If specified, the output will be exactly one of the choices."),
    )
    guided_grammar: Optional[str] = Field(
        default=None,
        description=("If specified, the output will follow the context free grammar."),
    )
    guided_decoding_backend: Optional[str] = Field(
        default=None,
        description=(
            "If specified, will override the default guided decoding backend "
            "of the server for this specific request. If set, must be either "
            "'outlines' / 'lm-format-enforcer'"
        ),
    )
    guided_whitespace_pattern: Optional[str] = Field(
        default=None,
        description=(
            "If specified, will override the default whitespace pattern "
            "for guided json decoding."
        ),
    )


class CreateCompletionRequest(BaseCreateCompletionRequest, VLLMCreateCompletionRequest):
    """
    Overrides OpenAPI CreateCompletionRequest with VLLM-specific params.
    """


class CreateChatCompletionRequest(
    BaseCreateChatCompletionRequest, VLLMCreateChatCompletionRequest
):
    """
    Overrides OpenAPI CreateChatCompletionRequest with VLLM-specific params.
    """


class BaseCompletionRequest(BaseModel):
    request_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None  # headers can go in here
    params: Union[CreateCompletionRequest, CreateChatCompletionRequest]


class CompletionRequest(BaseCompletionRequest):
    params: CreateCompletionRequest


class ChatCompletionRequest(BaseCompletionRequest):
    params: CreateChatCompletionRequest


class OpenAIModel(BaseKServeModel):
    """
    An abstract model with methods for implementing OpenAI's completions (v1/completions)
    and chat completions (v1/chat/completions) endpoints.

    Users should extend this model and implement the abstract methods in order to expose
    these endpoints.
    """

    def __init__(self, name: str):
        super().__init__(name)

        # We don't support the `load()` method on OpenAIModel yet
        # Assume the model is ready
        self.ready = True

    @abstractmethod
    async def create_completion(
        self, request: CompletionRequest
    ) -> Union[Completion, AsyncIterator[Completion]]:
        pass

    @abstractmethod
    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> Union[ChatCompletion, AsyncIterator[ChatCompletionChunk]]:
        pass


class AsyncMappingIterator:
    def __init__(
        self,
        iterator: AsyncIterator,
        mapper: Callable = lambda item: item,
        skip_none: bool = True,
        close: Optional[Callable] = None,
    ):
        self.iterator = iterator
        self.mapper = mapper
        self.skip_none = skip_none
        self.close = close

    def __aiter__(self):
        return self

    async def __anext__(self):
        # This will raise StopAsyncIteration when there are no more completions.
        # We don't catch it so it will stop our iterator as well.
        async def next():
            try:
                return self.mapper(await self.iterator.__anext__())
            except Exception as e:
                if self.close:
                    if inspect.iscoroutinefunction(self.close):
                        await self.close()
                    else:
                        self.close()
                raise e

        mapped_item = await next()
        if self.skip_none:
            while mapped_item is None:
                mapped_item = await next()
        return mapped_item
