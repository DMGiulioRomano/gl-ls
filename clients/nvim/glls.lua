-- gl-ls per Neovim.
--
-- Uso (Neovim >= 0.11, API vim.lsp.config):
--   require("glls")            -- se il file sta in ~/.config/nvim/lua/glls.lua
-- oppure copia il contenuto in init.lua.
--
-- Il server e' `glls` (venv di gl-ls). Cambia `cmd` se non e' nel PATH.

local cmd = { "glls" }
-- esempio con venv esplicito:
-- local cmd = { vim.fn.expand("~/gl-ls/.venv/bin/glls") }

-- Attivazione per marker: la prima riga del file deve essere "# gl-ls".
-- Convenzione condivisa tra piu' language server per yaml nello stesso repo:
-- ognuno riconosce la propria etichetta, cosi' file diversi nella stessa
-- directory possono agganciarsi a server diversi senza rinominarli.
local MARKER = "^#%s*gl%-ls%s*$"

local function has_marker(bufnr)
  local first_line = vim.api.nvim_buf_get_lines(bufnr, 0, 1, false)[1]
  return first_line ~= nil and first_line:match(MARKER) ~= nil
end

if vim.lsp.config then
  -- Neovim >= 0.11
  vim.lsp.config("glls", {
    cmd = cmd,
    filetypes = { "yaml" },
    root_markers = { ".git" },
  })
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "yaml",
    callback = function(args)
      if has_marker(args.buf) then
        vim.lsp.enable("glls")
      end
    end,
  })
else
  -- Neovim 0.8–0.10: vim.lsp.start diretto
  vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile" }, {
    pattern = "*.yml,*.yaml",
    callback = function(args)
      if not has_marker(args.buf) then
        return
      end
      vim.lsp.start({
        name = "glls",
        cmd = cmd,
        root_dir = vim.fs.dirname(
          vim.fs.find({ ".git" }, { upward = true, path = args.file })[1]
        ),
      })
    end,
  })
end

-- Consigli:
--   vim.lsp.inlay_hint.enable(true)                  -- conversioni hz/s/bpm inline
--   vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action)  -- i ricalcoli
--   vim.keymap.set("n", "K", vim.lsp.buf.hover)

-- Semantic token: funzionano senza config. streams (namespace) e spread
-- (decorator) prendono gia' colori distinti dai default di Neovim. Le sezioni
-- axes/stack/base (struct) invece ricadono su Type, lo stesso dei nomi d'asse.
-- Scommenta per distinguerle (adatta il colore al tuo colorscheme):
--   vim.api.nvim_set_hl(0, "@lsp.type.struct.yaml", { link = "Special" })
