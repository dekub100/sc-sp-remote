'use strict';

// The web UI is a no-build, plain-script project, so the DOM-free helpers are
// loaded into a VM context instead of being imported as modules.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(file) {
  const code = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const sandbox = { atob };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: file });
  return sandbox;
}

const lib = load('lib.js');
const filter = load('filter.js');

test('formatTime pads seconds and clamps bad input', () => {
  assert.equal(lib.formatTime(0), '0:00');
  assert.equal(lib.formatTime(59999), '0:59');
  assert.equal(lib.formatTime(61000), '1:01');
  assert.equal(lib.formatTime(-5000), '0:00');
  assert.equal(lib.formatTime(NaN), '0:00');
});

test('escapeHtml escapes all five entities', () => {
  assert.equal(
    lib.escapeHtml('<a href="x">&\'</a>'),
    '&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;'
  );
});

test('interpolateProgress extrapolates only while playing', () => {
  const now = Date.now();
  const paused = lib.interpolateProgress({
    isPlaying: false,
    progress: 1234,
    duration: 10000,
    timestamp: now,
  });
  assert.equal(paused.currentProgress, 1234);

  const playing = lib.interpolateProgress({
    isPlaying: true,
    progress: 1000,
    duration: 10000,
    timestamp: now - 5000,
    clientTimestamp: now - 5000,
  });
  assert.ok(playing.currentProgress >= 5900 && playing.currentProgress <= 6100);
});

test('interpolateProgress never runs past the duration', () => {
  const now = Date.now();
  const result = lib.interpolateProgress({
    isPlaying: true,
    progress: 9000,
    duration: 10000,
    timestamp: now - 60000,
    clientTimestamp: now - 60000,
  });
  assert.equal(result.currentProgress, 10000);
});

test('findLyricIndex picks the last line at or before the position', () => {
  const synced = [{ time: 0 }, { time: 1000 }, { time: 2500 }];
  assert.equal(lib.findLyricIndex(synced, -1), -1);
  assert.equal(lib.findLyricIndex(synced, 0), 0);
  assert.equal(lib.findLyricIndex(synced, 1499), 1);
  assert.equal(lib.findLyricIndex(synced, 99999), 2);
  assert.equal(lib.findLyricIndex([], 500), -1);
});

test('filterText leaves clean text untouched', () => {
  assert.equal(filter.filterText(''), '');
  assert.equal(filter.filterText('hello world'), 'hello world');
  assert.equal(filter.filterText(null), null);
});

test('filterText masks a listed word and respects word boundaries', () => {
  // Pick a term out of the loaded list so the test file itself adds no slurs.
  const term = vm.runInContext('_slurList[0]', filter);
  const masked = '*'.repeat(term.length);
  assert.equal(filter.filterText(`say ${term} now`), `say ${masked} now`);
  assert.equal(filter.filterText(`x${term}x`), `x${term}x`);
});
