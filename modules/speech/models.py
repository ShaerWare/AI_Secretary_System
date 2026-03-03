"""Speech models: TTS presets."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class TTSPreset(Base):
    """Custom TTS voice preset with parameters"""

    __tablename__ = "tts_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    params: Mapped[str] = mapped_column(Text)  # JSON object with TTS parameters
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": json.loads(self.params) if self.params else {},
            "builtin": self.builtin,
        }

    def get_params(self) -> dict:
        result: dict = json.loads(self.params) if self.params else {}
        return result

    def set_params(self, params: dict) -> None:
        self.params = json.dumps(params, ensure_ascii=False)
