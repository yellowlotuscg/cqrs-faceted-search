import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Manual, Manufacturer, OutboxEvent, Section

SECTION_TITLES = ("Safety", "Installation", "Maintenance", "Troubleshooting", "Specifications")


def emit(
    session: Session, event_type: str, aggregate_id: str, payload: dict[str, Any]
) -> OutboxEvent:
    event = OutboxEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


class CommandService:
    def __init__(self, db):
        self.db = db

    def create_manual(
        self,
        *,
        title: str,
        category: str,
        manufacturer: str,
        year: int,
        doc_type: str,
        sections: Iterable[dict[str, str]],
    ) -> Manual:
        manual_id = str(uuid.uuid4())
        with self.db.session() as session:
            maker = session.scalar(select(Manufacturer).where(Manufacturer.name == manufacturer))
            if maker is None:
                maker = Manufacturer(name=manufacturer)
                session.add(maker)
                session.flush()
            manual = Manual(
                id=manual_id,
                title=title,
                category=category,
                year=year,
                doc_type=doc_type,
                manufacturer_id=maker.id,
            )
            session.add(manual)
            normalized = []
            for position, item in enumerate(sections):
                section_id = str(uuid.uuid4())
                section = Section(
                    id=section_id,
                    manual_id=manual_id,
                    title=item["title"],
                    body=item["body"],
                    position=position,
                )
                session.add(section)
                normalized.append({"id": section_id, "title": section.title, "body": section.body})
            session.flush()
            emit(
                session,
                "ManualCreated",
                manual_id,
                {
                    "manual_id": manual_id,
                    "section_ids": [item["id"] for item in normalized],
                    "ingest_version": manual.version,
                },
            )
            return manual

    def update_section(self, manual_id: str, section_id: str, title: str, body: str) -> Section:
        with self.db.session() as session:
            section = session.scalar(
                select(Section).where(Section.id == section_id, Section.manual_id == manual_id)
            )
            if section is None:
                raise KeyError("section not found")
            manual = session.get(Manual, manual_id)
            if manual is None or manual.retired:
                raise KeyError("manual not found")
            section.title = title
            section.body = body
            section.version += 1
            manual.version += 1
            event = emit(
                session,
                "SectionUpdated",
                manual_id,
                {
                    "manual_id": manual_id,
                    "section_id": section_id,
                    "ingest_version": manual.version,
                },
            )
            section._source_event_id = event.event_id
            return section

    def retire_manual(self, manual_id: str) -> None:
        with self.db.session() as session:
            manual = session.get(Manual, manual_id)
            if manual is None:
                raise KeyError("manual not found")
            manual.retired = True
            manual.version += 1
            emit(
                session,
                "ManualRetired",
                manual_id,
                {"manual_id": manual_id, "ingest_version": manual.version},
            )

    def get_manual(self, manual_id: str) -> Manual | None:
        with self.db.session() as session:
            return session.scalar(select(Manual).where(Manual.id == manual_id))
