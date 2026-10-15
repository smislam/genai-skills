#!/usr/bin/env node
'use strict';
// Check that the vulnerability-data endpoints are reachable with the current proxy settings,
// and say exactly what to fix when they aren't. Usage: node net-check.js [--json]

const net = require('./lib/net');

const checks = [
  ['OSV.dev', () => net.postJSON(`${net.ENDPOINTS.osv}/querybatch`, { queries: [{ package: { ecosystem: 'npm', name: 'left-pad' }, version: '1.3.0' }] })],
  ['CISA KEV', () => net.request({ url: net.ENDPOINTS.kev })],
  ['FIRST EPSS', () => net.getJSON(`${net.ENDPOINTS.epss}?cve=CVE-2021-44228`)],
  ['Maven Central', () => net.request({ url: `${net.ENDPOINTS.maven}/org/springframework/boot/spring-boot-starter-parent/maven-metadata.xml` })],
];

const config = net.describeConfig();
const results = checks.map(([name, run]) => {
  const r = run();
  return { name, ok: r.ok, status: r.status, category: r.category || '', hint: r.hint || '' };
});

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify({ config, results }, null, 2) + '\n');
} else {
  console.log(`proxy=${config.proxy}${config.proxySource ? ` (${config.proxySource})` : ''} auth=${config.proxyAuth} ca=${config.caBundle}${config.noProxy ? ` no_proxy=${config.noProxy}` : ''}`);
  for (const r of results) {
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.name.padEnd(14)} ${r.ok ? `HTTP ${r.status}` : `${r.category}: ${r.hint}`}`);
  }
  // Maven Central is needed only for Maven/Gradle version resolution.
  const required = results.slice(0, 3);
  console.log(required.every((r) => r.ok) ? 'Vulnerability data: reachable.' : 'Vulnerability data: NOT reachable. Dependency results will be marked "not checked" until this is fixed.');
}
