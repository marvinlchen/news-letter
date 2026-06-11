from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class Article:
    article_id: str
    title: str
    url: str
    source: str
    published_at: datetime
    description: str
    category: str
    source_weight: int
    score: float = 0.0
    cluster_size: int = 1

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["published_at"] = self.published_at.isoformat()
        return value

