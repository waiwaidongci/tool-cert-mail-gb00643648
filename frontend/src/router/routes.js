export const pages = ['overview', 'inputs', 'run', 'results', 'review', 'delivery', 'trace'];

export function route() {
  const [path, search] = location.hash.slice(1).split('?');
  const [page, id, third, fourth] = path.split('/');
  const numeric = /^\d+$/.test(third || '');
  return {
    page:pages.includes(page) ? page : 'overview',
    id:Number(id) || null,
    offset: numeric ? Number(third) : 0,
    arg: (numeric ? fourth : third) ? decodeURIComponent(numeric ? fourth : third) : null,
    query: Object.fromEntries(new URLSearchParams(search || '')),
  };
}
