import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Pinia } from 'pinia'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/Login.vue'),
      meta: { public: true },
    },
    {
      path: '/init-setup',
      name: 'init-setup',
      component: () => import('@/views/auth/InitSetup.vue'),
      meta: { public: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { title: '仪表盘' },
    },
    {
      path: '/jobs',
      name: 'jobs',
      component: () => import('@/views/jobs/JobList.vue'),
      meta: { title: '工作流管理' },
    },
    {
      path: '/jobs/:id',
      name: 'job-detail',
      component: () => import('@/views/jobs/JobDetail.vue'),
      meta: { title: '工作流详情' },
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/logs/JobLogViewer.vue'),
      meta: { title: '任务日志' },
    },
    {
      path: '/logs/:jobId',
      redirect: (to) => ({
        path: '/logs',
        query: { jobId: to.params.jobId as string, ...to.query },
      }),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/settings/SystemSettings.vue'),
      meta: { title: '系统设置' },
    },
    {
      path: '/storage-config',
      name: 'storage-config',
      component: () => import('@/views/components/StorageConfig.vue'),
      meta: { title: '存储配置' },
    },
    {
      path: '/executor-config',
      name: 'executor-config',
      component: () => import('@/views/components/ExecutorConfig.vue'),
      meta: { title: '执行器配置' },
    },
  ],
})

export function setupRouterGuard(pinia: Pinia) {
  router.beforeEach(async (to, _from, next) => {
    const authStore = useAuthStore(pinia)

    // Init-setup: only allow if system actually needs init
    if (to.path === '/init-setup') {
      const needsInit = await authStore.checkInitStatus()
      if (!needsInit) {
        next(authStore.isAuthenticated ? '/dashboard' : '/login')
        return
      }
      next()
      return
    }

    // Login page: if already authenticated, skip to dashboard
    if (to.path === '/login') {
      if (authStore.isAuthenticated) {
        next('/dashboard')
        return
      }
      next()
      return
    }

    if (to.meta.public) {
      next()
      return
    }

    const needsInit = await authStore.checkInitStatus()

    if (needsInit) {
      next('/init-setup')
      return
    }

    if (!authStore.isAuthenticated) {
      next('/login')
      return
    }

    next()
  })
}

export default router
