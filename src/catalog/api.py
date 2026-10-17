
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .db import Database, get_database
from .read_model import SQLiteFTS5ReadAdapter
from .system import Catalog


class SectionInput(BaseModel):
    title: str
    body: str = Field(min_length=1)


class ManualInput(BaseModel):
    title: str
    category: str
    manufacturer: str
    year: int
    doc_type: str
    sections: list[SectionInput]


class SectionUpdate(BaseModel):
    title: str
    body: str = Field(min_length=1)


def create_app(db: Database | None = None) -> FastAPI:
    database = db or get_database()
    catalog = Catalog(database)
    search = SQLiteFTS5ReadAdapter(database)
    app = FastAPI(title="CQRS Faceted Search", version="0.1.0")
    app.state.catalog = catalog
    app.state.db = database

    @app.post("/manuals", status_code=201)
    def create_manual(payload: ManualInput):
        manual = catalog.create_manual(
            title=payload.title,
            category=payload.category,
            manufacturer=payload.manufacturer,
            year=payload.year,
            doc_type=payload.doc_type,
            sections=[section.model_dump() for section in payload.sections],
        )
        return {"id": manual.id, "title": manual.title, "status": "accepted"}

    @app.put("/manuals/{manual_id}/sections/{section_id}")
    def update_section(manual_id: str, section_id: str, payload: SectionUpdate):
        try:
            section = catalog.update_section(
                manual_id=manual_id,
                section_id=section_id,
                title=payload.title,
                body=payload.body,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"id": section.id, "version": section.version, "status": "accepted"}

    @app.delete("/manuals/{manual_id}", status_code=204)
    def retire_manual(manual_id: str):
        try:
            catalog.retire_manual(manual_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/search")
    def search_manuals(
        q: str = "",
        category: str | None = None,
        manufacturer: str | None = None,
        year: int | None = None,
        doc_type: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        catalog.dispatch()
        return search.search(
            q=q,
            category=category,
            manufacturer=manufacturer,
            year=year,
            doc_type=doc_type,
            page=page,
            page_size=page_size,
        )

    @app.post("/admin/rebuild")
    def rebuild():
        return catalog.index_manager.rebuild()

    return app


app = create_app()
