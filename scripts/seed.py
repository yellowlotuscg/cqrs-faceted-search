#!/usr/bin/env python3
"""Seed a deterministic synthetic catalog of invented industrial equipment manuals."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from catalog.db import Database
from catalog.system import Catalog

SEED = 20250301
MANUFACTURERS = ["Acme Industrial", "Contoso Machinery", "Fabrikam Tools", "Northstar Fabrication"]
CATEGORIES = ["pumps", "compressors", "conveyors", "HVAC units", "forklifts", "generators"]
DOC_TYPES = ["installation guide", "service manual", "parts list", "safety bulletin"]


def make_sections(rng: random.Random, category: str, model: str):
    return [
        {
            "title": "Safety",
            "body": f"{model} {category} safety requires an isolation check before service. "
            f"Use the marked guard points and verify the emergency stop indicator.",
        },
        {
            "title": "Installation",
            "body": f"Install {model} on the specified mounting frame for {category} equipment. "
            "Connect the service lines, align the drive, and record the commissioning value.",
        },
        {
            "title": "Maintenance",
            "body": f"Inspect {model} {category} assemblies every 500 operating hours. "
            "Clean the filter, inspect fasteners, and log the measured service value.",
        },
        {
            "title": "Troubleshooting",
            "body": (
                f"If {model} shows an alarm, stop the unit and inspect the "
                f"{category} control path. Compare the corrective action table."
            ),
        },
        {
            "title": "Specifications",
            "body": f"{model} {category} specification values include a 480 volt input and a "
            "nominal 60 hertz operating range. See the rating plate for the configured value.",
        },
    ]


def seed(url="sqlite:///./catalog.db", count=300):
    rng = random.Random(SEED)
    catalog = Catalog(Database(url))
    for number in range(count):
        category = rng.choice(CATEGORIES)
        manufacturer = rng.choice(MANUFACTURERS)
        doc_type = rng.choice(DOC_TYPES)
        year = rng.randint(2018, 2025)
        model = f"{manufacturer.split()[0].upper()}-{category[:3].upper()}-{number:04d}"
        catalog.create_manual(
            title=f"{model} {category.title()} Manual",
            category=category,
            manufacturer=manufacturer,
            year=year,
            doc_type=doc_type,
            sections=make_sections(rng, category, model),
        )
    print(f"seeded {count} synthetic manuals with seed {SEED}")


if __name__ == "__main__":
    seed()
