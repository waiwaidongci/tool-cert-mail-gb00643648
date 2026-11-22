import {feedback, field} from '../components/common/fields.js';
import {empty, panel} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

const KINDS = [
  {value:'certificate', label:'器具台账与校准证书'},
  {value:'trace', label:'超差追溯与批次流转'},
];

export async function inputs(route, refresh) {
  const {spec,datasets} = workspace;
  const kind = route.arg === 'trace' ? 'trace' : 'certificate';
  const visible = datasets.filter(item => (item.kind || 'certificate') === kind);
  const selected = visible.find(item => item.id === route.id) || visible[0];
  const error = feedback();
  const fields = kind === 'trace' ? spec.trace_fields : spec.fields;
  const sampleName = kind === 'trace' ? spec.trace_sample_name : spec.sample_name;
  const sample = button('下载示例 CSV', {class:'quiet',onClick:event=>handler(sample,error,()=>
    workspace.download(kind === 'trace' ? '/template?kind=trace' : '/template',sampleName))(event)});
  const detail = selected && await workspace.getDataset(selected.id,route.offset);
  const columns = fields.map(field => ({key:field.key,label:field.label}));
  const preview = detail ? panel('批次明细', el('div',{class:'actions'},
    el('label',{for:'dataset-id',class:'sr'}, '选择数据批次'),
    el('select',{id:'dataset-id','aria-label':'选择数据批次',onChange:event=>{
      location.hash = `#inputs/${event.target.value}/0/${kind}`;}},
      visible.map(item=>el('option',{value:item.id,selected:item.id === selected.id}, item.name))),
    link(kind === 'trace' ? '使用此批次追溯' : '使用此批次运行',
      kind === 'trace' ? `#trace?dataset=${detail.id}` : `#run/${detail.id}`,{class:'quiet'})),
    p(`${detail.filename} · ${detail.row_count} 行 · ${date(detail.created_at)}`,'filename'),
    table(columns,detail.rows,{caption:'批次明细',pageSize:16}),
    el('div',{class:'pagination'},
      route.offset > 0 && link('上一批明细',`#inputs/${detail.id}/${Math.max(0,route.offset-16)}/${kind}`,{class:'quiet'}),
      p(`${detail.rows.length ? route.offset+1 : route.offset}–${route.offset+detail.rows.length} / ${detail.row_count}`),
      route.offset+16 < detail.row_count && link('下一批明细',`#inputs/${detail.id}/${route.offset+16}/${kind}`,{class:'quiet'})))
    : empty('没有可用的批次。请导入示例或业务 CSV。');
  const submit = button('校验并导入', {type:'submit',class:'primary'});
  const upload = session.canWrite && el('form',{class:'fields',onSubmit:handler(submit,error,async event=>{
    const data = new FormData(event.target);
    const file = data.get('source');
    if (!file?.size) throw new Error('请选择一个 CSV 文件');
    if (file.size > 2_000_000) throw new Error('CSV 最多 2 MB');
    const item = await workspace.upload({name:data.get('batch_name'),filename:file.name,kind,
      csv_text:await file.text()});
    const target = `#inputs/${item.id}/${0}/${kind}`;
    if (location.hash === target) await refresh();
    else location.hash = target;
  })},field({key:'batch_name',label:'批次名称',type:'string',max_length:120}),
    el('label',{class:'field',for:'source'}, el('span',{},'业务 CSV'),el('input',{id:'source',type:'file',name:'source',accept:'.csv,text/csv',required:true})), submit);
  const switcher = el('div',{class:'actions'},KINDS.map(item=>link(item.label,
    `#inputs${item.value === 'trace' ? '/0/0/trace' : ''}`,{class:item.value === kind ? 'primary' : 'quiet'})));
  return el('div',{class:'two-col'},el('div',{class:'wide-panel'},switcher,preview),el('aside',{class:'sidebar-panel'},
    panel('数据导入',p(kind === 'trace'
      ? '超差追溯批次包含台账、证书、检验、流转与出货记录；同一记录编号可重复导入以补录更正。'
      : '导入后保留原批次和校验指纹，可用同一份数据复跑。','subtle'),sample,upload,error),
    panel('字段说明',el('dl',{class:'dictionary'},fields.map(item=>el('div',{},el('dt',{},item.label),
      el('dd',{},item.key,item.required === false ? ' · 可空' : ' · 必填',item.options ? ` · ${item.options.join(' / ')}` : '')))))));
}
