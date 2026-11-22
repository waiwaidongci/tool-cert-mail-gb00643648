import json
from sqlalchemy import func, select
from src.config.database import Session
from src.constants.enums import Role
from src.domain.demo import TRACE_VERSION_NAMES, demo_rows, demo_trace_rows
from src.domain.spec import KIND_CERTIFICATE, KIND_TRACE, SPEC
from src.models.identity import User
from src.models.source import Dataset
from src.services.datasets import save
from src.services.validation import normalize_rows
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role, password_hash=hash_password(f'{role.value}-demo-2611')))
        item, created = save(db, SPEC['default_dataset'], SPEC['sample_name'],
                             normalize_rows(demo_rows(), KIND_CERTIFICATE), 'seed', KIND_CERTIFICATE)
        trace_item, trace_created = save(db, TRACE_VERSION_NAMES['baseline'], SPEC['trace_sample_name'],
                                         normalize_rows(demo_trace_rows('baseline'), KIND_TRACE),
                                         'seed', KIND_TRACE)
        return {'users': db.scalar(select(func.count()).select_from(User)),
                'datasets': db.scalar(select(func.count()).select_from(Dataset)),
                'seed_dataset_id': item.id, 'row_count': item.row_count, 'checksum': item.checksum,
                'created_dataset': created,
                'seed_trace_dataset_id': trace_item.id, 'trace_row_count': trace_item.row_count,
                'created_trace_dataset': trace_created}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
