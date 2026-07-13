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

local function is_study(bufname)
  return bufname:match("study%.yml$") ~= nil
end

if vim.lsp.config then
  -- Neovim >= 0.11
  vim.lsp.config("glls", {
    cmd = cmd,
    filetypes = { "yaml" },
    root_markers = { "study.yml", ".git" },
  })
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "yaml",
    callback = function(args)
      if is_study(vim.api.nvim_buf_get_name(args.buf)) then
        vim.lsp.enable("glls")
      end
    end,
  })
else
  -- Neovim 0.8–0.10: vim.lsp.start diretto
  vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile" }, {
    pattern = "study.yml",
    callback = function(args)
      vim.lsp.start({
        name = "glls",
        cmd = cmd,
        root_dir = vim.fs.dirname(
          vim.fs.find({ ".git", "study.yml" }, { upward = true, path = args.file })[1]
        ),
      })
    end,
  })
end

-- Consigli:
--   vim.lsp.inlay_hint.enable(true)                  -- conversioni hz/s/bpm inline
--   vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action)  -- i ricalcoli
--   vim.keymap.set("n", "K", vim.lsp.buf.hover)
