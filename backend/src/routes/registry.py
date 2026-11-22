from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.spec import KIND_CERTIFICATE, KIND_TRACE, SPEC
from src.models.identity import User
from src.models.source import Dataset
from src.schemas.requests import Upload
from src.services.audit import record
from src.services.datasets import save, template, trace_template
from src.services.validation import parse_rows
from src.utils import views

router = APIRouter()


@router.get('/spec')
def spec():
    return {key: value for key, value in SPEC.items() if key != 'fixture'}


@router.get('/template')
def sample(kind: str = KIND_CERTIFICATE, version: str = 'baseline', actor: User = Depends(current)):
    if kind == KIND_TRACE:
        if version not in ('baseline', 'correction'):
            raise HTTPException(404, '找不到该追溯模板版本')
        body, filename = trace_template(version), SPEC['trace_sample_name']
    else:
        body, filename = template(), SPEC['sample_name']
    return Response(body, media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.get('/datasets')
def datasets(kind: str | None = None, db: Session = Depends(connection), actor: User = Depends(current)):
    query = select(Dataset).order_by(Dataset.id.desc()).limit(100)
    if kind:
        query = query.where(Dataset.kind == kind)
    return [views.dataset(item) for item in db.scalars(query)]


@router.get('/datasets/{dataset_id}')
def details(dataset_id: int, offset: int = Query(0, ge=0), limit: int = Query(16, ge=1, le=100),
            db: Session = Depends(connection), actor: User = Depends(current)):
    item = db.get(Dataset, dataset_id)
    if not item:
        raise HTTPException(404, '找不到该数据批次')
    return {**views.dataset(item), 'rows': item.rows[offset:offset + limit]}


@router.post('/datasets', status_code=201)
def upload(body: Upload, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    rows = parse_rows(body.csv_text, body.kind)
    item, created = save(db, body.name, body.filename, rows, actor.username, body.kind)
    if created:
        record(db, actor.username, 'dataset.imported', item.id, rows=item.row_count, kind=item.kind)
    db.commit()
    return {**views.dataset(item), 'created': created}
