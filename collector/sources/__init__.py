from .base import Source
from .good_antiques import GoodAntiques
from .municipal_rss import MunicipalRSS

REGISTRY = {GoodAntiques.name: GoodAntiques}

__all__ = ["Source", "GoodAntiques", "MunicipalRSS", "REGISTRY"]
