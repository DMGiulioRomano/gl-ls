/* Client Pulsar/Atom per gl-ls, basato su atom-languageclient. */
const { AutoLanguageClient } = require("atom-languageclient");
const cp = require("child_process");

class GllsLanguageClient extends AutoLanguageClient {
  getGrammarScopes() {
    return ["source.yaml"];
  }
  getLanguageName() {
    return "Granulation Study YAML";
  }
  getServerName() {
    return "gl-ls";
  }

  // Attiva il server solo se la prima riga del buffer e' "# gl-ls".
  // Il marker permette a piu' language server yaml di convivere nella
  // stessa directory senza convenzioni sul nome file.
  shouldStartForEditor(editor) {
    if (!super.shouldStartForEditor(editor)) return false;
    const firstLine = editor.lineTextForBufferRow(0) || "";
    return /^#\s*gl-ls\s*$/.test(firstLine);
  }

  startServerProcess() {
    const serverPath =
      atom.config.get("glls-client.serverPath") || "glls";
    const child = cp.spawn(serverPath, [], { stdio: "pipe" });
    child.on("error", (err) => {
      atom.notifications.addError("gl-ls: impossibile avviare il server", {
        detail:
          `${serverPath}: ${err.message}\n` +
          "Imposta glls-client.serverPath (Settings → Packages → glls-client).",
        dismissable: true,
      });
    });
    return child;
  }
}

module.exports = new GllsLanguageClient();
