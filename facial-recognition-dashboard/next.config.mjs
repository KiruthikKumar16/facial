import { loadEnvConfig } from '@next/env'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

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
  // @next/env handles overriding correctly (process.env wins over file for keys that already exist)
  process.env.ROOT_ENV_LOADED_FROM = rootEnv
  loadEnvConfig(rootDir, process.env.NODE_ENV !== 'production', {
    // minimal log; suppress "Load env" messages that reference the wrong dir
  })
} else {
  // Default Next.js behaviour: load from projectDir (facial-recognition-dashboard/.env*)
  loadEnvConfig(projectDir, process.env.NODE_ENV !== 'production')
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
