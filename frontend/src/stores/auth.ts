import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getInitStatus, initSetup, login as apiLogin } from '@/api/auth'
import type { AuthResult } from '@/api/auth'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'schedflow_token'
const USER_KEY = 'schedflow_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const username = ref<string>(localStorage.getItem(USER_KEY) || '')
  const needInit = ref(false)
  const initChecked = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  function saveAuth(result: AuthResult) {
    token.value = result.token
    username.value = result.username
    localStorage.setItem(TOKEN_KEY, result.token)
    localStorage.setItem(USER_KEY, result.username)
  }

  function clearAuth() {
    token.value = ''
    username.value = ''
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function checkInitStatus(): Promise<boolean> {
    if (initChecked.value) return needInit.value
    try {
      const res = await getInitStatus()
      needInit.value = res.need_init
      initChecked.value = true
      return res.need_init
    } catch {
      return false
    }
  }

  async function doInitSetup(username_: string, password: string) {
    const result = await initSetup(username_, password)
    saveAuth(result)
    needInit.value = false
    initChecked.value = true
  }

  async function login(username_: string, password: string) {
    const result = await apiLogin(username_, password)
    saveAuth(result)
    ElMessage.success('登录成功')
  }

  function logout() {
    clearAuth()
    ElMessage.info('已退出登录')
  }

  return {
    token, username, needInit, initChecked, isAuthenticated,
    checkInitStatus, doInitSetup, login, logout,
  }
})
