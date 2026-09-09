// 验证默认机会库输入覆盖 Pending/Scored，显式 URL/文件仍可限定范围。
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { collectPipelineUrls, loadLivenessUrls } from '../check-liveness.mjs';

const fixture = `# Pipeline
## Pending
- [ ] https://example.com/1 | A | Role
- [!] https://example.com/2 — Error: login required
- [ ] local:jds/snapshot.md | C | Role | note: https://example.com/snapshot
## Scored（已评分 · 可手动启动申请）
- [~] #001 | https://example.com/3 | D | Role | 4.2/5 | Report: reports/001.md
- [~] #002 | https://example.com/1 | A | Duplicate
## Processed
- [x] https://example.com/4 | Closed
- [ ] https://example.com/5 | Misplaced
## Pendientes
- [ ] https://example.com/6
## Awaiting Confirmation
- [~] #003 | https://example.com/7
## 已评分
- [~] #004 | https://example.com/8
## Other
- [ ] https://example.com/9
`;
const expected = [1, 2, 3, 6, 7, 8].map(id => `https://example.com/${id}`);
assert.deepEqual(collectPipelineUrls(fixture.replaceAll('\n', '\r\n')), expected);

const dir = mkdtempSync(join(tmpdir(), 'career-liveness-'));
const previous = process.env.CAREER_OPS_PIPELINE;
try {
  const pipeline = join(dir, 'pipeline.md');
  writeFileSync(pipeline, fixture);
  process.env.CAREER_OPS_PIPELINE = pipeline;
  assert.deepEqual(await loadLivenessUrls([]), expected);
  assert.deepEqual(await loadLivenessUrls(['https://example.com/explicit']), ['https://example.com/explicit']);
  const list = join(dir, 'urls.txt');
  writeFileSync(list, '# URL list\n\nhttps://example.com/file\n');
  assert.deepEqual(await loadLivenessUrls(['--file', list]), ['https://example.com/file']);
  await assert.rejects(loadLivenessUrls(['--file']), /需要/);
  await assert.rejects(loadLivenessUrls(['--invalid']), /未知参数/);
  assert.equal(readFileSync(pipeline, 'utf-8'), fixture);
  writeFileSync(pipeline, '## Processed\n- [x] https://example.com/closed\n');
  const script = fileURLToPath(new URL('../check-liveness.mjs', import.meta.url));
  const output = execFileSync(process.execPath, [script], { encoding: 'utf-8' });
  assert.match(output, /Checking 0 URL/);
  assert.equal(readFileSync(pipeline, 'utf-8'), '## Processed\n- [x] https://example.com/closed\n');
  const apiFixture = `## Pending
- [ ] https://boards.greenhouse.io/acme/jobs/1
## Scored（已评分）
- [~] #001 | https://boards.greenhouse.io/acme/jobs/2 | Acme | Role
## Processed
- [x] https://boards.greenhouse.io/acme/jobs/3
`;
  writeFileSync(pipeline, apiFixture);
  const mock = join(dir, 'fetch.mjs');
  writeFileSync(mock, `// 固定公共 API 响应，真实 CLI 与检测器在离线环境执行。
globalThis.fetch = async url => {
  if (!['1', '2'].some(id => url === 'https://boards-api.greenhouse.io/v1/boards/acme/jobs/' + id)) throw new Error('Unexpected request');
  return new Response('', { status: url.endsWith('/2') ? 404 : 200 });
};
`);
  const run = spawnSync(process.execPath, ['--import', mock, script], { encoding: 'utf-8', timeout: 5000 });
  assert.equal(run.status, 1, run.stderr);
  assert.match(run.stdout, /1 active  1 expired  0 uncertain  \(2 via API/);
  assert.equal(readFileSync(pipeline, 'utf-8'), apiFixture);

} finally {
  if (previous === undefined) delete process.env.CAREER_OPS_PIPELINE;
  else process.env.CAREER_OPS_PIPELINE = previous;
  rmSync(dir, { recursive: true, force: true });
}
console.log('✓ 默认 Pending/Scored、区段隔离、去重、显式输入及只读 CLI 检查通过');
