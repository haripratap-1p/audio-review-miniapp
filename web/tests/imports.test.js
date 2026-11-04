// module graph of web/js: no import cycles, every relative import is cache-busted with ?v=__V__
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const dir = new URL("../js/", import.meta.url);
const graph = {};
for (const f of readdirSync(dir).filter((f) => f.endsWith(".js"))) {
  const src = readFileSync(new URL(f, dir), "utf8");
  graph[f] = [...src.matchAll(/^\s*(?:import|export)\b[^"'`]*?from\s*["'](\.[^"']+)["']/gm)].map((m) => m[1]);
}

test("every relative import ends in ?v=__V__", () => {
  for (const [f, deps] of Object.entries(graph)) for (const d of deps) assert.match(d, /^\.\/[\w-]+\.js\?v=__V__$/, `${f} imports ${d}`);
});

test("no import cycles", () => {
  const done = new Set(), path = [];
  const visit = (f) => {
    assert.ok(!path.includes(f), `cycle: ${[...path.slice(path.indexOf(f)), f].join(" -> ")}`);
    if (done.has(f)) return;
    path.push(f);
    for (const d of graph[f] || []) visit(d.slice(2).split("?")[0]);
    path.pop();
    done.add(f);
  };
  Object.keys(graph).forEach(visit);
  assert.ok(Object.keys(graph).length > 5);
});
