/* Smoke test del client Pulsar senza l'editor: carica il package con un
 * `atom` globale stubbato, poi usa il suo startServerProcess() per avviare
 * il vero glls e fare un round-trip LSP initialize/shutdown su stdio.
 *
 * Uso: GLLS_BIN=/path/al/glls node ci/pulsar/smoke.js
 */
const assert = require("assert");
const path = require("path");
const Module = require("module");

const serverPath = process.env.GLLS_BIN || "glls";

// Il modulo 'atom' esiste solo dentro l'editor: stub minimale con le classi
// che atom-languageclient importa a livello di modulo.
class Disposable {
  dispose() {}
}
class CompositeDisposable extends Disposable {
  add() {}
}
class Emitter {
  on() {
    return new Disposable();
  }
  emit() {}
  dispose() {}
}
class Point {
  constructor(row = 0, column = 0) {
    this.row = row;
    this.column = column;
  }
}
class Range {
  constructor(start = new Point(), end = new Point()) {
    this.start = start;
    this.end = end;
  }
}
const fakeAtomModule = {
  Disposable,
  CompositeDisposable,
  Emitter,
  Point,
  Range,
  TextEditor: class {},
  TextBuffer: class {},
};
const origLoad = Module._load;
Module._load = function (request, ...rest) {
  if (request === "atom") return fakeAtomModule;
  if (request === "electron") return { shell: { openExternal: () => {} } };
  return origLoad.call(this, request, ...rest);
};

global.atom = {
  config: { get: (key) => (key === "glls-client.serverPath" ? serverPath : undefined) },
  notifications: {
    addError: (msg, opts) => {
      console.error("atom.notifications.addError:", msg, opts && opts.detail);
    },
  },
};

const client = require(path.resolve(__dirname, "../../clients/pulsar/src/main.js"));

assert.deepStrictEqual(client.getGrammarScopes(), ["source.yaml"]);
assert.strictEqual(client.getServerName(), "gl-ls");
assert.strictEqual(client.getLanguageName(), "Granulation Study YAML");
console.log("OK: package caricato, metadata corretti");

const child = client.startServerProcess();
assert(child && child.pid, "startServerProcess non ha restituito un processo");

// --- mini client JSON-RPC su stdio (framing LSP) ---------------------------

function send(msg) {
  const body = JSON.stringify(msg);
  child.stdin.write(`Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`);
}

let buf = Buffer.alloc(0);
const pending = new Map();
child.stdout.on("data", (chunk) => {
  buf = Buffer.concat([buf, chunk]);
  for (;;) {
    const headerEnd = buf.indexOf("\r\n\r\n");
    if (headerEnd < 0) return;
    const m = /Content-Length: (\d+)/.exec(buf.slice(0, headerEnd).toString());
    if (!m) return;
    const len = parseInt(m[1], 10);
    if (buf.length < headerEnd + 4 + len) return;
    const msg = JSON.parse(buf.slice(headerEnd + 4, headerEnd + 4 + len).toString());
    buf = buf.slice(headerEnd + 4 + len);
    if (msg.id !== undefined && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  }
});

function request(id, method, params) {
  return new Promise((resolve, reject) => {
    pending.set(id, resolve);
    setTimeout(() => reject(new Error(`timeout su ${method}`)), 15000);
    send({ jsonrpc: "2.0", id, method, params });
  });
}

(async () => {
  const init = await request(1, "initialize", {
    processId: process.pid,
    rootUri: null,
    capabilities: {},
  });
  assert(init.result && init.result.capabilities, "initialize senza capabilities");
  assert(init.result.capabilities.completionProvider, "manca completionProvider");
  assert(init.result.capabilities.hoverProvider, "manca hoverProvider");
  send({ jsonrpc: "2.0", method: "initialized", params: {} });
  await request(2, "shutdown", null);
  send({ jsonrpc: "2.0", method: "exit", params: null });
  console.log("OK: handshake LSP col server avviato dal client Pulsar");
  process.exit(0);
})().catch((err) => {
  console.error("FAIL:", err.message);
  child.kill();
  process.exit(1);
});
