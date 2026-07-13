-- Smoke test headless del client Neovim: carica il VERO clients/nvim/glls.lua,
-- apre la fixture study.yml e attende le diagnostiche pubblicate da glls.
-- Esce 0 se arrivano, exit code != 0 altrimenti (via :cq).
--
-- Uso: GLLS_FIXTURE=ci/fixtures/study.yml nvim --headless -u NONE \
--        +"luafile ci/nvim/smoke.lua"

local fixture = os.getenv("GLLS_FIXTURE")
if not fixture or vim.fn.filereadable(fixture) == 0 then
  io.stderr:write("FAIL: fixture non trovata: " .. tostring(fixture) .. "\n")
  vim.cmd("cq")
end

vim.cmd("filetype plugin on")

local ok, err = pcall(dofile, "clients/nvim/glls.lua")
if not ok then
  io.stderr:write("FAIL: clients/nvim/glls.lua non carica: " .. tostring(err) .. "\n")
  vim.cmd("cq")
end

vim.cmd("edit " .. vim.fn.fnameescape(fixture))
vim.bo.filetype = "yaml" -- forza il FileType anche con -u NONE

local attached = vim.wait(15000, function()
  return #vim.lsp.get_clients({ bufnr = 0, name = "glls" }) > 0
end, 100)
if not attached then
  io.stderr:write("FAIL: il client glls non si e' attaccato al buffer\n")
  vim.cmd("cq")
end

local got = vim.wait(15000, function()
  return #vim.diagnostic.get(0) > 0
end, 100)
if not got then
  io.stderr:write("FAIL: nessuna diagnostica ricevuta da gl-ls\n")
  vim.cmd("cq")
end

local diags = vim.diagnostic.get(0)
print(("OK: %d diagnostiche (prima: %s)"):format(#diags, diags[1].message))
vim.cmd("qa!")
