/* Client VS Code per gl-ls: avvia `glls` su stdio per i file yaml che
 * dichiarano "# gl-ls" come prima riga. Il marker permette a piu' language
 * server yaml di convivere nella stessa directory senza convenzioni sul
 * nome file. */
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

const MARKER = /^#\s*gl-ls\s*$/;

function hasMarker(document) {
  return MARKER.test(document.lineAt(0).text);
}

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("glls");
  const serverPath = config.get("serverPath", "glls");

  const serverOptions = {
    command: serverPath,
    args: [],
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [{ language: "yaml" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{yml,yaml}"),
    },
    middleware: {
      didOpen: (document, next) => {
        if (hasMarker(document)) {
          return next(document);
        }
      },
    },
  };

  client = new LanguageClient(
    "glls",
    "gl-ls (Granulation Language Server)",
    serverOptions,
    clientOptions
  );

  client.start().catch((err) => {
    console.error(`gl-ls: avvio fallito ('${serverPath}'):`, err);
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
