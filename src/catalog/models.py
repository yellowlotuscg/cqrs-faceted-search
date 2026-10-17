from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    manuals: Mapped[list["Manual"]] = relationship(back_populates="manufacturer")


class Manual(Base):
    __tablename__ = "manuals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(80), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    doc_type: Mapped[str] = mapped_column(String(80), index=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"), index=True)
    retired: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    manufacturer: Mapped[Manufacturer] = relationship(back_populates="manuals")
    sections: Mapped[list["Section"]] = relationship(
        back_populates="manual", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manual_id: Mapped[str] = mapped_column(ForeignKey("manuals.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    manual: Mapped[Manual] = relationship(back_populates="sections")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class IndexState(Base):
    __tablename__ = "index_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(120))


class SearchEntry(Base):
    __tablename__ = "search_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_version: Mapped[str] = mapped_column(String(36), index=True)
    manual_id: Mapped[str] = mapped_column(String(36), index=True)
    section_id: Mapped[str] = mapped_column(String(36), index=True)
    section_title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), index=True)
    manufacturer: Mapped[str] = mapped_column(String(120), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    doc_type: Mapped[str] = mapped_column(String(80), index=True)
    ingest_version: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[str] = mapped_column(String(36))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("index_version", "section_id"),)
