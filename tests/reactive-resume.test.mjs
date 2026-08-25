/**
 * Verify the managed-copy seam without touching the user's local service.
 */

import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildResumePatch, renderReactiveResume } from '../reactive-resume.mjs';

const root = await mkdtemp(join(tmpdir(), 'career-ops-reactive-resume-'));
try {
  const inputPath = join(root, 'output', '007-acme-role', 'cv', 'tailored', 'v001', 'cv.json');
  const metadataPath = join(root, 'output', '007-acme-role', 'cv', 'reactive-resume.json');
  const outputPath = join(root, 'output', '007-acme-role', 'cv', 'tailored', 'v001', 'cv.pdf');
  const payload = {
    page_format: 'a4',
    candidate: {
      name: 'Jane Doe', email: 'jane@example.com', phone: '+1 555', location: 'Berlin',
      linkedin: { url: 'https://linkedin.com/in/jane', display: 'linkedin.com/in/jane' },
      portfolio: { url: 'https://jane.example', display: 'jane.example' },
    },
    sections: { competencies: 'Core Competencies', experience: 'Work Experience' },
    summary: 'Builds reliable AI systems.',
    competencies: ['LLMOps', 'RAG'],
    experience: [{ company: 'Acme', role: 'Engineer', dates: '2024 - Present', bullets: ['Shipped <safe> systems'] }],
    projects: [], education: [], certifications: [], awards: [],
    skills: [{ category: 'Languages', items: 'Python, TypeScript' }],
  };
  let updatedAt = '2026-08-25T00:00:00.000Z';
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const path = new URL(url).pathname.replace('/api/openapi', '');
    const method = init.method ?? 'GET';
    calls.push({ method, path, body: init.body && JSON.parse(init.body) });
    if (method === 'GET' && path === '/resumes') return Response.json([]);
    if (method === 'POST' && path.endsWith('/duplicate')) return Response.json('resume-007');
    if (method === 'GET' && path === '/resumes/resume-007') {
      return Response.json({ id: 'resume-007', name: 'Career Ops #007 — Acme — Role', slug: 'career-ops-r007', updatedAt });
    }
    if (method === 'PATCH' && path === '/resumes/resume-007') {
      updatedAt = '2026-08-25T00:01:00.000Z';
      return Response.json({ id: 'resume-007', updatedAt });
    }
    if (method === 'GET' && path === '/resumes/resume-007/pdf') {
      return new Response(Buffer.from('%PDF-test'), { headers: { 'content-type': 'application/pdf' } });
    }
    return new Response('unexpected request', { status: 500 });
  };
  const options = {
    payload, inputPath, outputPath, metadataPath, reportNum: 7, company: 'Acme', role: 'Role', version: 1,
    baseResumeId: 'base-id', apiBaseUrl: 'http://127.0.0.1:3000/api/openapi', apiKey: 'test-key', fetchImpl,
    recordManifest: false,
  };
  await renderReactiveResume(options);
  await renderReactiveResume(options);

  assert.equal(calls.filter((call) => call.method === 'POST').length, 1, 'the base resume is duplicated only once');
  assert.equal(calls.filter((call) => call.method === 'PATCH').length, 2, 'reruns patch the stable managed copy');
  assert.equal(JSON.parse(await readFile(metadataPath, 'utf8')).resume_id, 'resume-007');
  assert.equal((await readFile(outputPath)).toString(), '%PDF-test');
  const operations = buildResumePatch(payload);
  assert.equal(operations.find((op) => op.path === '/sections/skills/items').value[0].name, 'Core Competencies');
  assert.match(operations.find((op) => op.path === '/sections/experience/items').value[0].description, /&lt;safe&gt;/);
  assert.equal(operations.some((op) => op.path.startsWith('/picture')), false, 'the base portrait is preserved');
  assert.equal(operations.find((op) => op.path === '/basics/headline').value, '', 'unverified base content is cleared');
  assert.deepEqual(operations.find((op) => op.path === '/customSections').value, [], 'base custom content is cleared');
  assert.deepEqual(operations.find((op) => op.path === '/sections/languages/items').value, [], 'unmapped base sections are cleared');
  await assert.rejects(
    renderReactiveResume({ ...options, payload: { summary: '' }, fetchImpl: () => { throw new Error('must not call API'); } }),
    /candidate\.name is required/,
  );
  console.log('  ✅ Reactive Resume duplicates once, patches deterministically, preserves visuals, and downloads PDF');
} finally {
  await rm(root, { recursive: true, force: true });
}
