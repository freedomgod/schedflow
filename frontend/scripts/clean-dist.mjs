import { rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Vite's emptyOutDir relies on recursive removal, which some Windows setups
// (sandboxed workspaces, AV filters, sync clients) silently block; stale
// hashed chunks then pile up in dist. Cleaning explicitly keeps every
// production build deterministic.
const projectDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const distDir = resolve(projectDir, 'dist')

rmSync(distDir, { recursive: true, force: true })
console.log('[clean-dist] removed', distDir)
