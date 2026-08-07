<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- Logo -->
    <router-link to="/dashboard" class="sidebar-logo">
      <div class="logo-icon">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect width="28" height="28" rx="8" fill="url(#logo-grad)"/>
          <path d="M8 10h4v8H8zM16 7h4v11h-4zM12 14h4v4h-4z" fill="white" opacity="0.9"/>
          <defs>
            <linearGradient id="logo-grad" x1="0" y1="0" x2="28" y2="28">
              <stop stop-color="#3B82F6"/>
              <stop offset="1" stop-color="#6366F1"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
      <span v-show="!isCollapsed" class="logo-text">SchedFlow</span>
    </router-link>

    <!-- Navigation -->
    <nav class="sidebar-nav">
      <router-link to="/dashboard" class="nav-item" :class="{ active: isActive('/dashboard') }" title="仪表盘">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="2" width="7" height="4" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="8" width="7" height="10" rx="1.5" stroke="currentColor" stroke-width="1.5"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">仪表盘</span>
        <span v-if="isActive('/dashboard') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
      <router-link to="/jobs" class="nav-item" :class="{ active: isActive('/jobs') }" title="工作流管理">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="2" y1="7" x2="18" y2="7" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="2" x2="7" y2="7" stroke="currentColor" stroke-width="1.5"/><line x1="13" y1="2" x2="13" y2="7" stroke="currentColor" stroke-width="1.5"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">工作流管理</span>
        <span v-if="isActive('/jobs') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
      <router-link to="/logs" class="nav-item" :class="{ active: isActive('/logs') }" title="任务日志">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="6" x2="13" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="7" y1="9" x2="13" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="7" y1="12" x2="10" y2="12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">任务日志</span>
        <span v-if="isActive('/logs') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
      <router-link to="/executor-config" class="nav-item" :class="{ active: isActive('/executor-config') }" title="执行器配置">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">执行器配置</span>
        <span v-if="isActive('/executor-config') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
      <router-link to="/storage-config" class="nav-item" :class="{ active: isActive('/storage-config') }" title="存储配置">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><ellipse cx="10" cy="5" rx="8" ry="3" stroke="currentColor" stroke-width="1.5"/><path d="M2 5v4c0 1.66 3.58 3 8 3s8-1.34 8-3V5" stroke="currentColor" stroke-width="1.5"/><path d="M2 9v4c0 1.66 3.58 3 8 3s8-1.34 8-3V9" stroke="currentColor" stroke-width="1.5"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">存储配置</span>
        <span v-if="isActive('/storage-config') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
      <router-link to="/settings" class="nav-item" :class="{ active: isActive('/settings') }" title="系统设置">
        <span class="nav-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M8.61 2.54a1.46 1.46 0 012.78 0l.23.88a6.18 6.18 0 011.48.65l.82-.37a1.46 1.46 0 012.08 1.84l-.48.77a6.18 6.18 0 01.57 1.5l.87.15a1.46 1.46 0 010 2.78l-.87.15a6.18 6.18 0 01-.57 1.5l.48.77a1.46 1.46 0 01-2.08 1.84l-.82-.37a6.18 6.18 0 01-1.48.65l-.23.88a1.46 1.46 0 01-2.78 0l-.23-.88a6.18 6.18 0 01-1.48-.65l-.82.37A1.46 1.46 0 014 13.83l.48-.77a6.18 6.18 0 01-.57-1.5l-.87-.15a1.46 1.46 0 010-2.78l.87-.15a6.18 6.18 0 01.57-1.5l-.48-.77a1.46 1.46 0 012.08-1.84l.82.37a6.18 6.18 0 011.48-.65l.23-.88z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="10" cy="10" r="3.5" stroke="currentColor" stroke-width="1.5"/></svg>
        </span>
        <span v-show="!isCollapsed" class="nav-label">系统设置</span>
        <span v-if="isActive('/settings') && !isCollapsed" class="nav-indicator"></span>
      </router-link>
    </nav>

    <!-- Bottom section -->
    <div class="sidebar-footer">
      <!-- Collapse toggle -->
      <button class="collapse-btn" @click="isCollapsed = !isCollapsed" :title="isCollapsed ? '展开侧栏' : '收起侧栏'">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" :class="{ rotated: isCollapsed }">
          <path d="M7 4L11.5 9L7 14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isCollapsed = ref(false)

function isActive(path: string) {
  const r = route.path
  if (path === '/logs') return r.startsWith('/logs')
  if (path === '/jobs') return r.startsWith('/jobs')
  if (path === '/settings') return r.startsWith('/settings')
  if (path === '/executor-config') return r.startsWith('/executor-config')
  if (path === '/storage-config') return r.startsWith('/storage-config')
  return r === path
}
</script>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-right: 1px solid var(--glass-border);
  transition: width var(--transition-slow), background var(--transition-base);
  user-select: none;
  position: relative;
  z-index: 200;
}

.app-sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

/* ── Logo ────────── */
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  height: var(--topbar-height);
  padding: 0 18px;
  text-decoration: none;
  border-bottom: 1px solid var(--glass-border);
  overflow: hidden;
  flex-shrink: 0;
  transition: padding var(--transition-slow);
}

.collapsed .sidebar-logo {
  padding: 0 14px;
  justify-content: center;
}

.logo-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.logo-text {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 700;
  background: linear-gradient(135deg, #60A5FA, #818CF8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
}

/* ── Navigation ──── */
.sidebar-nav {
  flex: 1;
  padding: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  position: relative;
  transition: color var(--transition-fast), background var(--transition-fast);
  white-space: nowrap;
  overflow: hidden;
}

.collapsed .nav-item {
  justify-content: center;
  padding: 0;
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-surface-hover);
}

.nav-item.active {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.nav-indicator {
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--color-primary);
}

.nav-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  opacity: 0.75;
  transition: opacity var(--transition-fast);
}

.nav-item:hover .nav-icon,
.nav-item.active .nav-icon {
  opacity: 1;
}

.nav-label {
  font-size: 13.5px;
}

/* ── Footer ──────── */
.sidebar-footer {
  padding: var(--space-sm) var(--space-md);
  border-top: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  min-height: 48px;
}
.collapsed .sidebar-footer {
  justify-content: center;
  padding: var(--space-sm) 0;
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.collapse-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-secondary);
}

.collapse-btn svg {
  transition: transform var(--transition-slow);
}

.collapse-btn svg.rotated {
  transform: rotate(180deg);
}
</style>
