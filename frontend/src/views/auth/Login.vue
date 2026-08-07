<template>
  <div class="auth-wrapper">
    <!-- Background dots -->
    <div class="auth-bg-dots"></div>
    <!-- Ambient blobs -->
    <div class="auth-blob auth-blob-1"></div>
    <div class="auth-blob auth-blob-2"></div>

    <div class="auth-card glass-card">
      <div class="auth-logo">
        <svg width="36" height="36" viewBox="0 0 28 28" fill="none">
          <rect width="28" height="28" rx="8" fill="url(#auth-logo-grad)"/>
          <path d="M8 10h4v8H8zM16 7h4v11h-4zM12 14h4v4h-4z" fill="white" opacity="0.9"/>
          <defs>
            <linearGradient id="auth-logo-grad" x1="0" y1="0" x2="28" y2="28">
              <stop stop-color="#3B82F6"/>
              <stop offset="1" stop-color="#818CF8"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
      <h1 class="auth-title">SchedFlow</h1>
      <p class="auth-subtitle">任务调度管理系统</p>

      <form class="auth-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label class="form-label">用户名</label>
          <input
            v-model="form.username"
            class="form-input"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
          />
        </div>
        <div class="form-group">
          <label class="form-label">密码</label>
          <input
            v-model="form.password"
            class="form-input"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="handleLogin"
          />
        </div>
        <button type="submit" class="auth-btn" :disabled="loading">
          <span v-if="loading" class="btn-spinner"></span>
          <span v-else>登 录</span>
        </button>
      </form>

      <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({ username: '', password: '' })

async function handleLogin() {
  errorMsg.value = ''
  if (!form.username.trim()) { errorMsg.value = '请输入用户名'; return }
  if (!form.password) { errorMsg.value = '请输入密码'; return }

  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    router.push('/dashboard')
  } catch (e: any) {
    errorMsg.value = e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-deep);
  position: relative;
  overflow: hidden;
}

/* ── BG Dots Pattern ── */
.auth-bg-dots {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, var(--border-subtle) 1px, transparent 1px);
  background-size: 24px 24px;
  opacity: 0.5;
}

/* ── Ambient blobs ── */
.auth-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
  opacity: 0.12;
}
.auth-blob-1 {
  width: 400px;
  height: 400px;
  background: var(--color-primary);
  top: -100px;
  right: -100px;
  animation: blob-drift 15s ease-in-out infinite;
}
.auth-blob-2 {
  width: 300px;
  height: 300px;
  background: #818CF8;
  bottom: -80px;
  left: -80px;
  animation: blob-drift 18s ease-in-out infinite reverse;
}

@keyframes blob-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
}

/* ── Card ────────── */
.auth-card {
  position: relative;
  z-index: 1;
  width: 400px;
  max-width: 90vw;
  padding: 44px 40px;
  text-align: center;
}

.auth-logo {
  margin-bottom: 16px;
}

.auth-title {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.auth-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 32px;
}

/* ── Form ────────── */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group {
  text-align: left;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 11px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-body);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  outline: none;
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-soft);
}

/* ── Button ──────── */
.auth-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 12px;
  margin-top: 4px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--color-primary), #6366F1);
  color: white;
  font-size: 15px;
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: opacity var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.auth-btn:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow);
}
.auth-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}
.auth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Error ───────── */
.auth-error {
  margin: 16px 0 0;
  font-size: 13px;
  color: var(--color-danger);
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .auth-blob { animation: none; }
}
</style>
