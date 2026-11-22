import {plot} from '../components/common/chart.js';
import {feedback, field} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {REVIEW, STATUS} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, h, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

const KIND = 'trace';

function reviewForm(job, spec, refresh) {
  const message = feedback();
  const submit = button('登记复核结论', {class:'primary', type:'submit'});
  return el('form', {class:'fields', onSubmit:handler(submit, message, async event => {
    const data = new FormData(event.target);
    await workspace.review(job.id, {review:data.get('review'), decision:data.get('decision'), note:data.get('note')});
    await refresh();
  })}, el('label', {class:'field', for:'trace-review-state'}, el('span', {}, '复核结论'),
    el('select', {id:'trace-review-state', name:'review'}, el('option', {value:'accepted'}, '通过'),
      el('option', {value:'returned'}, '退回'))),
    field({key:'decision', label:spec.trace_decision, type:'select', options:spec.trace_modes,
      required:false, max_length:120}),
    el('label', {class:'field', for:'trace-review-note'}, el('span', {}, '复核说明'),
      el('textarea', {id:'trace-review-note', name:'note', required:true, maxlength:500, rows:3})),
    submit, message);
}

function reportForm(datasets, runs, spec, refresh, selected) {
  const message = feedback();
  const submit = button('执行超差追溯', {type:'submit', class:'primary', 'data-testid':'start-trace'});
  const previous = runs.filter(item => item.status === 'complete');
  return el('form', {class:'fields', 'data-testid':'trace-form', onSubmit:handler(submit, message, async event => {
    const data = new FormData(event.target);
    const previousRun = data.get('previous_run_id');
    const item = await workspace.start({
      dataset_id:Number(data.get('dataset_id')), name:data.get('name'),
      params:{report_day:data.get('report_day')},
      previous_run_id: previousRun ? Number(previousRun) : null,
    });
    await refresh();
    location.hash = `#trace/${item.id}`;
  })},
  el('label', {for:'trace-dataset', class:'field'}, el('span', {}, '追溯数据批次'),
    el('select', {id:'trace-dataset', name:'dataset_id', required:true}, datasets.map(item =>
      el('option', {value:item.id, selected:item.id === selected}, `${item.name} · ${item.row_count} 行`)))),
  field({key:'name', label:'运行名称', type:'string', max_length:120}, `超差追溯 ${new Date().toISOString().slice(0, 10)}`),
  field({key:'report_day', label:'报告日', type:'date', required:true, default:spec.trace_params[0].default}),
  el('label', {for:'previous-run', class:'field'}, el('span', {}, '增量对比'),
    el('select', {id:'previous-run', name:'previous_run_id'},
      el('option', {value:''}, '自动：对比同报告日的上次追溯结果'),
      previous.map(item => el('option', {value:item.id}, item.name)))),
  p('默认对比同一报告日的上次结果，只重算受上游记录变更影响的批次；撤下失效路径，仍有其他路径的批次保留。也可指定具体运行对比。', 'subtle'),
  el('div', {class:'actions'}, submit), message);
}

function batchEvidence(job, evidence) {
  const evidenceItem = (label, valueText) => el('div', {}, el('dt', {}, label), el('dd', {}, value(valueText)));
  const noteOf = (item, base) => [base, item.late ? '补录' : null].filter(Boolean).join(' · ');
  const inspectionRows = evidence.inspections.map(item => ({
    record_id:item.record_id, asset_id:item.asset_id, inspected_on:item.inspected_on, note:noteOf(item, item.note),
  }));
  const flowRows = [
    ...evidence.flows_in.map(item => ({direction:'转入', batch:`${item.parent_batch_id} → ${evidence.batch_id}`,
      record_id:item.record_id, event_at:item.event_at, recorded_at:item.recorded_at, late:item.late})),
    ...evidence.flows_out.map(item => ({direction:'转出', batch:`${evidence.batch_id} → ${item.batch_id}`,
      record_id:item.record_id, event_at:item.event_at, recorded_at:item.recorded_at, late:item.late})),
  ];
  return panel(`批次 ${evidence.batch_id} 的检验、流转与出货依据`,
    el('div', {class:'actions'}, pill(evidence.status, evidence.status),
      p(`首次到达 ${date(evidence.first_at)} · 路径 ${evidence.path_count} 条 · 来源器具 ${evidence.sources.join('、')}`)),
    el('dl', {class:'dictionary'},
      evidenceItem('批次', evidence.batch_id),
      evidenceItem('来源器具', evidence.sources.join('、')),
      evidenceItem('首次到达', date(evidence.first_at))),
    h(3, '检验依据'),
    table([{key:'asset_id', label:'器具编号'}, {key:'root_batch', label:'倒查批次'},
      {label:'检验时间', render:row=>date(row.inspected_on)}, {key:'path', label:'到达路径'}],
      evidence.lineage, {caption:'上游倒查检验依据', empty:'该批次即倒查起点，见下方检验记录。'}),
    table([{key:'record_id', label:'检验记录'}, {key:'asset_id', label:'器具编号'},
      {label:'检验时间', render:row=>date(row.inspected_on)}, {key:'note', label:'说明'}],
      [...inspectionRows, ...evidence.pending_inspections.map(item => ({record_id:item.record_id,
        asset_id:item.asset_id, inspected_on:null, note:item.detail}))],
      {caption:'检验依据', empty:'该批次没有直接检验记录，依据见上游倒查批次。'}),
    h(3, '流转依据'),
    table([{key:'direction', label:'方向'}, {key:'batch', label:'路径'}, {key:'record_id', label:'流转记录'},
      {label:'实际流转', render:row=>date(row.event_at)}, {label:'登记', render:row=>date(row.recorded_at)},
      {label:'补录', render:row=>row.late ? '是' : '—'}],
      flowRows, {caption:'流转依据', empty:'该批次没有上下游流转记录。'}),
    h(3, '出货依据'),
    table([{key:'shipment_id', label:'出货单号'}, {key:'destination', label:'去向'},
      {label:'出货时间', render:row=>date(row.shipped_on)},
      {label:'判定', render:row=>pill(row.status, row.status)}],
      evidence.shipments, {caption:'出货依据', empty:'该批次没有出货记录，去向待核实。'}),
    link(`返回运行 ${job.id}`, `#trace/${job.id}`, {class:'quiet'}));
}

export async function tracePage(route, refresh) {
  const {spec, datasets, runs} = workspace;
  const traceDatasets = datasets.filter(item => item.kind === KIND);
  const traceRuns = runs.filter(item => item.kind === KIND);
  const done = traceRuns.filter(item => item.status === 'complete');
  const id = route.id || done[0]?.id;
  const message = feedback();
  const hinted = Number(route.query?.dataset) || null;
  const form = panel('超差追溯与批次流转', p(spec.trace_methodology[0], 'subtle'),
    traceDatasets.length ? reportForm(traceDatasets, traceRuns, spec, refresh, hinted)
      : empty('请先导入追溯数据批次。', '#inputs/0/0/trace', '前往导入'));

  const runList = panel('追溯运行', table([
    {label:'运行', render:row=>link(row.name, `#trace/${row.id}`)},
    {label:'状态', render:row=>pill(STATUS[row.status], row.status)},
    {label:'报告日', render:row=>value(row.report_day)},
    {label:'时间', render:row=>date(row.created_at)},
  ], traceRuns, {caption:'追溯运行', empty:'导入追溯数据后执行首次追溯。'}), message);

  const sidebar = [panel('计算口径', el('ul', {class:'method-list'}, spec.trace_methodology.map(text=>el('li', {}, text)))),
    form, runList];

  if (!id) return el('div', {class:'two-col'}, el('div', {class:'wide-panel'}, empty('还没有可查看的追溯结果。', '#trace', '刷新')),
    el('aside', {class:'sidebar-panel'}, sidebar));
  const job = await workspace.getRun(id);
  if (job.status !== 'complete' || !job.result) {
    return el('div', {class:'two-col'}, el('div', {class:'wide-panel'},
      panel(job.name, pill(STATUS[job.status], job.status), p(job.error || '后台正在计算，请稍后刷新。', 'feedback'),
        button('刷新', {class:'quiet', onClick:refresh}))), el('aside', {class:'sidebar-panel'}, sidebar));
  }

  const result = job.result;
  const download = button('下载追溯 CSV', {class:'quiet', onClick:event=>
    handler(download, message, () => workspace.download(`/runs/${job.id}/export`, `trace-${job.id}.csv`))(event)});
  const evidence = route.arg ? result.batch_evidence?.[route.arg] : null;
  const missing = route.arg && !evidence;
  const lookupMessage = feedback();
  const lookup = button('查看批次依据', {type:'submit', class:'quiet', 'data-testid':'find-batch'});
  const batchLookup = el('form', {class:'fields batch-lookup', onSubmit:handler(lookup, lookupMessage, () => {
    const input = batchLookup.elements.batch_id;
    const batch = input.value.trim();
    if (!batch) throw new Error('请输入批次号');
    if (!result.batch_evidence?.[batch]) throw new Error('该批次不在本次追溯范围内');
    location.hash = `#trace/${job.id}/${encodeURIComponent(batch)}`;
    refresh();
  })}, el('label', {class:'field', for:'batch-lookup'}, el('span', {}, '按批次查看检验、流转与出货依据'),
    el('input', {id:'batch-lookup', name:'batch_id', type:'text', maxlength:40, value:route.arg || '',
      placeholder:'例如 B-2410'})), lookup, lookupMessage);
  const columnsFor = item => item.columns.map(column => column.key === 'batch_id'
    ? {...column, render:row=>link(row.batch_id, `#trace/${job.id}/${encodeURIComponent(row.batch_id)}`,
        {class:row.batch_id === route.arg ? 'primary' : undefined})}
    : column);
  const analysis = el('section', {class:'analysis', 'data-testid':'trace-complete'},
    el('div', {class:'result-head'}, p(job.name, 'eyeline'), h(2, result.headline), p(result.note, 'intro-copy'),
      el('div', {class:'actions'}, pill(STATUS[job.status], job.status), download, message)),
    metrics(result.metrics),
    result.charts.map(plot),
    panel('批次依据查询', batchLookup,
      missing ? p(`批次 ${route.arg} 不在本次追溯范围内，请核对批次号或查看追溯批次表。`, 'feedback') : null),
    result.tables.map(item => panel(item.title, table(columnsFor(item), item.rows, {caption:item.title}))),
    evidence ? batchEvidence(job, evidence) : p('点击批次号或输入批次号，查看该批次的检验、流转和出货依据。', 'subtle'));

  return el('div', {class:'two-col'}, el('div', {class:'wide-panel'}, analysis),
    el('aside', {class:'sidebar-panel'}, sidebar,
      panel(spec.trace_decision, pill(REVIEW[job.review], job.review),
        job.review_note && el('div', {class:'decision'}, p(job.decision), p(job.review_note)),
        job.review === 'pending'
          ? (session.canReview ? reviewForm(job, spec, refresh) : p('等待业务负责人复核。', 'subtle'))
          : link('查看复核记录', `#review/${job.id}`, {class:'quiet'}))));
}
