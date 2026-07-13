/* Corpo del test eseguito DENTRO VS Code: apre study.yml nel workspace e
 * attende le diagnostiche con source "gl-ls" pubblicate dal server. */
const path = require("path");
const vscode = require("vscode");

async function run() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) throw new Error("nessun workspace aperto");
  const file = path.join(folder.uri.fsPath, "study.yml");

  const doc = await vscode.workspace.openTextDocument(file);
  await vscode.window.showTextDocument(doc);

  const deadline = Date.now() + 60000;
  for (;;) {
    const diags = vscode.languages
      .getDiagnostics(doc.uri)
      .filter((d) => d.source === "gl-ls");
    if (diags.length > 0) {
      console.log(`OK: ${diags.length} diagnostiche gl-ls (prima: ${diags[0].message})`);
      return;
    }
    if (Date.now() > deadline) {
      throw new Error("nessuna diagnostica gl-ls entro 60s");
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

module.exports = { run };
