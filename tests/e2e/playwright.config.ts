import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: [
    { command: 'python -m apps.api.app.seed --reset && python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/health', cwd: projectRoot, reuseExistingServer: true },
    { command: 'npm run dev -- --port 5173', url: 'http://127.0.0.1:5173', cwd: path.join(projectRoot, 'apps/web'), reuseExistingServer: true },
  ],
})
