import uuid
import time
import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Payload:
    """Represents the core data embedded in the media."""
    metadata: Dict[str, Any] = field(default_factory=dict)
    media_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    nonce: str = field(default_factory=lambda: os.urandom(8).hex())

    def get_serializable_data(self) -> bytes:
        """Returns deterministic bytes for consistent hashing and signing."""
        data_dict = {
            "media_id": self.media_id,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "metadata": self.metadata
        }
        return json.dumps(data_dict, sort_keys=True).encode('utf-8')