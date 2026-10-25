// Offline JS unit test with a small DOM/canvas double. Does not launch a
// browser, render screenshots, fetch URLs, or claim visual acceptance.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const name of ['rigid_check', 'upper_limb', 'lower_limb', 'bilateral']) {
  const file = path.join(__dirname, '..', 'preset_runs', `demo_${name}`, 'report.html');
  const html = fs.readFileSync(file, 'utf8');
  const payload = html.match(/<script id="session-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
  const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  const parsed = JSON.parse(payload);
  const elements = new Map();
  let animation;
  const coordinate = (...values) => assert.ok(values.every(Number.isFinite), 'Canvas coordinates must be finite');
  const canvas = {scale: coordinate, moveTo: coordinate, lineTo: coordinate, arc: coordinate,
    beginPath() {}, stroke() {}, fill() {}, fillText(text, x, y) {coordinate(x, y);}};
  function element(id = '') {
    if (!elements.has(id)) elements.set(id, {textContent: '', value: id === 'view' ? '-35' : '0', style: {}, children: [],
      append(...children) {this.children.push(...children);},
      getBoundingClientRect() {return {width: 440, height: id === 'chart' ? 270 : 350};},
      getContext() {return canvas;}});
    return elements.get(id);
  }
  element('session-data').textContent = payload;
  const context = vm.createContext({document: {getElementById: element,
    createElement: tag => ({...element(`created-${Math.random()}`), tag}),
    createTextNode: text => ({textContent: text})},
    devicePixelRatio: 1, requestAnimationFrame: callback => {animation = callback;}, addEventListener() {}});
  vm.runInContext(script, context, {filename: `report-${name}.js`, timeout: 3000});
  assert.equal(element('seek').max, parsed.result.frames.length-1);
  assert.ok(element('source').textContent.includes('合成演示数据'));
  element('seek').value = '100';
  element('seek').oninput();
  assert.equal(element('time').textContent, '2.00 s');
  element('view').value = '75';
  element('view').oninput();
  element('play').onclick();
  assert.equal(element('play').textContent, '暂停');
  animation(100);
  animation(140);
  assert.equal(Number(element('seek').value), 102);
  console.log(`Offline report script passed: ${name}`);
}
