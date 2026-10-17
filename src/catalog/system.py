import threading
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import delete, select, text

from .commands import CommandService
from .models import IndexState, Manual, OutboxEvent, SearchEntry, Section
from .read_model import Projector, SQLiteFTS5ReadAdapter


class RebuildError(RuntimeError):
    pass


class IndexManager:
    def __init__(self, db, projector: Projector):
        self.db = db
        self.projector = projector
        self.adapter = projector.adapter
        self.lock = threading.RLock()

    def _version(self) -> str:
        return str(uuid.uuid4())

    def _populate(self, version: str) -> None:
        with self.db.session() as session:
            manuals = session.scalars(select(Manual).where(Manual.retired.is_(False))).all()
            for manual in manuals:
                sections = session.scalars(
                    select(Section).where(Section.manual_id == manual.id).order_by(Section.position)
                ).all()
                event = session.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == manual.id)
                    .order_by(OutboxEvent.id.desc())
                )
                source_event_id = event.event_id if event else "rebuild"
                for section in sections:
                    self.adapter.upsert_section(
                        session, manual, section, source_event_id, index_version=version
                    )

    def _clear_version(self, version: str) -> None:
        with self.db.session() as session:
            entries = session.scalars(
                select(SearchEntry).where(SearchEntry.index_version == version)
            ).all()
            for entry in entries:
                session.execute(
                    text(
                        "INSERT INTO search_fts(search_fts, rowid, text) "
                        "VALUES ('delete', :id, '')"
                    ),
                    {"id": entry.id},
                )
            session.execute(delete(SearchEntry).where(SearchEntry.index_version == version))

    def consistency_check(self, version: str, sample_size: int = 20) -> dict[str, Any]:
        with self.db.session() as session:
            manuals = session.scalars(select(Manual).where(Manual.retired.is_(False))).all()
            expected_sections = sum(len(manual.sections) for manual in manuals)
            entries = session.scalars(
                select(SearchEntry).where(SearchEntry.index_version == version)
            ).all()
            if len(entries) != expected_sections:
                raise RebuildError(
                    f"document count mismatch: index={len(entries)} "
                    f"write={expected_sections}"
                )
            actual_manuals = {entry.manual_id for entry in entries}
            if len(actual_manuals) != len(manuals):
                raise RebuildError(
                    f"manual count mismatch: index={len(actual_manuals)} write={len(manuals)}"
                )
            expected_facets = {
                key: Counter(
                    (manual.manufacturer.name if key == "manufacturer" else getattr(manual, key))
                    for manual in manuals
                    for _section in manual.sections
                )
                for key in ("category", "manufacturer", "year", "doc_type")
            }
            actual_facets = {
                key: Counter(getattr(entry, key) for entry in entries)
                for key in ("category", "manufacturer", "year", "doc_type")
            }
            if expected_facets != actual_facets:
                raise RebuildError("facet counts do not match the write model")
            for entry in entries[:sample_size]:
                section = session.get(Section, entry.section_id)
                if section is None or section.body != entry.text:
                    raise RebuildError(f"provenance text mismatch for section {entry.section_id}")
                tokens = self.adapter._tokens(entry.text[:80])
                start, end = self.adapter._provenance(entry.text, tokens)
                if section.body[start:end] != entry.text[start:end]:
                    raise RebuildError(f"invalid provenance offsets for section {entry.section_id}")
            return {"version": version, "documents": len(entries), "facets": actual_facets}

    def rebuild(self) -> dict[str, Any]:
        version = self._version()
        self._populate(version)
        # The short critical section snapshots writes and swaps atomically.
        # Writes use the same lock.
        with self.lock:
            self._clear_version(version)
            self._populate(version)
            report = self.consistency_check(version)
            with self.db.session() as session:
                state = session.get(IndexState, "live_index")
                if state is None:
                    session.add(IndexState(key="live_index", value=version))
                else:
                    state.value = version
        return report


class Catalog:
    def __init__(self, db):
        self.db = db
        self.projector = Projector(db, SQLiteFTS5ReadAdapter(db))
        self.index_manager = IndexManager(db, self.projector)
        self.commands = CommandService(db)

    def create_manual(self, **kwargs):
        with self.index_manager.lock:
            manual = self.commands.create_manual(**kwargs)
            self.projector.dispatch_pending()
            return manual

    def update_section(self, **kwargs):
        with self.index_manager.lock:
            section = self.commands.update_section(**kwargs)
            self.projector.dispatch_pending()
            return section

    def retire_manual(self, manual_id: str):
        with self.index_manager.lock:
            self.commands.retire_manual(manual_id)
            self.projector.dispatch_pending()

    def dispatch(self):
        with self.index_manager.lock:
            return self.projector.dispatch_pending()
