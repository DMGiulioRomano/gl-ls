/* Lancia VS Code (via @vscode/test-electron) con l'estensione clients/vscode
 * e il test di suite/index.js su un workspace temporaneo con la fixture.
 *
 * Uso: GLLS_BIN=/path/al/glls node ci/vscode-test/runTests.js
 * (in CI dentro xvfb-run per il display virtuale)
 */
const path = require("path");
const fs = require("fs");
const os = require("os");
const { runTests } = require("@vscode/test-electron");

(async () => {
  const glls = process.env.GLLS_BIN;
  if (!glls || !fs.existsSync(glls)) {
    throw new Error(`GLLS_BIN mancante o inesistente: ${glls}`);
  }

  // wrapper diagnostico: logga spawn/env e cattura lo stderr del server,
  // cosi' un crash durante l'initialize resta leggibile nel log del job
  const diag = fs.mkdtempSync(path.join(os.tmpdir(), "glls-diag-"));
  const stderrLog = path.join(diag, "server-stderr.log");
  const spawnLog = path.join(diag, "spawn.log");
  const wrapper = path.join(diag, "glls-wrapped");
  fs.writeFileSync(
    wrapper,
    `#!/bin/bash
{
  echo "== spawn $(date -Is) args: $*"
  echo "PATH=$PATH"
  env | grep -E '^(LD_LIBRARY_PATH|PYTHON|ELECTRON|NODE_OPTIONS|VSCODE_)' || true
} >> ${JSON.stringify(spawnLog)}
exec ${JSON.stringify(glls)} "$@" 2>> ${JSON.stringify(stderrLog)}
`
  );
  fs.chmodSync(wrapper, 0o755);

  // workspace temporaneo: fixture + settings che puntano al glls del CI
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "glls-ws-"));
  fs.copyFileSync(
    path.resolve(__dirname, "../fixtures/study.yml"),
    path.join(ws, "study.yml")
  );
  fs.mkdirSync(path.join(ws, ".vscode"));
  fs.writeFileSync(
    path.join(ws, ".vscode", "settings.json"),
    JSON.stringify({ "glls.serverPath": wrapper }, null, 2)
  );

  const dumpDiag = () => {
    for (const f of [spawnLog, stderrLog]) {
      console.log(`--- ${path.basename(f)} ---`);
      console.log(fs.existsSync(f) ? fs.readFileSync(f, "utf8") : "(vuoto)");
    }
  };

  try {
    await runTests({
      extensionDevelopmentPath: path.resolve(__dirname, "../../clients/vscode"),
      extensionTestsPath: path.resolve(__dirname, "suite"),
      launchArgs: [
        ws,
        "--disable-workspace-trust",
        "--disable-gpu",
        "--disable-extensions", // solo la nostra, niente builtin di terze parti
      ],
    });
  } catch (err) {
    dumpDiag();
    throw err;
  }
  dumpDiag();
  console.log("OK: integrazione VS Code riuscita");
})().catch((err) => {
  console.error("FAIL:", err.message || err);
  process.exit(1);
});
