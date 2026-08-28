"""
Source adapters: each turns one database into canonical assertions.

CONTRACT
--------
An adapter does exactly three things and nothing else:

    is_available()  -> are this source's files present?
    describe()      -> what it provides, its licence, its version
    extract(store)  -> add entities and assertions to a KnowledgeStore

An adapter NEVER:
  * reads the DDI label table (rule 3 of docs/BIOLOGICAL_GRAPH_LEAKAGE.md);
  * invents a confidence a source did not report;
  * merges two sources' assertions about one relation;
  * fabricates a record for a source whose files are absent.

An adapter for a source we do not yet hold is still written: it declares the
schema it expects and refuses to run. That is the difference between
"unimplemented" and "silently returns nothing", and only the first is safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..integration.schema import KnowledgeStore

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"


class SourceUnavailable(FileNotFoundError):
    """The source's files are not present. Carries what to download."""


@dataclass(frozen=True)
class SourceDescription:
    """What an adapter provides, stated before it runs."""

    name: str
    version: str
    licence: str
    #: Human-readable list of relation types this adapter can emit.
    provides: tuple[str, ...]
    #: Files it needs, relative to data/raw/.
    required_files: tuple[str, ...]
    download_url: str = ""
    retrieval_date: date | None = None
    notes: str = ""
    #: Set when the source is known but not yet held. Its extract() must raise.
    is_placeholder: bool = False


@runtime_checkable
class Adapter(Protocol):
    """The three-method contract every adapter satisfies."""

    def describe(self) -> SourceDescription: ...
    def is_available(self) -> bool: ...
    def extract(self, store: KnowledgeStore, **kwargs) -> KnowledgeStore: ...


@dataclass
class BaseAdapter:
    """Shared plumbing. Subclasses supply `describe` and `_extract`."""

    directory: Path | None = None
    _description: SourceDescription | None = field(default=None, init=False)

    def describe(self) -> SourceDescription:  # pragma: no cover - overridden
        raise NotImplementedError

    def base_dir(self) -> Path:
        return self.directory or RAW_DIR

    def missing_files(self) -> list[Path]:
        base = self.base_dir()
        return [base / f for f in self.describe().required_files
                if not (base / f).exists()]

    def is_available(self) -> bool:
        desc = self.describe()
        return not desc.is_placeholder and not self.missing_files()

    def require(self) -> None:
        """Raise with instructions rather than failing deep inside a parser."""
        desc = self.describe()
        if desc.is_placeholder:
            raise SourceUnavailable(
                f"{desc.name}: adapter is an interface only - this source has "
                f"not been obtained yet. Expected files: "
                f"{', '.join(desc.required_files)}. "
                + (f"Download: {desc.download_url}" if desc.download_url else "")
            )
        missing = self.missing_files()
        if missing:
            raise SourceUnavailable(
                f"{desc.name}: missing {', '.join(str(p) for p in missing)}. "
                + (f"Download: {desc.download_url}" if desc.download_url else "")
            )

    def extract(self, store: KnowledgeStore, **kwargs) -> KnowledgeStore:
        self.require()
        return self._extract(store, **kwargs)

    def _extract(self, store: KnowledgeStore, **kwargs) -> KnowledgeStore:
        raise NotImplementedError
