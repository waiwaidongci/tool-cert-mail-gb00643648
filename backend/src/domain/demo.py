"""澄岭精密的固定演练台账和证书历史，以及超差追溯的多版本演练数据。"""

from .spec import (
    ACTIVE, CAL_OUT, CAL_PASS, CERTIFICATE, DEMO_DAY, FLOW, INACTIVE, INSPECTION,
    INSTRUMENT, SHIPMENT, TRACE_ACTIVE, TRACE_VOID,
)


def demo_rows() -> list[dict]:
    instruments = [
        ('QC-101', '数显卡尺', '机加工区', '车削一班', ACTIVE),
        ('QC-102', '扭矩扳手', '装配区', '装配二班', ACTIVE),
        ('QC-103', '外径千分尺', '机加工区', '磨削班', ACTIVE),
        ('QC-104', '针规组', '终检区', '终检班', ACTIVE),
        ('QC-105', '电子天平', '终检区', '来料检验班', ACTIVE),
        ('QC-106', '高度规', '终检区', '终检班', ACTIVE),
        ('QC-107', '指针式压力表', '装配区', '装配二班', INACTIVE),
    ]
    certificates = [
        ('QC-103', 'CL-103-26', '2026-06-05', '2026-12-05'),
        ('QC-101', 'CL-101-27', '2026-11-22', '2027-05-22'),
        ('QC-105', 'CL-105-26', DEMO_DAY, '2027-05-21'),
        ('QC-101', 'CL-101-26', '2026-05-20', '2026-11-20'),
        ('QC-101', 'CL-101-25', '2025-11-20', '2026-05-20'),
        ('QC-102', 'CL-102-26', '2026-05-21', DEMO_DAY),
        ('QC-104', 'CL-104-26', '2026-06-06', '2026-12-06'),
        ('QC-106', 'CL-106-26', '2026-11-22', '2027-05-22'),
        ('QC-107', 'CL-107-25', '2025-11-05', '2026-05-05'),
    ]
    return [
        dict(record_type=INSTRUMENT, asset_id=asset_id, asset_name=name, work_area=area,
             owner=owner, asset_status=status, certificate_id=None, issued_on=None, expires_on=None)
        for asset_id, name, area, owner, status in instruments
    ] + [
        dict(record_type=CERTIFICATE, asset_id=asset_id, asset_name=None, work_area=None,
             owner=None, asset_status=None, certificate_id=code, issued_on=issued, expires_on=expires)
        for asset_id, code, issued, expires in certificates
    ]


def _trace_row(record_id, record_type, **values):
    row = {
        'record_id': record_id, 'record_type': record_type, 'record_status': TRACE_ACTIVE,
        'asset_id': None, 'asset_name': None, 'work_area': None, 'owner': None,
        'asset_status': None, 'stopped_on': None, 'certificate_id': None, 'issued_on': None,
        'expires_on': None, 'calibration_result': None, 'batch_id': None, 'parent_batch_id': None,
        'inspected_on': None, 'event_at': None, 'recorded_at': None, 'shipment_id': None,
        'shipped_on': None, 'destination': None, 'note': None,
    }
    row.update(values)
    return row


def demo_trace_rows(version: str = 'baseline') -> list[dict]:
    """version=baseline 为初版；version=correction 将两条错误流转作废。"""
    rows = [
        # 器具台账：两台已停用的器具持有超差证书，一台仅需到期班报，一台超差但缺上次合格。
        _trace_row('AST-201', INSTRUMENT, asset_id='QC-201', asset_name='数显卡尺', work_area='机加工区',
                   owner='车削一班', asset_status=ACTIVE, stopped_on='2026-11-18'),
        _trace_row('AST-202', INSTRUMENT, asset_id='QC-202', asset_name='扭矩扳手', work_area='装配区',
                   owner='装配二班', asset_status=ACTIVE, stopped_on='2026-11-20'),
        _trace_row('AST-203', INSTRUMENT, asset_id='QC-203', asset_name='外径千分尺', work_area='机加工区',
                   owner='磨削班', asset_status=ACTIVE, stopped_on=None),
        _trace_row('AST-204', INSTRUMENT, asset_id='QC-204', asset_name='针规组', work_area='终检区',
                   owner='终检班', asset_status=ACTIVE, stopped_on='2026-11-16'),
        # 校准证书：每台保留合格历史，最新一张为超差；QC-203 最新仍为合格。
        _trace_row('CAL-201-24', CERTIFICATE, asset_id='QC-201', certificate_id='CL-201-24',
                   issued_on='2025-05-18', expires_on='2025-11-18', calibration_result=CAL_PASS),
        _trace_row('CAL-201-25', CERTIFICATE, asset_id='QC-201', certificate_id='CL-201-25',
                   issued_on='2026-05-18', expires_on='2026-11-18', calibration_result=CAL_PASS),
        _trace_row('CAL-201-26', CERTIFICATE, asset_id='QC-201', certificate_id='CL-201-26',
                   issued_on='2026-11-18', expires_on='2027-05-18', calibration_result=CAL_OUT),
        _trace_row('CAL-202-25', CERTIFICATE, asset_id='QC-202', certificate_id='CL-202-25',
                   issued_on='2026-05-20', expires_on='2026-11-20', calibration_result=CAL_PASS),
        _trace_row('CAL-202-26', CERTIFICATE, asset_id='QC-202', certificate_id='CL-202-26',
                   issued_on='2026-11-20', expires_on='2027-05-20', calibration_result=CAL_OUT),
        _trace_row('CAL-203-26', CERTIFICATE, asset_id='QC-203', certificate_id='CL-203-26',
                   issued_on='2026-09-01', expires_on='2027-03-01', calibration_result=CAL_PASS),
        _trace_row('CAL-204-26', CERTIFICATE, asset_id='QC-204', certificate_id='CL-204-26',
                   issued_on='2026-11-16', expires_on='2027-05-16', calibration_result=CAL_OUT),
        # 检验记录：窗口外、窗口内、停用后各留一条，验证倒查边界。
        _trace_row('INS-201-01', INSPECTION, asset_id='QC-201', batch_id='B-2401',
                   inspected_on='2026-05-10T09:10', recorded_at='2026-05-10T17:00',
                   note='上次合格签发前，窗口外'),
        _trace_row('INS-201-02', INSPECTION, asset_id='QC-201', batch_id='B-2402',
                   inspected_on='2026-06-02T10:20', recorded_at='2026-06-02T18:00'),
        _trace_row('INS-201-03', INSPECTION, asset_id='QC-201', batch_id='B-2403',
                   inspected_on='2026-07-11T14:05', recorded_at='2026-07-11T20:10'),
        _trace_row('INS-201-04', INSPECTION, asset_id='QC-201', batch_id='B-2404',
                   inspected_on='2026-11-19T08:30', recorded_at='2026-11-19T12:00',
                   note='停用次日检验，窗口外'),
        _trace_row('INS-202-01', INSPECTION, asset_id='QC-202', batch_id='B-2301',
                   inspected_on='2026-09-05T09:40', recorded_at='2026-09-05T16:30'),
        _trace_row('INS-202-02', INSPECTION, asset_id='QC-202', batch_id='B-2303',
                   inspected_on='2026-09-20T11:20', recorded_at='2026-09-20T19:10'),
        _trace_row('INS-202-03', INSPECTION, asset_id='QC-202', batch_id='B-2305',
                   inspected_on='2026-11-21T08:10', recorded_at='2026-11-21T09:00',
                   note='停用后检验，窗口外'),
        _trace_row('INS-203-01', INSPECTION, asset_id='QC-203', batch_id='B-2601',
                   inspected_on='2026-10-10T10:00', recorded_at='2026-10-10T18:00'),
        _trace_row('INS-204-01', INSPECTION, asset_id='QC-204', batch_id='B-2501',
                   inspected_on='2026-10-01T09:00', recorded_at='2026-10-01T17:10'),
        # 混批与拆批：B-2402 经两条路径到达同一出货单，只计一批。
        _trace_row('FLW-01', FLOW, parent_batch_id='B-2402', batch_id='B-2410',
                   event_at='2026-06-20T08:30', recorded_at='2026-06-20T09:00'),
        _trace_row('FLW-02', FLOW, parent_batch_id='B-2403', batch_id='B-2413',
                   event_at='2026-07-20T08:30', recorded_at='2026-07-20T09:00'),
        _trace_row('FLW-03', FLOW, parent_batch_id='B-2410', batch_id='B-2420',
                   event_at='2026-09-01T07:45', recorded_at='2026-09-01T08:10'),
        _trace_row('FLW-04', FLOW, parent_batch_id='B-2402', batch_id='B-2411',
                   event_at='2026-07-25T09:15', recorded_at='2026-07-25T09:40'),
        # 晚到补录：登记时间晚于实际流转时间，追溯仍按实际时间接续。
        _trace_row('FLW-05', FLOW, parent_batch_id='B-2411', batch_id='B-2420',
                   event_at='2026-08-15T10:00', recorded_at='2026-11-19T15:20',
                   note='11 月补录 8 月流转'),
        _trace_row('FLW-06', FLOW, parent_batch_id='B-2413', batch_id='B-2421',
                   event_at='2026-08-01T09:00', recorded_at='2026-08-01T09:30'),
        _trace_row('FLW-07', FLOW, parent_batch_id='B-2402', batch_id='B-2413',
                   event_at='2026-08-10T08:00', recorded_at='2026-08-10T08:20'),
        _trace_row('FLW-08', FLOW, parent_batch_id='B-2403', batch_id='B-2416',
                   event_at='2026-08-20T07:30', recorded_at='2026-08-20T08:00'),
        _trace_row('FLW-09', FLOW, parent_batch_id='B-2416', batch_id='B-2422',
                   event_at='2026-09-15T06:50', recorded_at='2026-09-15T07:20'),
        _trace_row('FLW-11', FLOW, parent_batch_id='B-2301', batch_id='B-2302',
                   event_at='2026-09-10T10:00', recorded_at='2026-09-10T10:30'),
        _trace_row('FLW-12', FLOW, parent_batch_id='B-2303', batch_id='B-2304',
                   event_at='2026-09-25T09:00', recorded_at='2026-09-25T09:30'),
        _trace_row('FLW-21', FLOW, parent_batch_id='B-2501', batch_id='B-2502',
                   event_at='2026-10-05T09:00', recorded_at='2026-10-05T09:30'),
        # 出货记录：S-9001 同时包含两条批次，只计一张单；S-9201 缺去向；B-2304 无下游。
        _trace_row('SHP-9001-A', SHIPMENT, batch_id='B-2410', shipment_id='S-9001',
                   destination='华东汽配', shipped_on='2026-09-05T06:00'),
        _trace_row('SHP-9001-B', SHIPMENT, batch_id='B-2420', shipment_id='S-9001',
                   destination='华东汽配', shipped_on='2026-09-05T06:00'),
        _trace_row('SHP-9003', SHIPMENT, batch_id='B-2413', shipment_id='S-9003',
                   destination='华北重工', shipped_on='2026-08-25T07:00'),
        _trace_row('SHP-9006', SHIPMENT, batch_id='B-2422', shipment_id='S-9006',
                   destination='华南机电', shipped_on='2026-09-20T06:30'),
        _trace_row('SHP-9101', SHIPMENT, batch_id='B-2302', shipment_id='S-9101',
                   destination='西南装配', shipped_on='2026-11-19T18:00'),
        _trace_row('SHP-9201', SHIPMENT, batch_id='B-2502', shipment_id='S-9201',
                   destination=None, shipped_on='2026-10-10T06:00', note='去向待补'),
    ]
    if version == 'correction':
        rows = [
            {**row, 'record_status': TRACE_VOID, 'recorded_at': '2026-11-21T09:00'}
            if row['record_id'] == 'FLW-02' else row for row in rows
        ]
        rows = [
            {**row, 'record_status': TRACE_VOID, 'recorded_at': '2026-11-21T09:05'}
            if row['record_id'] == 'FLW-08' else row for row in rows
        ]
        rows.append(_trace_row('FLW-02B', FLOW, parent_batch_id='B-2403', batch_id='B-2410',
                               event_at='2026-07-20T08:30', recorded_at='2026-11-21T09:10',
                               note='更正原流转去向'))
    return rows


TRACE_VERSION_NAMES = {
    'baseline': '澄岭精密 11 月超差追溯演练批次',
    'correction': '澄岭精密 11 月超差追溯演练批次（更正）',
}
