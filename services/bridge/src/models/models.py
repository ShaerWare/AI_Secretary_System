"""OpenAI-compatible model listing models."""

from typing import Literal
from pydantic import BaseModel, Field
import time


class Model(BaseModel):
    """Model information."""

    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "cli-bridge"

    # Extended: provider capabilities
    supports_streaming: bool = True
    supports_thinking: bool = False


class ModelList(BaseModel):
    """List of available models."""

    object: Literal["list"] = "list"
    data: list[Model]
