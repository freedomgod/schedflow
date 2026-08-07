<template>
  <div class="task-selector">
    <div class="selector-header">
      <el-input
        v-model="search"
        placeholder="搜索任务"
        clearable
        size="default"
        :prefix-icon="Search"
      />
    </div>
    <div class="selector-list" v-loading="loading">
      <div
        v-for="job in filteredJobs"
        :key="job.id"
        class="task-item"
        :class="{ 'is-active': job.id === activeJobId }"
        @click="$emit('select', job.id, job.name)"
      >
        <span
          class="status-dot"
          :class="job.job_status === 'RUNNING' ? 'running' : 'paused'"
        ></span>
        <span class="task-name">{{ job.name }}</span>
      </div>
      <el-empty v-if="!loading && filteredJobs.length === 0" description="无匹配任务" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getJobs } from '@/api/jobs'
import type { Job } from '@/types'

defineProps<{
  activeJobId: string | null
}>()

const emit = defineEmits<{
  select: [jobId: string, jobName: string]
}>()

const jobs = ref<Job[]>([])
const loading = ref(false)
const search = ref('')

const filteredJobs = computed(() => {
  if (!search.value) return jobs.value
  const kw = search.value.toLowerCase()
  return jobs.value.filter((j) => j.name?.toLowerCase().includes(kw))
})

async function fetchJobs() {
  loading.value = true
  try {
    jobs.value = await getJobs()
  } finally {
    loading.value = false
  }
}

onMounted(fetchJobs)

defineExpose({ refresh: fetchJobs })
</script>

<style scoped>
.task-selector {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-lighter, #fafafa);
}

.selector-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
}

.selector-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 2px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}

.task-item:hover {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.task-item.is-active {
  background: var(--el-color-primary-light-7, #d9ecff);
  color: var(--el-color-primary, #409eff);
  font-weight: 500;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.running {
  background: var(--el-color-success, #67c23a);
}

.status-dot.paused {
  background: var(--el-text-color-placeholder, #c0c4cc);
}

.task-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
