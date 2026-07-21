import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by FastAPI under /leaderboard/ — base and outDir keep the build
// output landing exactly where leaderboard/api.py already expects it
// (leaderboard/static/index.html + leaderboard/static/assets/*).
export default defineConfig({
  base: '/leaderboard/',
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
