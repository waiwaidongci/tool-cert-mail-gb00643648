import csv
import hashlib
import io
import json
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.domain.demo import demo_rows, demo_trace_rows
from src.domain.spec import KIND_CERTIFICATE, KIND_TRACE, SPEC, TRACE_FIELDS
from src.models.source import Dataset


def checksum(rows):
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def save(db, name, filename, rows, actor, kind=KIND_CERTIFICATE):
    signature = checksum(rows)
    lookup = select(Dataset).where(Dataset.name == name, Dataset.checksum == signature)
    existing = db.scalar(lookup)
    if existing:
        return existing, False
    dataset = Dataset(name=name, filename=filename, checksum=signature, rows=rows,
                      row_count=len(rows), kind=kind, author=actor)
    try:
        with db.begin_nested():
            db.add(dataset)
            db.flush()
    except IntegrityError:
        existing = db.scalar(lookup.with_for_update())
        if existing:
            return existing, False
        raise
    return dataset, True


def _render(fields, rows):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=[field['key'] for field in fields], extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return '﻿' + buffer.getvalue()


def template():
    # The complete representative dataset also works as a reproducible import fixture.
    return _render(SPEC['fields'], demo_rows())


def trace_template(version='baseline'):
    return _render(TRACE_FIELDS, demo_trace_rows(version))
