import threading

import pytest

from catalog.commands import CommandService
from catalog.db import Database
from catalog.models import SearchEntry
from catalog.read_model import Projector, SQLiteFTS5ReadAdapter
from catalog.system import Catalog, RebuildError


def make_catalog(tmp_path):
    return Catalog(Database(f"sqlite:///{tmp_path / 'test.db'}"))


def create(catalog, text="The isolation alarm requires a frame check.", category="pumps"):
    return catalog.create_manual(
        title="Synthetic pump manual",
        category=category,
        manufacturer="Acme Industrial",
        year=2024,
        doc_type="service manual",
        sections=[
            {"title": "Safety", "body": text},
            {"title": "Specifications", "body": "480 volt input."},
        ],
    )


def test_command_event_projection(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'events.db'}")
    commands = CommandService(db)
    manual = commands.create_manual(
        title="Manual",
        category="pumps",
        manufacturer="Acme Industrial",
        year=2024,
        doc_type="installation guide",
        sections=[{"title": "Safety", "body": "isolation step"}],
    )
    projector = Projector(db)
    assert projector.dispatch_pending() == 1
    result = SQLiteFTS5ReadAdapter(db).search(q="isolation")
    assert result["total"] == 1
    assert result["hits"][0]["manual_id"] == manual.id


def test_facets_and_exact_provenance(tmp_path):
    catalog = make_catalog(tmp_path)
    manual = create(catalog, "Always isolate the pump before maintenance.")
    hit = SQLiteFTS5ReadAdapter(catalog.db).search(q="isolate")["hits"][0]
    provenance = hit["provenance"]
    assert hit["text"][provenance["char_offset_start"] : provenance["char_offset_end"]] == "isolate"
    assert hit["manual_id"] == manual.id
    assert hit["section_id"] == provenance["section_id"]
    assert hit["section_title"] == "Safety"
    assert hit["provenance"]["source_event_id"]
    categories = SQLiteFTS5ReadAdapter(catalog.db).search()["facets"]["category"]
    assert {facet["value"] for facet in categories} == {"pumps"}


def test_rebuild_consistency_and_tamper_detection(tmp_path):
    catalog = make_catalog(tmp_path)
    create(catalog)
    report = catalog.index_manager.rebuild()
    assert report["documents"] >= 2
    version = report["version"]
    with catalog.db.session() as session:
        entry = session.query(SearchEntry).filter_by(index_version=version).first()
        entry.text = "tampered"
    with pytest.raises(RebuildError):
        catalog.index_manager.consistency_check(version)


def test_writes_succeed_during_rebuild(tmp_path):
    catalog = make_catalog(tmp_path)
    create(catalog)
    errors = []

    def writer():
        try:
            create(catalog, "Concurrent generator alarm text.", category="generators")
        except Exception as exc:  # pragma: no cover - assertion reports the real exception
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    report = catalog.index_manager.rebuild()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not errors
    assert report["documents"] >= 2
    assert SQLiteFTS5ReadAdapter(catalog.db).search(q="Concurrent")["total"] == 1


def test_search_pagination(tmp_path):
    catalog = make_catalog(tmp_path)
    for index in range(3):
        create(catalog, f"Unique manual marker {index}.")
    read = SQLiteFTS5ReadAdapter(catalog.db)
    first = read.search(page=1, page_size=2)
    second = read.search(page=2, page_size=2)
    assert first["total"] == 6
    assert len(first["hits"]) == 2
    assert len(second["hits"]) == 2
    assert {hit["section_id"] for hit in first["hits"]}.isdisjoint(
        {hit["section_id"] for hit in second["hits"]}
    )
