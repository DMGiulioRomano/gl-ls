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

  // workspace temporaneo: fixture + settings che puntano al glls del CI
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "glls-ws-"));
  fs.copyFileSync(
    path.resolve(__dirname, "../fixtures/study.yml"),
    path.join(ws, "study.yml")
  );
  fs.mkdirSync(path.join(ws, ".vscode"));
  fs.writeFileSync(
    path.join(ws, ".vscode", "settings.json"),
    JSON.stringify({ "glls.serverPath": glls }, null, 2)
  );

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
  console.log("OK: integrazione VS Code riuscita");
})().catch((err) => {
  console.error("FAIL:", err.message || err);
  process.exit(1);
});
