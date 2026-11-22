import logging
from datetime import date, timedelta
from sqlalchemy import and_, or_, select
from src.config.database import Session
from src.constants.enums import Status
from src.domain.analysis import analyze
from src.domain.spec import KIND_TRACE, SPEC
from src.domain import trace
from src.models.jobs import Delivery, Run, Schedule
from src.models.source import Dataset
from src.services.audit import record
from src.utils.exports import write_report
from src.utils.time import now

log = logging.getLogger(__name__)


def _latest_dataset(db, schedule):
    same_kind = select(Dataset.id).where(Dataset.kind == schedule.kind).order_by(Dataset.id.desc()).limit(1)
    return db.scalar(same_kind) or schedule.dataset_id


def materialize_due():
    if not SPEC.get('scheduled'):
        return
    stamp = now()
    with Session.begin() as db:
        schedules = db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_at <= stamp)
                                .order_by(Schedule.next_at).limit(20).with_for_update(skip_locked=True))
        for item in schedules:
            due = item.next_at
            dataset_id = item.dataset_id
            params = dict(item.params)
            if item.repeat_daily:
                elapsed_days = (stamp - due).days
                due += timedelta(days=elapsed_days)
                period_key = SPEC['schedule_date_param']
                report_day = date.fromisoformat(params[period_key]) + timedelta(days=elapsed_days)
                params[period_key] = report_day.isoformat()
                item.params = {**params, period_key: (report_day + timedelta(days=1)).isoformat()}
                dataset_id = _latest_dataset(db, item)
                item.next_at = due + timedelta(days=1)
            else:
                item.enabled = False
            db.add(Run(dataset_id=dataset_id, schedule_id=item.id, scheduled_at=due, kind=item.kind,
                       name=item.name, params=params, author=item.author))


def claim():
    stamp = now()
    with Session.begin() as db:
        query = select(Run).where(or_(Run.status == Status.QUEUED,
                                      and_(Run.status == Status.RUNNING, Run.lease_until < stamp)))
        job = db.scalar(query.order_by(Run.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        if job.attempt >= 3:
            job.status = Status.FAILED
            job.error = '后台进程多次中断，请发起新的运行'
            job.finished_at = stamp
            record(db, 'worker', 'analysis.failed', job.id, reason=job.error)
            return None
        job.status = Status.RUNNING
        job.attempt += 1
        job.lease_until = stamp + timedelta(minutes=3)
        dataset = db.get(Dataset, job.dataset_id)
        previous = None
        if job.kind == KIND_TRACE:
            if job.previous_run_id is None:
                # 不指定对比结果时按同一报告日的上一次追溯增量计算；换了报告日就全量计算。
                same_day = _last_complete_trace(db, job, same_report_day=True)
                job.previous_run_id = same_day.id if same_day else None
            prior = db.get(Run, job.previous_run_id) if job.previous_run_id else None
            if prior and prior.id != job.id and prior.status == Status.COMPLETE:
                previous = {
                    'rows': db.get(Dataset, prior.dataset_id).rows,
                    'params': dict(prior.params),
                }
        return job.id, job.attempt, dataset.rows, job.params, job.kind, previous


def _last_complete_trace(db, job, same_report_day=False):
    query = select(Run).where(Run.kind == KIND_TRACE, Run.status == Status.COMPLETE, Run.id < job.id)
    if same_report_day:
        query = query.where(Run.params['report_day'].as_string() == job.params.get('report_day'))
    return db.scalar(query.order_by(Run.id.desc()).limit(1))


def execute(lease):
    job_id, attempt, rows, params, kind, previous = lease
    result = export = failure = None
    try:
        if kind == KIND_TRACE:
            result = trace.analyze(rows, params, previous_rows=(previous or {}).get('rows'),
                                   previous_params=(previous or {}).get('params'))
        else:
            result = analyze(rows, params)
        export = write_report(job_id, attempt, result)
    except ValueError as error:
        failure = str(error)[:500]
    except Exception:
        log.exception('Analysis %s failed', job_id)
        failure = '计算失败，请检查字段口径后重试'
    with Session.begin() as db:
        job = db.get(Run, job_id, with_for_update=True)
        if job.attempt != attempt or job.status != Status.RUNNING:
            return
        job.lease_until = None
        job.finished_at = now()
        job.status = Status.FAILED if failure else Status.COMPLETE
        job.result = None if failure else result
        job.export_file = export
        job.error = failure
        record(db, 'worker', f'analysis.{job.status}', job.id, attempt=attempt, reason=failure)
        if job.schedule_id:
            plan = db.get(Schedule, job.schedule_id)
            ready = not failure and result.get('ready', True)
            detail = '已保存 CSV 到站内收件箱' if ready else (failure or result['headline'])
            receipt = Delivery(run_id=job.id, recipient=plan.recipient, state='delivered' if ready else 'blocked', detail=detail[:500])
            db.add(receipt)
            record(db, 'worker', f'delivery.{receipt.state}', job.id, recipient=plan.recipient)
