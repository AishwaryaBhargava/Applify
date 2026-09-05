import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * The dependency groups that are worth their own file.
 *
 * Each one is large, versioned independently of our code, and used by a subset
 * of the routes — so splitting them means a deploy of application code does not
 * invalidate them in the browser cache, and a visitor who never opens a chat
 * never downloads the markdown renderer.
 *
 * Matched against the package directory name, which is the segment right after
 * `node_modules/` (or after the scope, for a scoped package).
 */
const VENDOR_CHUNKS: { name: string; test: RegExp }[] = [
  // Supabase's client pulls in auth, realtime, storage and postgrest.
  { name: 'supabase', test: /^@supabase\// },
  // react-markdown and the whole unified / micromark pipeline behind it. Only
  // the chat thread and the analysis narrative render markdown.
  {
    name: 'markdown',
    test: /^(react-markdown|unified|remark-.*|rehype-.*|micromark.*|mdast-.*|hast-.*|unist-.*|vfile.*|property-information|space-separated-tokens|comma-separated-tokens|html-url-attributes|character-entities.*|decode-named-character-reference|trim-lines|longest-streak|zwitch|ccount|markdown-table|devlop|bail|is-plain-obj|trough|extend)$/,
  },
  // React itself plus the router: on every page, changed rarely.
  { name: 'react-vendor', test: /^(react|react-dom|react-router|react-router-dom|scheduler|use-sync-external-store)$/ },
]

/** The package name a module id belongs to, or null outside node_modules. */
function packageName(id: string): string | null {
  const normalized = id.replace(/\\/g, '/')
  const index = normalized.lastIndexOf('node_modules/')
  if (index === -1) return null
  const rest = normalized.slice(index + 'node_modules/'.length).split('/')
  return rest[0]?.startsWith('@') ? `${rest[0]}/${rest[1]}` : (rest[0] ?? null)
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const pkg = packageName(id)
          if (!pkg) return undefined
          return VENDOR_CHUNKS.find((chunk) => chunk.test.test(pkg))?.name
        },
      },
    },
  },
})
