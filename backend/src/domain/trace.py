"""超差追溯：从上次合格证书倒查检验批次，沿混批/拆批追到出货。

纯函数实现，不依赖数据库，便于在 worker 之外单独校验口径。
"""

import json
from collections import defaultdict
from datetime import datetime

from .spec import (
    CAL_OUT, CAL_PASS, CERTIFICATE, FLOW, INSPECTION, INSTRUMENT, SHIPMENT,
    TRACE_ACTIVE, TRACE_VOID,
)

MAX_PATHS = 200
MAX_DEPTH = 16
DT_MIN = datetime.min

STATUS_SHIPPED = '已出货'
STATUS_FLOWING = '已流转'
STATUS_PENDING = '待核实'

_REQUIRED_FOR = {
    INSTRUMENT: ('asset_id',),
    CERTIFICATE: ('asset_id', 'certificate_id', 'issued_on'),
    INSPECTION: ('asset_id',),
    FLOW: ('parent_batch_id', 'batch_id'),
    SHIPMENT: ('batch_id',),
}
_REQUIRED_LABEL = {
    'asset_id': '器具编号', 'certificate_id': '证书编号', 'issued_on': '签发日',
    'parent_batch_id': '上游批次号', 'batch_id': '批次号',
}


def _as_dt(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace(' ', 'T')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _as_day(value):
    parsed = _as_dt(value)
    return parsed.date() if parsed else None


def _iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec='seconds')
    return value.isoformat()


def _fingerprint(row):
    """比对记录版本时统一空值与时间格式，避免导入批次与历史批次仅因写法不同被判为变更。"""
    canonical = {}
    for key, value in row.items():
        if key.startswith('_'):
            continue
        if isinstance(value, str):
            value = value.strip() or None
        if key in ('inspected_on', 'event_at', 'recorded_at', 'shipped_on'):
            value = _iso(_as_dt(value))
        elif key in ('stopped_on', 'issued_on', 'expires_on'):
            day = _as_day(value)
            value = day.isoformat() if day else None
        canonical[key] = value
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def validate_rows(rows):
    """结构校验：只拒绝无法追溯的数据，业务缺口留给结果标待核实。"""
    seen = defaultdict(list)
    for index, row in enumerate(rows, start=2):
        record_id = (row.get('record_id') or '').strip()
        if not record_id:
            raise ValueError(f'第 {index} 行 · 记录编号不能为空')
        kind = row.get('record_type')
        if kind not in _REQUIRED_FOR:
            raise ValueError(f'第 {index} 行 · 记录类型须为器具台账、校准证书、检验记录、流转记录或出货记录')
        status = row.get('record_status') or TRACE_ACTIVE
        if status not in (TRACE_ACTIVE, TRACE_VOID):
            raise ValueError(f'第 {index} 行 · 记录状态须为有效或作废')
        if status != TRACE_VOID:
            for key in _REQUIRED_FOR[kind]:
                if not str(row.get(key) or '').strip():
                    raise ValueError(f'第 {index} 行 · {kind}缺少{_REQUIRED_LABEL[key]}')
        if kind == CERTIFICATE:
            issued, expires = _as_dt(row.get('issued_on')), _as_dt(row.get('expires_on'))
            if issued and expires and expires < issued:
                raise ValueError(f'第 {index} 行 · 证书 {row.get("certificate_id")} 的到期日早于签发日')
            result = row.get('calibration_result') or CAL_PASS
            if result not in (CAL_PASS, CAL_OUT):
                raise ValueError(f'第 {index} 行 · 校准结果须为合格或超差')
        for key, label in (('inspected_on', '检验时间'), ('event_at', '实际流转时间'),
                           ('shipped_on', '出货时间'), ('recorded_at', '登记时间'),
                           ('stopped_on', '停用日期'), ('issued_on', '签发日'), ('expires_on', '到期日')):
            if row.get(key) and _as_dt(row.get(key)) is None:
                raise ValueError(f'第 {index} 行 · {label}格式不正确')
        seen[record_id].append(row)
    for record_id, versions in seen.items():
        if len(versions) < 2:
            continue
        stamps = [row.get('recorded_at') for row in versions]
        if any(not stamp for stamp in stamps) or len(set(stamps)) != len(stamps):
            raise ValueError(f'记录 {record_id} 有多个版本，请用不同的登记时间区分先后')


def _effective(rows):
    """同一记录编号取登记时间最晚的版本；最终版本为作废则该记录不参与追溯。"""
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row['record_id']].append((index, row))
    effective = []
    for record_id, versions in grouped.items():
        index, row = max(versions, key=lambda pair: (_as_dt(pair[1].get('recorded_at')) or DT_MIN, pair[0]))
        if (row.get('record_status') or TRACE_ACTIVE) == TRACE_VOID:
            continue
        item = dict(row)
        item['_index'] = index
        effective.append(item)
    return effective


def _prepare(rows):
    effective = _effective(rows)
    prep = {
        'instruments': {}, 'certs': defaultdict(list), 'inspections': defaultdict(list),
        'edges': defaultdict(list), 'incoming': defaultdict(list), 'shipments': {},
        'records': {}, 'rows': {}, 'flags': [],
    }
    shipments = {}
    seen_cert = defaultdict(list)

    def flag(kind, target, detail):
        prep['flags'].append({'object': target, 'type': kind, 'detail': detail})

    for row in effective:
        record_id = row['record_id']
        prep['rows'][record_id] = row
        prep['records'][record_id] = _fingerprint(row)
        kind = row['record_type']

        if kind == INSTRUMENT:
            asset = row['asset_id']
            current = prep['instruments'].get(asset)
            if current and row['_index'] < current['_index']:
                continue
            prep['instruments'][asset] = {
                'asset_id': asset, 'asset_name': row.get('asset_name'),
                'work_area': row.get('work_area'), 'owner': row.get('owner'),
                'asset_status': row.get('asset_status'),
                'stopped_on': _as_day(row.get('stopped_on')),
                'record_id': record_id, '_index': row['_index'],
            }

        elif kind == CERTIFICATE:
            asset = row['asset_id']
            seen_cert[(asset, row.get('certificate_id'))].append({
                'record_id': record_id, 'asset_id': asset,
                'certificate_id': row.get('certificate_id'),
                'issued': _as_day(row.get('issued_on')),
                'expires': _as_day(row.get('expires_on')),
                'result': row.get('calibration_result') or CAL_PASS,
            })

        elif kind == INSPECTION:
            at = _as_dt(row.get('inspected_on'))
            batch = (row.get('batch_id') or '').strip() or None
            item = {
                'record_id': record_id, 'asset_id': row.get('asset_id'), 'batch_id': batch,
                'at': at, 'recorded_at': _as_dt(row.get('recorded_at')),
                'note': row.get('note'),
            }
            if at is None:
                item['pending'] = f'检验批次 {batch or "（空）"} 缺少检验时间，无法确定倒查窗口'
            if batch is None:
                item['pending'] = '检验记录缺少批次号，无法向下游追溯'
            if item.get('pending'):
                flag('检验记录', record_id, f'{item["pending"]}，标待核实')
            prep['inspections'][row['asset_id']].append(item)

        elif kind == FLOW:
            parent = (row.get('parent_batch_id') or '').strip()
            child = (row.get('batch_id') or '').strip()
            recorded = _as_dt(row.get('recorded_at'))
            event = _as_dt(row.get('event_at'))
            if not parent or not child:
                flag('流转记录', record_id, '流转记录缺少上游或下游批次，已跳过该路径')
                continue
            if parent == child:
                flag('流转记录', record_id, '流转记录上下游批次相同，已跳过该路径')
                continue
            late = bool(recorded and event and recorded.date() > event.date())
            if event is None:
                event = recorded
                flag('流转记录', record_id, f'{parent} → {child} 缺少实际流转时间，暂按登记时间接续并标待核实')
            edge = {
                'record_id': record_id, 'parent': parent, 'batch': child,
                'event_at': event, 'recorded_at': recorded, 'late': late,
                '_order': event or DT_MIN,
            }
            prep['edges'][parent].append(edge)
            prep['incoming'][child].append(edge)

        elif kind == SHIPMENT:
            batch = (row.get('batch_id') or '').strip()
            if not batch:
                flag('出货记录', record_id, '出货记录缺少批次号，无法归属，标待核实')
                continue
            key = (row.get('shipment_id') or record_id).strip()
            entry = shipments.setdefault(key, {
                'key': key, 'shipment_id': key, 'batches': set(), 'destinations': [],
                'shipped_on': None, 'record_ids': [], 'flags': [],
            })
            entry['batches'].add(batch)
            entry['record_ids'].append(record_id)
            destination = (row.get('destination') or '').strip()
            if destination:
                entry['destinations'].append(destination)
            shipped = _as_dt(row.get('shipped_on'))
            if shipped and (entry['shipped_on'] is None or shipped < entry['shipped_on']):
                entry['shipped_on'] = shipped

    for (asset, certificate_id), versions in seen_cert.items():
        kept = max(versions, key=lambda cert: (cert['issued'] or DT_MIN.date(), cert['record_id']))
        prep['certs'][asset].append(kept)
        if len(versions) > 1:
            flag('校准证书', certificate_id, '同一证书编号存在多条记录，按最新签发日采纳一条')
    for parent, edges in prep['edges'].items():
        edges.sort(key=lambda edge: (edge['_order'], edge['record_id']))
    for child, edges in prep['incoming'].items():
        edges.sort(key=lambda edge: (edge['_order'], edge['record_id']))

    for entry in shipments.values():
        destinations = sorted(set(entry['destinations']))
        entry['destinations'] = destinations
        if not destinations:
            flag('出货记录', entry['shipment_id'], '出货单缺少去向，去向断档，标待核实')
            entry['flags'].append('缺少出货去向')
        if len(destinations) > 1:
            flag('出货记录', entry['shipment_id'], '同一出货单登记了多个去向，标待核实')
            entry['flags'].append('去向不一致')
        if entry['shipped_on'] is None:
            entry['flags'].append('缺少出货时间')
    prep['shipments'] = shipments
    return prep


def _reach(roots, edges, incoming):
    """从倒查批次出发枚举下游路径；流转顺序按实际流转时间接续。"""
    discovered = {}
    truncated = False

    def walk(batch, path, visited):
        nonlocal truncated
        entry = discovered.setdefault(batch, {'batch_id': batch, 'paths': set(), 'outgoing': {},
                                              'incoming': {}, 'terminal': True})
        if len(entry['paths']) < MAX_PATHS:
            entry['paths'].add(tuple(edge['record_id'] for edge in path))
        for edge in edges.get(batch, []):
            entry['terminal'] = False
            entry['outgoing'][edge['record_id']] = edge
            if edge['batch'] in visited:
                continue
            if len(path) >= MAX_DEPTH:
                truncated = True
                continue
            walk(edge['batch'], (*path, edge), visited | {edge['batch']})

    for root in sorted(roots):
        walk(root, (), {root})
    for batch, entry in discovered.items():
        for edge in incoming.get(batch, []):
            entry['incoming'][edge['record_id']] = edge
    return discovered, truncated


def _trace_instrument(asset, prep, day):
    certs = [cert for cert in prep['certs'].get(asset, []) if cert['issued'] and cert['issued'] <= day]
    if not certs:
        return None
    latest = max(certs, key=lambda cert: (cert['issued'], cert['certificate_id'] or ''))
    if latest['result'] != CAL_OUT:
        return None
    info = prep['instruments'].get(asset, {})
    passes = [cert for cert in certs if cert['result'] == CAL_PASS and
              (cert['issued'], cert['certificate_id'] or '') < (latest['issued'], latest['certificate_id'] or '')]
    last_pass = max(passes, key=lambda cert: (cert['issued'], cert['certificate_id'] or '')) if passes else None
    stop = info.get('stopped_on') or latest['issued']
    start = last_pass['issued'] if last_pass else None
    flags = []
    if last_pass is None:
        flags.append({'object': asset, 'type': '校准证书',
                      'detail': '未找到上次合格证书，按停用前全部检验批次倒查'})
    if start and stop < start:
        flags.append({'object': asset, 'type': '停用日期', 'detail': '停用日期早于上次合格签发日，倒查窗口为空'})

    inspections, pending, before, after = [], [], 0, 0
    root_times = {}
    for item in prep['inspections'].get(asset, []):
        if item['at'] is None or item['batch_id'] is None:
            pending.append(item)
            continue
        day_of = item['at'].date()
        if start and day_of < start:
            before += 1
            continue
        if day_of > stop:
            after += 1
            continue
        inspections.append(item)
        batch = item['batch_id']
        if batch not in root_times or item['at'] < root_times[batch]:
            root_times[batch] = item['at']
    inspections.sort(key=lambda item: (item['at'], item['record_id']))
    roots = sorted(root_times)
    discovered, truncated = _reach(roots, prep['edges'], prep['incoming'])
    if truncated:
        flags.append({'object': asset, 'type': '流转路径',
                      'detail': f'路径超过 {MAX_DEPTH} 层或单批路径超过 {MAX_PATHS} 条，已截断展示'})

    shipment_keys = {key for key, shipment in prep['shipments'].items()
                     if shipment['batches'] & set(discovered)}

    relevant = {info.get('record_id'), latest['record_id']}
    if last_pass:
        relevant.add(last_pass['record_id'])
    relevant.update(item['record_id'] for item in prep['inspections'].get(asset, []))
    relevant.update(cert['record_id'] for cert in prep['certs'].get(asset, []))
    for entry in discovered.values():
        relevant.update(entry['outgoing'])
        relevant.update(entry['incoming'])
    for key in shipment_keys:
        relevant.update(prep['shipments'][key]['record_ids'])
    relevant.discard(None)

    return {
        'asset_id': asset, 'asset_name': info.get('asset_name') or '',
        'work_area': info.get('work_area') or '', 'owner': info.get('owner') or '',
        'oot_certificate': latest['certificate_id'], 'oot_issued': latest['issued'],
        'oot_expires': latest['expires'], 'last_pass_certificate': last_pass['certificate_id'] if last_pass else None,
        'last_pass_issued': last_pass['issued'] if last_pass else None,
        'stopped_on': stop, 'window_start': start, 'window_end': stop,
        'inspections': inspections, 'pending_inspections': pending,
        'excluded_before': before, 'excluded_after': after,
        'batches': discovered, 'root_times': root_times,
        'shipment_keys': sorted(shipment_keys),
        'flags': flags, 'relevant': sorted(prep['records'][rid] for rid in relevant if rid in prep['records']),
    }


def _edge_index(prep):
    return {edge['record_id']: edge for edges in prep['edges'].values() for edge in edges}


def _first_arrival(entry, edge_index):
    """根批次以检验时间到达，下游批次取最早一条路径的实际流转时间。"""
    if any(not signature for signature in entry['paths']):
        return None
    times = []
    for signature in entry['paths']:
        edge = edge_index.get(signature[-1])
        times.append((edge['event_at'] or DT_MIN) if edge else DT_MIN)
    return min(times) if times else None


def _aggregate(traces, prep):
    edge_index = _edge_index(prep)
    batches = {}
    flags = []
    for trace in traces:
        flags.extend(trace['flags'])
        for batch, entry in trace['batches'].items():
            target = batches.setdefault(batch, {
                'batch_id': batch, 'sources': set(), 'paths': set(), 'incoming': {}, 'outgoing': {},
                'terminal': True, 'first_at': None,
            })
            target['sources'].add(trace['asset_id'])
            target['paths'].update(entry['paths'])
            target['incoming'].update(entry['incoming'])
            target['outgoing'].update(entry['outgoing'])
            target['terminal'] = target['terminal'] and entry['terminal']
            arrival = _first_arrival(entry, edge_index)
            if batch in trace['root_times'] and (arrival is None or trace['root_times'][batch] < arrival):
                arrival = trace['root_times'][batch]
            if arrival is not None and (target['first_at'] is None or arrival < target['first_at']):
                target['first_at'] = arrival

    for batch, entry in batches.items():
        keys = sorted(key for key, shipment in prep['shipments'].items() if batch in shipment['batches'])
        entry['shipment_keys'] = keys
        if keys:
            pending = [key for key in keys if prep['shipments'][key]['flags']]
            entry['status'] = STATUS_PENDING if pending else STATUS_SHIPPED
            if len(pending) > 1:
                flags.append({'object': batch, 'type': '批次',
                              'detail': f'批次经 {", ".join(pending)} 出货，但去向或时间不完整，标待核实'})
        elif entry['terminal']:
            entry['status'] = STATUS_PENDING
            flags.append({'object': batch, 'type': '批次',
                          'detail': '批次无下游流转也无出货记录，去向断档，标待核实'})
        else:
            entry['status'] = STATUS_FLOWING
    return batches, flags


def _shipment_rows(keys, prep, batches):
    rows = []
    for key in sorted(keys):
        shipment = prep['shipments'][key]
        path_batches = sorted(batch for batch in shipment['batches'] if batch in batches)
        path_count = sum(len(batches[batch]['paths']) for batch in path_batches)
        destinations = '、'.join(shipment['destinations'])
        rows.append({
            'shipment_id': shipment['shipment_id'], 'batches': '、'.join(path_batches),
            'destination': destinations or '（空）', 'shipped_on': _iso(shipment['shipped_on']),
            'path_count': path_count, 'batch_count': len(path_batches),
            'status': STATUS_PENDING if shipment['flags'] else STATUS_SHIPPED,
            'reason': '、'.join(shipment['flags']),
        })
    return rows


def _batch_rows(batches, prep):
    rows = []
    for batch, entry in sorted(batches.items()):
        destinations = sorted({destination for key in entry['shipment_keys']
                               for destination in prep['shipments'][key]['destinations']})
        pending_keys = [key for key in entry['shipment_keys'] if prep['shipments'][key]['flags']]
        label = '、'.join(destinations) or '—'
        if pending_keys:
            label = f'{label}（{ "、".join(pending_keys) } 待核实）'
        upstream = sorted({edge['parent'] for edge in entry['incoming'].values()})
        rows.append({
            'batch_id': batch, 'sources': '、'.join(sorted(entry['sources'])),
            'upstreams': '、'.join(upstream) or '—',
            'first_at': _iso(entry['first_at']), 'path_count': len(entry['paths']),
            'shipments': '、'.join(entry['shipment_keys']) or '—',
            'destination': label, 'status': entry['status'],
        })
    return rows


def _instrument_rows(traces, reused, has_previous):
    rows = []
    for trace in traces:
        rows.append({
            'asset_id': trace['asset_id'], 'asset_name': trace['asset_name'],
            'oot_certificate': trace['oot_certificate'], 'oot_issued': _iso(trace['oot_issued']),
            'last_pass_certificate': trace['last_pass_certificate'] or '（无）',
            'last_pass_issued': _iso(trace['last_pass_issued']),
            'stopped_on': trace['stopped_on'].isoformat(), 'inspection_count': len(trace['inspections']),
            'excluded': f'{trace["excluded_before"]} 前 / {trace["excluded_after"]} 后',
            'batch_count': len(trace['batches']), 'shipment_count': len(trace['shipment_keys']),
            'calculation': ('未受影响' if reused.get(trace['asset_id']) else '重算') if has_previous else '本次计算',
        })
    return rows


def _flag_rows(flags):
    seen, rows = set(), []
    for flag in flags:
        key = (flag['object'], flag['type'], flag['detail'])
        if key in seen:
            continue
        seen.add(key)
        rows.append({'object': flag['object'], 'type': flag['type'], 'detail': flag['detail']})
    return rows


def _batch_evidence(batches, prep, traces):
    edge_index = _edge_index(prep)
    evidence = {}
    for batch, entry in batches.items():
        inspections, pending, lineage = [], [], []
        seen_paths = set()
        for trace in traces:
            for item in trace['inspections']:
                if item['batch_id'] == batch:
                    inspections.append({
                        'record_id': item['record_id'], 'asset_id': item['asset_id'],
                        'inspected_on': _iso(item['at']), 'note': item['note'] or '',
                        'late': bool(item['recorded_at'] and item['at'] and item['recorded_at'] > item['at']),
                    })
            for item in trace['pending_inspections']:
                if item['batch_id'] == batch:
                    pending.append({'record_id': item['record_id'], 'asset_id': item['asset_id'],
                                    'detail': item.get('pending') or ''})
            reached = trace['batches'].get(batch)
            if not reached:
                continue
            for signature in reached['paths']:
                if not signature:
                    continue
                edges = [edge_index[record_id] for record_id in signature if record_id in edge_index]
                if len(edges) != len(signature):
                    continue
                root_batch = edges[0]['parent']
                key = (trace['asset_id'], root_batch, signature)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                lineage.append({
                    'asset_id': trace['asset_id'], 'root_batch': root_batch,
                    'inspected_on': _iso(trace['root_times'].get(root_batch)),
                    'path': ' → '.join([root_batch] + [edge['batch'] for edge in edges]),
                    'record_ids': list(signature),
                })
        lineage.sort(key=lambda item: (item['asset_id'], item['inspected_on'] or '', len(item['record_ids'])))
        flows_in = [{
            'record_id': edge['record_id'], 'parent_batch_id': edge['parent'],
            'event_at': _iso(edge['event_at']), 'recorded_at': _iso(edge['recorded_at']),
            'late': edge['late'], 'parent_in_trace': edge['parent'] in batches,
        } for edge in sorted(entry['incoming'].values(), key=lambda edge: (edge['_order'], edge['record_id']))]
        flows_out = [{
            'record_id': edge['record_id'], 'batch_id': edge['batch'],
            'event_at': _iso(edge['event_at']), 'recorded_at': _iso(edge['recorded_at']),
            'late': edge['late'], 'child_in_trace': edge['batch'] in batches,
        } for edge in sorted(entry['outgoing'].values(), key=lambda edge: (edge['_order'], edge['record_id']))]
        shipments = [{
            'shipment_id': prep['shipments'][key]['shipment_id'],
            'destination': '、'.join(prep['shipments'][key]['destinations']) or '（空）',
            'shipped_on': _iso(prep['shipments'][key]['shipped_on']),
            'status': STATUS_PENDING if prep['shipments'][key]['flags'] else STATUS_SHIPPED,
        } for key in entry['shipment_keys']]
        evidence[batch] = {
            'batch_id': batch, 'status': entry['status'], 'sources': sorted(entry['sources']),
            'path_count': len(entry['paths']), 'first_at': _iso(entry['first_at']),
            'inspections': inspections, 'pending_inspections': pending, 'lineage': lineage,
            'flows_in': flows_in, 'flows_out': flows_out, 'shipments': shipments,
        }
    return evidence


def _changed_records(prev_prep, prep):
    return {record_id for record_id in set(prev_prep['records']) | set(prep['records'])
            if prev_prep['records'].get(record_id) != prep['records'].get(record_id)}


def _affected_batches(changed, prev_prep, prep):
    affected = set()
    for record_id in changed:
        for source in (prev_prep, prep):
            row = source['rows'].get(record_id)
            if not row:
                continue
            kind = row['record_type']
            if kind == FLOW:
                for key in ('parent_batch_id', 'batch_id'):
                    if row.get(key):
                        affected.add(row[key].strip())
            elif kind in (INSPECTION, SHIPMENT):
                if row.get('batch_id'):
                    affected.add(row['batch_id'].strip())
            elif kind == CERTIFICATE:
                for trace in source.get('traces', []):
                    if trace['asset_id'] == row.get('asset_id'):
                        affected.update(trace['batches'])
    return affected


def _downstream(start, edges):
    seen, queue = set(), list(start)
    while queue:
        batch = queue.pop()
        if batch in seen:
            continue
        seen.add(batch)
        queue.extend(edge['batch'] for edge in edges.get(batch, []))
    return seen


def _diagnostics(prev_prep, prev_traces, prep, traces, changed):
    prev_batches, _ = _aggregate(prev_traces, prev_prep)
    new_batches, _ = _aggregate(traces, prep)
    old_keys, new_keys = set(prev_batches), set(new_batches)
    affected = _downstream(_affected_batches(changed, prev_prep, prep), prep['edges'])
    recomputed = affected & new_keys
    retained = set()
    for record_id in changed:
        old = prev_prep['rows'].get(record_id)
        new = prep['rows'].get(record_id)
        if not old or old.get('record_type') != FLOW:
            continue
        old_child = old.get('batch_id')
        if not old_child:
            continue
        same_path = bool(new and new.get('batch_id') == old_child and
                         new.get('parent_batch_id') == old.get('parent_batch_id'))
        if old_child in new_keys and not same_path:
            retained.add(old_child)
    withdrawn = old_keys - new_keys
    rows = []
    for batch in sorted(withdrawn):
        rows.append({'batch_id': batch, 'result': '撤销', 'detail': '原路径失效，已无其他路径到达'})
    for batch in sorted(retained & recomputed):
        rows.append({'batch_id': batch, 'result': '保留', 'detail': '原路径失效，仍有其他有效路径到达'})
    for batch in sorted(recomputed - retained):
        rows.append({'batch_id': batch, 'result': '重算', 'detail': '受上游记录变更影响'})
    return {
        'changed_records': sorted(changed),
        'recomputed': sorted(recomputed),
        'retained': sorted(retained & recomputed),
        'withdrawn': sorted(withdrawn),
        'rows': rows,
    }


def _metrics(traces, batches, shipment_rows, pending_objects):
    late = set()
    for trace in traces:
        for entry in trace['batches'].values():
            late.update(edge['record_id'] for edge in entry['outgoing'].values() if edge['late'])
    return [
        {'label': '超差器具', 'value': len(traces), 'detail': '截至报告日最新证书为超差'},
        {'label': '追溯批次', 'value': len(batches), 'detail': '上次合格后至停用前检验，含混批拆批下游'},
        {'label': '涉及出货单', 'value': len(shipment_rows), 'detail': '同一批经多条路径只计一单'},
        {'label': '待核实', 'value': len(pending_objects), 'detail': '去向断档或依据缺失，按批次与出货单去重'},
        {'label': '补录流转', 'value': len(late), 'detail': '登记晚于实际流转，已按实际时间接续'},
    ]


def _build_traces(prep, day):
    return [trace for asset in sorted(prep['certs'])
            for trace in [_trace_instrument(asset, prep, day)] if trace]


def analyze(rows, params, previous_rows=None, previous_params=None):
    day = params['report_day']
    if isinstance(day, str):
        day = _as_day(day)
    prep = _prepare(rows)
    traces = _build_traces(prep, day)
    prep['traces'] = traces

    reused, diagnostics = {}, None
    if previous_rows is not None:
        prev_day = (previous_params or params)['report_day']
        if isinstance(prev_day, str):
            prev_day = _as_day(prev_day)
        prev_prep = _prepare(previous_rows)
        prev_traces = _build_traces(prev_prep, prev_day)
        prev_by_asset = {trace['asset_id']: trace for trace in prev_traces}
        for trace in traces:
            previous = prev_by_asset.get(trace['asset_id'])
            reused[trace['asset_id']] = bool(previous and previous['relevant'] == trace['relevant'])
        prev_prep['traces'] = prev_traces
        changed = _changed_records(prev_prep, prep)
        diagnostics = _diagnostics(prev_prep, prev_traces, prep, traces, changed)
    else:
        for trace in traces:
            reused[trace['asset_id']] = False

    batches, flags = _aggregate(traces, prep)
    shipment_keys = sorted({key for entry in batches.values() for key in entry['shipment_keys']})
    shipment_rows = _shipment_rows(shipment_keys, prep, batches)
    flag_rows = _flag_rows(flags + prep['flags'])
    pending_objects = ({entry['batch_id'] for entry in batches.values() if entry['status'] == STATUS_PENDING} |
                       {row['shipment_id'] for row in shipment_rows if row['status'] == STATUS_PENDING})
    pending = len(pending_objects)
    headline = (f'{day} 超差追溯 · {len(traces)} 台器具，{len(batches)} 个批次，'
                f'{len(shipment_rows)} 张出货单，{pending} 项待核实')
    note = (f'报告日 {day}。倒查上次合格签发日之后、停用日之前（含停用当日）的检验批次，'
            '沿有效流转记录按实际时间追溯混批与拆批。同一批次经多条路径到达同一出货单只计一批一单，'
            '去向断档标待核实。')
    tables = [
        {'title': '超差器具与倒查窗口',
         'columns': [{'key': key, 'label': label} for key, label in (
             ('asset_id', '器具编号'), ('asset_name', '器具名称'), ('oot_certificate', '超差证书'),
             ('oot_issued', '超差签发日'), ('last_pass_certificate', '上次合格证书'),
             ('last_pass_issued', '上次合格签发日'), ('stopped_on', '停用日期'),
             ('inspection_count', '倒查批次记录'), ('excluded', '窗口外记录'),
             ('batch_count', '追溯批次'), ('shipment_count', '出货单'), ('calculation', '计算方式'))],
         'rows': _instrument_rows(traces, reused, previous_rows is not None)},
        {'title': '追溯批次与去向',
         'columns': [{'key': key, 'label': label} for key, label in (
             ('batch_id', '批次号'), ('sources', '来源器具'), ('upstreams', '上游批次'),
             ('first_at', '首次到达'), ('path_count', '路径数'), ('shipments', '出货单'),
             ('destination', '去向'), ('status', '判定'))],
         'rows': _batch_rows(batches, prep)},
        {'title': '出货去向依据',
         'columns': [{'key': key, 'label': label} for key, label in (
             ('shipment_id', '出货单号'), ('batches', '批次'), ('destination', '去向'),
             ('shipped_on', '出货时间'), ('batch_count', '批次计数'), ('path_count', '路径数'),
             ('status', '判定'), ('reason', '待核实原因'))],
         'rows': shipment_rows},
    ]
    if diagnostics and diagnostics['rows']:
        tables.append({
            'title': '上游更新后的增量重算',
            'columns': [{'key': key, 'label': label} for key, label in (
                ('batch_id', '批次号'), ('result', '处置'), ('detail', '说明'))],
            'rows': diagnostics['rows'],
        })
    tables.append({
        'title': '待核实清单',
        'columns': [{'key': key, 'label': label} for key, label in (
            ('object', '对象'), ('type', '类型'), ('detail', '说明'))],
        'rows': flag_rows,
    })
    charts = [{
        'title': '批次去向判定（批次）', 'kind': 'bar',
        'series': [{'label': status, 'value': sum(1 for entry in batches.values() if entry['status'] == status)}
                   for status in (STATUS_SHIPPED, STATUS_FLOWING, STATUS_PENDING)],
    }] if batches else []
    return {
        'ready': True, 'headline': headline, 'note': note,
        'metrics': _metrics(traces, batches, shipment_rows, pending_objects),
        'tables': tables, 'charts': charts,
        'batch_evidence': _batch_evidence(batches, prep, traces),
        'diagnostics': diagnostics,
        'report_day': day.isoformat(),
    }
