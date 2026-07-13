/* Client VS Code per gl-ls: avvia `glls` su stdio per gli study.yml. */
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("glls");
  const serverPath = config.get("serverPath", "glls");
  const pattern = config.get("filePattern", "**/study.yml");

  const serverOptions = {
    command: serverPath,
    args: [],
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [
      { language: "yaml", pattern },
      { scheme: "file", pattern },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher(pattern),
    },
  };

  client = new LanguageClient(
    "glls",
    "gl-ls (Granulation Language Server)",
    serverOptions,
    clientOptions
  );

  client.start().catch((err) => {
    vscode.window.showErrorMessage(
      `gl-ls: impossibile avviare '${serverPath}': ${err.message}. ` +
        "Imposta glls.serverPath (es. il glls dentro il venv di gl-ls)."
    );
  });

  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
