from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import Tender


class ConnectorError(RuntimeError): pass


class Connector(ABC):
    def __init__(self, source: dict): self.source = source
    @property
    def name(self) -> str: return self.source["name"]
    @abstractmethod
    def fetch(self, since: datetime) -> list[Tender]: ...
