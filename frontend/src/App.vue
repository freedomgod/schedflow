<template>
  <el-config-provider :locale="zhCn">
    <router-view v-if="isPublicRoute" />
    <AppLayout v-else />
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useTheme } from '@/composables/useTheme'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const isPublicRoute = computed(() => !!route.meta.public)

const settingsStore = useSettingsStore()

watch(isPublicRoute, (isPublic) => {
  if (!isPublic) {
    settingsStore.fetchTheme()
  }
}, { immediate: true })

useTheme()
</script>

<style>
/* ═══════════════════════════════════════════════════
   SchedFlow — Design System
   Modern Dark (Cinema Mobile) with Glassmorphism
   ═══════════════════════════════════════════════════ */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-body);
  background: var(--bg-deep);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  transition: background-color var(--transition-base), color var(--transition-base);
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-heading);
  font-weight: 600;
  letter-spacing: -0.01em;
}

code, pre, kbd, samp {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
}

/* ── Design Tokens (Dark — default) ────────────── */
:root {
  /* Background layers */
  --bg-deep: #0a0a0f;
  --bg-base: #0f0f14;
  --bg-elevated: #1a1a24;
  --bg-surface: rgba(255, 255, 255, 0.04);
  --bg-surface-hover: rgba(255, 255, 255, 0.07);

  /* Brand / semantic colors */
  --color-primary: #3B82F6;
  --color-primary-hover: #60A5FA;
  --color-primary-soft: rgba(59, 130, 246, 0.15);
  --color-success: #22C55E;
  --color-success-soft: rgba(34, 197, 94, 0.15);
  --color-warning: #F59E0B;
  --color-warning-soft: rgba(245, 158, 11, 0.15);
  --color-danger: #EF4444;
  --color-danger-soft: rgba(239, 68, 68, 0.15);
  --color-info: #6366F1;
  --color-info-soft: rgba(99, 102, 241, 0.15);
  --color-accent: #D97706;

  /* Text hierarchy */
  --text-primary: rgba(255, 255, 255, 0.92);
  --text-secondary: rgba(255, 255, 255, 0.60);
  --text-muted: rgba(255, 255, 255, 0.38);
  --text-inverse: rgba(15, 23, 42, 0.92);

  /* Borders */
  --border-subtle: rgba(255, 255, 255, 0.07);
  --border-default: rgba(255, 255, 255, 0.12);
  --border-strong: rgba(255, 255, 255, 0.18);

  /* Radii */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* Shadows (dark mode) */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 24px rgba(59, 130, 246, 0.15);
  --shadow-glow-success: 0 0 20px rgba(34, 197, 94, 0.12);

  /* Spacing scale */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;

  /* Typography */
  --font-heading: 'Fira Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-body: 'Fira Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;

  /* Transitions */
  --transition-fast: 150ms ease;
  --transition-base: 200ms ease;
  --transition-slow: 300ms cubic-bezier(0.16, 1, 0.3, 1);

  /* Glass effect */
  --glass-bg: rgba(255, 255, 255, 0.05);
  --glass-bg-hover: rgba(255, 255, 255, 0.08);
  --glass-border: rgba(255, 255, 255, 0.10);
  --glass-blur: 16px;

  /* Sidebar */
  --sidebar-width: 240px;
  --sidebar-collapsed-width: 64px;
  --topbar-height: 60px;
}

/* ── Light Theme Overrides ─────────────────────── */
html:not(.dark) {
  --bg-deep: #F8FAFC;
  --bg-base: #FFFFFF;
  --bg-elevated: #F1F5F9;
  --bg-surface: rgba(0, 0, 0, 0.02);
  --bg-surface-hover: rgba(0, 0, 0, 0.05);

  --text-primary: rgba(15, 23, 42, 0.92);
  --text-secondary: rgba(15, 23, 42, 0.60);
  --text-muted: rgba(15, 23, 42, 0.38);
  --text-inverse: rgba(255, 255, 255, 0.92);

  --border-subtle: rgba(0, 0, 0, 0.06);
  --border-default: rgba(0, 0, 0, 0.10);
  --border-strong: rgba(0, 0, 0, 0.15);

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
  --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.12);
  --shadow-glow: 0 0 24px rgba(59, 130, 246, 0.10);
  --shadow-glow-success: 0 0 20px rgba(34, 197, 94, 0.08);

  --glass-bg: rgba(255, 255, 255, 0.70);
  --glass-bg-hover: rgba(255, 255, 255, 0.85);
  --glass-border: rgba(0, 0, 0, 0.08);
  --glass-blur: 16px;
}

html.dark {
  color-scheme: dark;
}
html.dark select,
html.dark input,
html.dark textarea {
  color-scheme: dark;
}
/* Explicit option styling for dark mode selects */
html.dark select option {
  background-color: #1a1a24;
  color: rgba(255, 255, 255, 0.92);
}
html:not(.dark) select option {
  background-color: #fff;
  color: rgba(15, 23, 42, 0.92);
}

/* ── Element Plus Theme Overrides ──────────────── */
:root {
  --el-color-primary: var(--color-primary);
  --el-color-primary-light-3: var(--color-primary-hover);
  --el-color-primary-light-5: rgba(59, 130, 246, 0.5);
  --el-color-primary-light-7: rgba(59, 130, 246, 0.25);
  --el-color-primary-light-8: rgba(59, 130, 246, 0.15);
  --el-color-primary-light-9: rgba(59, 130, 246, 0.08);
  --el-color-primary-dark-2: #2563EB;

  --el-color-success: var(--color-success);
  --el-color-warning: var(--color-warning);
  --el-color-danger: var(--color-danger);
  --el-color-info: var(--color-info);

  --el-bg-color: var(--bg-base);
  --el-bg-color-page: var(--bg-deep);
  --el-bg-color-overlay: var(--bg-elevated);
  --el-border-color: var(--border-default);
  --el-border-color-light: var(--border-subtle);
  --el-border-color-lighter: var(--border-subtle);

  --el-text-color-primary: var(--text-primary);
  --el-text-color-regular: var(--text-secondary);
  --el-text-color-secondary: var(--text-muted);
  --el-text-color-placeholder: var(--text-muted);

  --el-fill-color: var(--bg-surface);
  --el-fill-color-light: var(--bg-surface);
  --el-fill-color-lighter: var(--bg-surface-hover);
  --el-fill-color-blank: var(--bg-base);

  --el-border-radius-base: var(--radius-sm);
  --el-border-radius-small: calc(var(--radius-sm) - 2px);
  --el-border-radius-round: var(--radius-full);

  --el-font-family: var(--font-body);

  --el-box-shadow-light: var(--shadow-sm);
  --el-box-shadow: var(--shadow-md);
  --el-box-shadow-dark: var(--shadow-lg);
}

/* Ensure Element Plus dark mode uses our tokens */
html.dark {
  --el-bg-color: var(--bg-base);
  --el-bg-color-page: var(--bg-deep);
  --el-bg-color-overlay: var(--bg-elevated);
  --el-fill-color: var(--bg-surface);
  --el-fill-color-light: var(--bg-surface);
  --el-fill-color-lighter: var(--bg-surface-hover);
}

/* ── Shared Utility Classes ───────────────────── */
/* Glass card */
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  transition: background var(--transition-base), border-color var(--transition-base),
              box-shadow var(--transition-base), transform var(--transition-base);
}

.glass-card-interactive {
  cursor: pointer;
}

.glass-card-interactive:hover {
  background: var(--glass-bg-hover);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.glass-card-interactive:active {
  transform: translateY(0) scale(0.985);
}

/* Glass panel (for drawers, side panels) */
.glass-panel {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid var(--glass-border);
}

/* Section header */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-md);
}

.section-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0 0 var(--space-md);
}

/* Page wrapper — consistent max-width & padding */
.page-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-lg) var(--space-xl);
}

/* Gradient text */
.gradient-text {
  background: linear-gradient(135deg, var(--color-primary), #818CF8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Status dot */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot--running {
  background: var(--color-success);
  box-shadow: 0 0 6px var(--color-success);
  animation: pulse-dot 2s ease-in-out infinite;
}
.status-dot--paused {
  background: var(--color-warning);
  box-shadow: 0 0 6px var(--color-warning);
}
.status-dot--stopped {
  background: var(--text-muted);
}

/* Skeleton loading */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, var(--bg-surface) 25%, var(--bg-surface-hover) 50%, var(--bg-surface) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

/* Page fade transition */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Slide panel transition (used by drawers) */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform var(--transition-slow);
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateX(100%);
}

/* Card stagger entrance */
@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(12px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
.stagger-item {
  animation: card-in 0.4s ease both;
}

/* Shake animation for form errors */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-4px); }
  40%, 80% { transform: translateX(4px); }
}
.shake {
  animation: shake 0.4s ease;
}

/* Pulse animation */
@keyframes pulse-dot {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px currentColor; }
  50% { opacity: 0.5; box-shadow: 0 0 12px currentColor; }
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-full);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}

/* Focus visible ring */
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: 2px;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
