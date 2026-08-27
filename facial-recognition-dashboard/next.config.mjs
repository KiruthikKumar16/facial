import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

function loadRootPublicEnv(envFile) {
  for (const line of fs.readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^(NEXT_PUBLIC_(?:API_URL|WS_URL))=(.*)$/)
    if (match && !process.env[match[1]]) {
      process.env[match[1]] = match[2].trim().replace(/^['"]|['"]$/g, '')
    }
  }
}

/**
 * Load .env from the MONOREPO ROOT (parent of facial-recognition-dashboard/).
 *
 * Directory layout:
 *   repo/                         <-- root .env lives here
 *     facial-recognition-dashboard/
 *       next.config.mjs           <-- this file
 *
 * On Vercel, environment variables are injected by the platform so there is
 * usually no .env file on disk — the file existence check below makes this
 * a safe no-op in production while still supporting local single-file env.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectDir = __dirname
const rootDir = path.resolve(projectDir, '..')
const rootEnv = path.join(rootDir, '.env')

if (fs.existsSync(rootEnv)) {
  // Vercel-injected variables always win; this only supports the root .env in local dev.
  process.env.ROOT_ENV_LOADED_FROM = rootEnv
  loadRootPublicEnv(rootEnv)
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  env: {
    // Explicitly expose NEXT_PUBLIC_* vars from root .env so Next.js picks them
    // up even if they were loaded from outside the project directory.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
  },
}

export default nextConfig
