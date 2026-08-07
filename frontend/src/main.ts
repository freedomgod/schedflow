import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@logicflow/core/dist/index.css'

import App from './App.vue'
import router, { setupRouterGuard } from './router'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// Setup auth guard before mounting
setupRouterGuard(pinia)

// Expose router on window for axios interceptor redirect
;(window as any).__router = router

// Wait for initial navigation to complete before mounting.
// This prevents AppLayout from briefly rendering and triggering
// authenticated API calls before the guard redirects to init-setup/login.
router.isReady().then(() => {
  app.mount('#app')
})
