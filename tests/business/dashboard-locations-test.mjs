// Verify Dashboard city filters, bilingual search and persisted filter controls.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const page = readFileSync(new URL('../../career_ops/dashboard/index.html', import.meta.url), 'utf8');
const script = page.split('<script>')[1].split('</script>')[0].split('\ndocument.addEventListener("click"')[0];
const elements = new Map();
const context = vm.createContext({
  assert,
  document: { getElementById(id) {
    if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '', classList: { toggle() {} } });
    return elements.get(id);
  } },
});
vm.runInContext(script + `
  jobs = [
    { id: 1, stage: 'scanned', company: 'A', source: 'search', location_cities: ['香港'], location_search: '香港 Hong Kong HK' },
    { id: 2, stage: 'scanned', company: 'B', source: 'search', location_cities: ['北京', '上海'], location_search: '北京 上海 Beijing Shanghai' },
    { id: 3, stage: 'scanned', company: 'C', source: 'search', location_cities: [], location_search: 'Remote' },
  ];
  const ids = () => filtered().map(j => j.id).join(',');
  state.city = '香港';
  assert.equal(ids(), '1');
  for (const q of ['香港', 'Hong Kong', 'HK']) {
    state.q = q;
    assert.equal(ids(), '1');
  }
  state.q = '';
  for (const city of ['北京', '上海']) {
    state.city = city;
    assert.equal(ids(), '2');
  }
  fillSelects();
  assert.equal($('fCity').value, '上海');
  assert.equal(($('fCity').innerHTML.match(/<option>上海/g) || []).length, 1);
  state.city = '不存在的城市';
  fillSelects();
  assert.equal(state.city, '');
  assert.equal(ids(), '1,2,3');
  jobs = [];
  state.q = '香港';
  render();
  assert.equal($('q').value, '香港');
  state.q = '';
  render();
  assert.equal($('q').value, '');
`, context);
console.log('dashboard locations: ok');
