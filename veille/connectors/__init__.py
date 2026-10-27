from .base import Connector, ConnectorError
from .boamp import BoampConnector
from .feed import FeedConnector
from .ted import TedConnector

CONNECTORS: dict[str, type[Connector]] = {
    "boamp": BoampConnector,
    "ted": TedConnector,
    "feed": FeedConnector,
}

__all__ = ["Connector", "ConnectorError", "BoampConnector", "FeedConnector", "TedConnector", "CONNECTORS"]
