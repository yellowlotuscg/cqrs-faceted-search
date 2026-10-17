import re
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select, text

from .models import IndexState, Manual, OutboxEvent, SearchEntry, Section


class SQLiteFTS5ReadAdapter:
    """Local read adapter backed by SQLite FTS5 and SearchEntry metadata."""

    def __init__(self, db):
        self.db = db

    def current_version(self, session) -> str:
        state = session.get(IndexState, "live_index")
        if state is None:
            version = str(uuid.uuid4())
            session.add(IndexState(key="live_index", value=version))
            return version
        return state.value

    def _remove_entry(self, session, entry: SearchEntry) -> None:
        session.execute(
            text("INSERT INTO search_fts(search_fts, rowid, text) VALUES ('delete', :id, '')"),
            {"id": entry.id},
        )
        session.delete(entry)

    def upsert_section(
        self,
        session,
        manual: Manual,
        section: Section,
        source_event_id: str,
        index_version: str | None = None,
    ) -> None:
        version = index_version or self.current_version(session)
        prior = session.scalar(
            select(SearchEntry).where(
                SearchEntry.index_version == version, SearchEntry.section_id == section.id
            )
        )
        if prior is not None:
            self._remove_entry(session, prior)
            session.flush()
        if manual.retired:
            return
        entry = SearchEntry(
            index_version=version,
            manual_id=manual.id,
            section_id=section.id,
            section_title=section.title,
            text=section.body,
            category=manual.category,
            manufacturer=manual.manufacturer.name,
            year=manual.year,
            doc_type=manual.doc_type,
            ingest_version=manual.version,
            source_event_id=source_event_id,
            retired=manual.retired,
        )
        session.add(entry)
        session.flush()
        session.execute(
            text("INSERT INTO search_fts(rowid, text) VALUES (:id, :body)"),
            {"id": entry.id, "body": section.body},
        )

    def remove_manual(self, session, manual_id: str) -> None:
        version = self.current_version(session)
        entries = session.scalars(
            select(SearchEntry).where(
                SearchEntry.index_version == version, SearchEntry.manual_id == manual_id
            )
        ).all()
        for entry in entries:
            self._remove_entry(session, entry)

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return re.findall(r"[\w-]+", query.lower())

    def search(
        self,
        *,
        q: str = "",
        category: str | None = None,
        manufacturer: str | None = None,
        year: int | None = None,
        doc_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, page)
        with self.db.session() as session:
            version = self.current_version(session)
            conditions = [SearchEntry.index_version == version, SearchEntry.retired.is_(False)]
            if category:
                conditions.append(SearchEntry.category == category)
            if manufacturer:
                conditions.append(SearchEntry.manufacturer == manufacturer)
            if year is not None:
                conditions.append(SearchEntry.year == year)
            if doc_type:
                conditions.append(SearchEntry.doc_type == doc_type)
            ids: list[int] | None = None
            tokens = self._tokens(q)
            if tokens:
                match = " AND ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
                rows = session.execute(
                    text(
                        "SELECT rowid FROM search_fts WHERE search_fts MATCH :match ORDER BY rank"
                    ),
                    {"match": match},
                ).all()
                ids = [row[0] for row in rows]
                conditions.append(SearchEntry.id.in_(ids or [-1]))
            entries = session.scalars(
                select(SearchEntry)
                .where(*conditions)
                .order_by(SearchEntry.manual_id, SearchEntry.section_id)
            ).all()
            total = len(entries)
            start = (page - 1) * page_size
            selected = entries[start : start + page_size]
            facets = {}
            for field in ("category", "manufacturer", "year", "doc_type"):
                counts = Counter(getattr(entry, field) for entry in entries)
                facets[field] = [
                    {"value": key, "count": counts[key]} for key in sorted(counts, key=str)
                ]
            hits = []
            for entry in selected:
                offset_start, offset_end = self._provenance(entry.text, tokens)
                hits.append(
                    {
                        "manual_id": entry.manual_id,
                        "section_id": entry.section_id,
                        "section_title": entry.section_title,
                        "title": entry.section_title,
                        "snippet": entry.text[offset_start:offset_end],
                        "text": entry.text,
                        "category": entry.category,
                        "manufacturer": entry.manufacturer,
                        "year": entry.year,
                        "doc_type": entry.doc_type,
                        "provenance": {
                            "manual_id": entry.manual_id,
                            "section_id": entry.section_id,
                            "section_title": entry.section_title,
                            "char_offset_start": offset_start,
                            "char_offset_end": offset_end,
                            "ingest_version": entry.ingest_version,
                            "source_event_id": entry.source_event_id,
                        },
                    }
                )
            return {
                "query": q,
                "page": page,
                "page_size": page_size,
                "total": total,
                "hits": hits,
                "facets": facets,
                "index_version": version,
            }

    @staticmethod
    def _provenance(body: str, tokens: list[str]) -> tuple[int, int]:
        if not tokens:
            return 0, min(len(body), 240)
        positions = [(body.lower().find(token), token) for token in tokens]
        positions = [(pos, token) for pos, token in positions if pos >= 0]
        if not positions:
            return 0, min(len(body), 240)
        start, token = min(positions, key=lambda item: item[0])
        return start, start + len(token)


class AzureSearchReadAdapter:
    """Production adapter; imports Azure SDKs only when this adapter is constructed."""

    def __init__(self, endpoint: str, index_name: str):
        from azure.identity import DefaultAzureCredential
        from azure.search.documents import SearchClient

        self.client = SearchClient(endpoint, index_name, DefaultAzureCredential())

    def search(self, **kwargs):
        query = kwargs.get("q") or "*"
        return self.client.search(search_text=query, top=kwargs.get("page_size", 20))


class Projector:
    def __init__(self, db, adapter: SQLiteFTS5ReadAdapter | None = None):
        self.db = db
        self.adapter = adapter or SQLiteFTS5ReadAdapter(db)

    def dispatch_pending(self, limit: int = 1000) -> int:
        count = 0
        with self.db.session() as session:
            events = session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.dispatched.is_(False))
                .order_by(OutboxEvent.id)
                .limit(limit)
            ).all()
            for event in events:
                self.apply_event(session, event)
                event.dispatched = True
                count += 1
        return count

    def apply_event(self, session, event: OutboxEvent, version: str | None = None) -> None:
        payload = event.payload
        manual = session.scalar(select(Manual).where(Manual.id == payload["manual_id"]))
        if manual is None:
            return
        if version is not None:
            original = session.get(IndexState, "live_index")
            old = original.value if original else None
            if original:
                original.value = version
            else:
                session.add(IndexState(key="live_index", value=version))
        try:
            if event.event_type == "ManualRetired":
                self.adapter.remove_manual(session, manual.id)
            else:
                sections = session.scalars(
                    select(Section).where(Section.manual_id == manual.id).order_by(Section.position)
                ).all()
                for section in sections:
                    self.adapter.upsert_section(session, manual, section, event.event_id)
        finally:
            if version is not None:
                state = session.get(IndexState, "live_index")
                if state is not None:
                    state.value = old or version
