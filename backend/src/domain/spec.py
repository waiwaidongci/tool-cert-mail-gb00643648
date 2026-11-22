DEMO_DAY = '2026-11-21'
INSTRUMENT = '器具台账'
CERTIFICATE = '校准证书'
INSPECTION = '检验记录'
FLOW = '流转记录'
SHIPMENT = '出货记录'
ACTIVE = '在用'
INACTIVE = '停用'
TRACE_ACTIVE = '有效'
TRACE_VOID = '作废'
CAL_PASS = '合格'
CAL_OUT = '超差'

KIND_CERTIFICATE = 'certificate'
KIND_TRACE = 'trace'

TRACE_FIELDS = [
    {'key': 'record_id', 'label': '记录编号', 'type': 'string', 'required': True, 'max_length': 60,
     'help': '同一记录编号再次导入时，以登记时间较晚的一条覆盖旧版本。'},
    {'key': 'record_type', 'label': '记录类型', 'type': 'select', 'required': True,
     'options': [INSTRUMENT, CERTIFICATE, INSPECTION, FLOW, SHIPMENT]},
    {'key': 'record_status', 'label': '记录状态', 'type': 'select', 'required': False,
     'options': [TRACE_ACTIVE, TRACE_VOID], 'default': TRACE_ACTIVE,
     'help': '修正历史记录时以同一记录编号导入，状态设为作废即可撤下旧路径。'},
    {'key': 'asset_id', 'label': '器具编号', 'type': 'string', 'required': False, 'max_length': 40},
    {'key': 'asset_name', 'label': '器具名称', 'type': 'string', 'required': False, 'max_length': 80},
    {'key': 'work_area', 'label': '作业区', 'type': 'string', 'required': False, 'max_length': 60},
    {'key': 'owner', 'label': '责任班组', 'type': 'string', 'required': False, 'max_length': 60},
    {'key': 'asset_status', 'label': '器具状态', 'type': 'select', 'required': False,
     'options': [ACTIVE, INACTIVE], 'default': ACTIVE},
    {'key': 'stopped_on', 'label': '停用日期', 'type': 'date', 'required': False,
     'help': '校准超差后停用的日期；未填时以超差证书签发日为停用日。'},
    {'key': 'certificate_id', 'label': '证书编号', 'type': 'string', 'required': False, 'max_length': 60},
    {'key': 'issued_on', 'label': '签发日', 'type': 'date', 'required': False},
    {'key': 'expires_on', 'label': '到期日', 'type': 'date', 'required': False},
    {'key': 'calibration_result', 'label': '校准结果', 'type': 'select', 'required': False,
     'options': [CAL_PASS, CAL_OUT], 'default': CAL_PASS},
    {'key': 'batch_id', 'label': '批次号', 'type': 'string', 'required': False, 'max_length': 40},
    {'key': 'parent_batch_id', 'label': '上游批次号', 'type': 'string', 'required': False, 'max_length': 40},
    {'key': 'inspected_on', 'label': '检验时间', 'type': 'datetime', 'required': False},
    {'key': 'event_at', 'label': '实际流转时间', 'type': 'datetime', 'required': False,
     'help': '追溯按实际流转时间接续，晚到补录的记录不会打乱既有路径顺序。'},
    {'key': 'recorded_at', 'label': '登记时间', 'type': 'datetime', 'required': False,
     'help': '同一记录编号有多条时，取登记时间较晚的版本。'},
    {'key': 'shipment_id', 'label': '出货单号', 'type': 'string', 'required': False, 'max_length': 60},
    {'key': 'shipped_on', 'label': '出货时间', 'type': 'datetime', 'required': False},
    {'key': 'destination', 'label': '出货去向', 'type': 'string', 'required': False, 'max_length': 120},
    {'key': 'note', 'label': '备注', 'type': 'string', 'required': False, 'max_length': 200},
]

TRACE_PARAMS = [
    {'key': 'report_day', 'label': '报告日', 'type': 'date', 'required': True, 'default': DEMO_DAY,
     'help': '只采纳签发日不晚于报告日的超差证书。'},
]

BASE_SPEC = {
    'title': '工厂计量器具证书到期班报',
    'short_name': 'tool-cert-mail',
    'subtitle': '交班前核对校准证书，逐台安排停用、送校与补档',
    'organization': '澄岭精密零件厂 · 质量计量室',
    'workflow': (
        '澄岭精密零件厂有机加工、装配和终检三处作业区，两班共用计量器具。'
        '过去由计量员把器具台账和校准机构的证书登记表逐项对照，再在交班群中通知线长。'
        '计量员现将两份清单合并导入，值班主管设定报告日、临期天数和覆盖门槛。'
        '班组在站内收件箱领取班报，按器具编号安排替换、送校和证书补档。'
    ),
    'pains': [
        '同一器具有多张历史证书，手工筛选时可能引用旧证或将后续签发的证书算入历史班报。',
        '班组难以从单一到期总数判断哪台器具该停用、送校或补档。',
        '证书登记缺口常在班报转发后才被发现。',
    ],
    'steps': [
        '11 月 21 日 07:30，计量员导入《澄岭厂器具台账及校准证书.csv》，其中有 6 台在用器具及 1 台停用器具。',
        '07:40，以 11 月 21 日为报告日生成班报，设置 14 天提醒和 80% 最低覆盖率。',
        '机加工卡尺 QC-101 已过期 1 天，线长换用有效备用卡尺并登记送校。',
        '装配扭矩扳手 QC-102 当日到期，线长在交班前安排换具和送校。',
        '计量员联系终检核对 QC-106 的证书，11 月 22 日签发的记录留待下一报告日采纳。',
        '主管确认 5/6 台有证书记录，配置站内定时分发。',
        '将覆盖门槛提高到 100% 试跑，班报保留逐台处置清单，定时分发暂停。',
        '卡尺 QC-201 校准超差停用，计量员导入《超差追溯及批次流转》批次，倒查上次合格后的检验批次。',
        '沿混批、拆批流转追到出货单 S-9001：两条路径同批出货只计一批，缺去向的 S-9201 与断档批次标待核实。',
        '补录 11 月的流转记录后重新追溯，指定上次结果做增量重算，撤销失效路径并保留仍有其他路径的批次。',
    ],
    'methodology': [
        '在用范围取导入台账。每台器具选取签发日不晚于报告日的最新证书，同日按证书编号字典序取最后一条。',
        '到期剩余天数 = 到期日减报告日。负值为已过期，0 为当日到期，其余在提醒天数内（含上限）为即将到期。',
        '覆盖率 = 截至报告日有证书的在用器具数 ÷ 在用器具总数，已过期的证书也计入覆盖率。',
        '至少有一台在用器具且实际覆盖率达到门槛时允许定时分发。每日计划推进报告日并读取最新导入批次。',
    ],
    'sample_name': '澄岭厂器具台账及校准证书.csv',
    'default_dataset': '澄岭精密 11 月校准证书演练批次',
    'entity': '器具台账与校准证书',
    'run': '证书到期班报',
    'decision': '班报处置',
    'action': '登记复核结论',
    'modes': ['确认班报', '安排换具送校', '催补证书'],
    'pages': ['计量值班台', '器具与证书', '班报与定时计划', '到期清单', '班报复核', '班报收件箱', '超差追溯'],
    'scheduled': True,
    'schedule_date_param': 'report_day',
    'fields': [
        {'key': 'record_type', 'label': '记录类型', 'type': 'select', 'required': True,
         'options': [INSTRUMENT, CERTIFICATE]},
        {'key': 'asset_id', 'label': '器具编号', 'type': 'string', 'required': True, 'max_length': 40},
        {'key': 'asset_name', 'label': '器具名称（台账填写）', 'type': 'string', 'required': False, 'max_length': 80},
        {'key': 'work_area', 'label': '作业区（台账填写）', 'type': 'string', 'required': False, 'max_length': 60},
        {'key': 'owner', 'label': '责任班组（台账填写）', 'type': 'string', 'required': False, 'max_length': 60},
        {'key': 'asset_status', 'label': '器具状态（台账填写）', 'type': 'select', 'required': False,
         'options': [ACTIVE, INACTIVE]},
        {'key': 'certificate_id', 'label': '证书编号（证书填写）', 'type': 'string', 'required': False, 'max_length': 60},
        {'key': 'issued_on', 'label': '签发日（证书填写）', 'type': 'date', 'required': False},
        {'key': 'expires_on', 'label': '到期日（证书填写）', 'type': 'date', 'required': False},
    ],
    'params': [
        {'key': 'report_day', 'label': '报告日', 'type': 'date', 'required': True, 'default': DEMO_DAY,
         'help': '以报告日筛选已签发的证书。每日分发计划会逐日推进此日期。'},
        {'key': 'horizon_days', 'label': '临期提醒天数', 'type': 'int', 'required': True,
         'default': 14, 'min': 0, 'max': 365, 'help': '0 天仅提醒当日到期。'},
        {'key': 'min_coverage_percent', 'label': '最低证书覆盖率（%）', 'type': 'int', 'required': True,
         'default': 80, 'min': 0, 'max': 100, 'help': '达到门槛才允许定时分发。'},
    ],
    'fixture': {'min_coverage_percent': 100},
    'axes': '按在用器具计数，每台器具只归入一个证书状态。',
    'trace_sample_name': '澄岭厂超差追溯及批次流转.csv',
    'trace_decision': '追溯处置',
    'trace_modes': ['确认追溯结果', '通知客户停用', '补录流转记录'],
    'trace_fields': TRACE_FIELDS,
    'trace_params': TRACE_PARAMS,
    'trace_methodology': [
        '超差范围为签发日不晚于报告日的最新一张超差证书；上次合格取同一器具在此前签发的最后一张合格证书。',
        '倒查该器具在上次合格签发之后、停用日期之前（含停用当日）的检验批次；停用日期未填时取超差证书签发日。',
        '沿有效流转记录向下追溯混批与拆批，按实际流转时间接续；登记时间晚于实际时间的记录标记为补录。',
        '同一记录编号只取登记时间最晚的版本；状态为作废的记录不参与追溯。',
        '同一批次经多条路径到达同一出货单只计一批、一单；出货单缺少去向或批次无下游流转也无出货记录时标待核实。',
        '上游记录更新后，只重算变更记录触及的批次及其下游批次，撤下失效路径；仍有其他有效路径的批次继续保留。',
        '同一报告日再次追溯时自动对比上次结果；指定上次运行可手工选择对比基准。',
    ],
}

SPEC = BASE_SPEC
