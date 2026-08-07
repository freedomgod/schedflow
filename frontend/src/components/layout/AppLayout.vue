<template>
  <div class="app-layout">
    <AppSidebar />
    <div class="main-area">
      <AppTopbar />
      <main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
    <!-- Ambient atmosphere blob -->
    <div class="ambient-blob"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AppSidebar from './AppSidebar.vue'
import AppTopbar from './AppTopbar.vue'
import { useSchedulerStore } from '@/stores/scheduler'

const store = useSchedulerStore()

onMounted(() => {
  store.fetchStatus()
})
</script>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  grid-template-rows: 1fr;
  height: 100vh;
  background: var(--bg-deep);
  position: relative;
  transition: grid-template-columns var(--transition-slow);
}

.main-area {
  display: grid;
  grid-template-rows: var(--topbar-height) 1fr;
  min-width: 0;
  min-height: 0;
  position: relative;
  z-index: 1;
}

.main-content {
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  min-height: 0;
}

/* ── Ambient blob ── */
.ambient-blob {
  position: fixed;
  top: -120px;
  right: -120px;
  width: 500px;
  height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.06), transparent 70%);
  pointer-events: none;
  z-index: 0;
  animation: blob-drift 20s ease-in-out infinite;
}

@keyframes blob-drift {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  25% {
    transform: translate(-40px, 30px) scale(1.05);
  }
  50% {
    transform: translate(-20px, -20px) scale(0.95);
  }
  75% {
    transform: translate(30px, -10px) scale(1.02);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ambient-blob {
    animation: none;
  }
}
</style>
