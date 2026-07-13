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

  // Attiva il server solo per gli study.yml
  shouldStartForEditor(editor) {
    if (!super.shouldStartForEditor(editor)) return false;
    const path = editor.getPath() || "";
    return /study\.yml$/.test(path);
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
