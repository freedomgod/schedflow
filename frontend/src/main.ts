import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@logicflow/core/dist/index.css'

import './styles/components.css'
import App from './App.vue'
import router, { setupRouterGuard } from './router'
import { useAuthStore } from './stores/auth'
import { onSessionExpired } from './utils/session'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// Setup auth guard before mounting
setupRouterGuard(pinia)

// When the API reports an expired/invalid session: drop the in-memory auth
// state (the interceptor already cleared localStorage), tell the user once and
// send them to the login page with a path to come back to.
onSessionExpired((redirect) => {
  useAuthStore(pinia).clearAuth()
  ElMessage.warning('登录状态已失效，请重新登录')
  router.replace({ path: '/login', query: { redirect } })
})

// Wait for initial navigation to complete before mounting.
// This prevents AppLayout from briefly rendering and triggering
// authenticated API calls before the guard redirects to init-setup/login.
router.isReady().then(() => {
  app.mount('#app')
})
