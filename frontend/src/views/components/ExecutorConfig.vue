<template>
  <div class="executor-config">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h2>执行器配置</h2>
        <p class="desc">管理系统调度任务的执行器，修改配置将影响所有引用该执行器的任务</p>
      </div>
      <el-button type="primary" @click="openAddDialog">
        <el-icon><Plus /></el-icon> 新增执行器
      </el-button>
    </div>

    <!-- Stats Row -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon exec-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ configured.length }}</div>
            <div class="stat-label">已配置执行器</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon job-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="6" x2="13" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="7" y1="10" x2="13" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ totalRefCount }}</div>
            <div class="stat-label">引用任务总数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon plugin-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/><path d="M10 2v2M10 16v2M3.5 3.5l1.5 1.5M15 15l1.5 1.5M2 10h2M16 10h2M3.5 16.5l1.5-1.5M15 5l1.5-1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ plugins.length }}</div>
            <div class="stat-label">可用插件类型</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- Table -->
    <el-card shadow="never">
      <el-table :data="configured" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="alias" label="别名" min-width="140">
          <template #default="{ row }">
            <span class="alias-cell">
              <span class="alias-text">{{ row.alias }}</span>
              <el-tag v-if="row.alias === 'default'" size="small" type="info" effect="plain">默认</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="140">
          <template #default="{ row }">
            <el-tag size="small" type="primary" effect="light">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配置参数" min-width="200">
          <template #default="{ row }">
            <div class="config-params">
              <el-tag
                v-for="(val, key) in row.config"
                :key="key"
                size="small"
                class="param-tag"
              >{{ key }}: {{ formatVal(key, val) }}</el-tag>
              <span v-if="!row.config || Object.keys(row.config).length === 0" class="no-config">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="引用任务" width="100" align="center">
          <template #default="{ row }">
            <el-badge :value="row.jobCount || 0" :type="row.jobCount > 0 ? 'primary' : 'info'" show-zero />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm
              v-if="row.alias !== 'default'"
              title="确定删除此执行器？"
              confirm-button-text="删除"
              @confirm="handleDelete(row.alias)"
            >
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑执行器' : '新增执行器'"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="别名" required>
          <el-input
            v-model="form.alias"
            placeholder="执行器别名"
            :disabled="isEditing"
          />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select
            v-model="form.type"
            placeholder="选择执行器类型"
            style="width: 100%"
            @change="onTypeChange"
          >
            <el-option
              v-for="p in plugins"
              :key="p.name"
              :label="p.name"
              :value="p.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-for="param in currentPluginParams"
          :key="param.name"
          :label="param.label"
          :required="param.required"
        >
          <el-input
            v-if="param.type === 'string' || param.type === 'number'"
            v-model="form.config[param.name]"
            :placeholder="param.placeholder"
            :type="param.type === 'number' ? 'number' : 'text'"
          />
          <el-input
            v-else-if="param.type === 'json'"
            v-model="form.config[param.name]"
            :placeholder="param.placeholder"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          {{ isEditing ? '保存' : '新增' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getExecutorPlugins,
  getConfiguredExecutors,
  configureExecutor,
  removeExecutor,
  updateExecutor,
  type ExecutorPlugin,
  type ExecutorPluginParam,
  type ConfiguredExecutor,
} from '@/api/components'

const plugins = ref<ExecutorPlugin[]>([])
const configured = ref<(ConfiguredExecutor & { config?: Record<string, unknown>; jobCount?: number })[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingAlias = ref('')
const formRef = ref()

const form = reactive({
  alias: '',
  type: '',
  config: {} as Record<string, unknown>,
})

const currentPluginParams = computed<ExecutorPluginParam[]>(() => {
  const plugin = plugins.value.find((p) => p.name === form.type)
  return plugin?.params || []
})

const totalRefCount = computed(() =>
  configured.value.reduce((sum, item) => sum + (item.jobCount || 0), 0)
)

const SENSITIVE_KEYS = ['password', 'passwd', 'pwd', 'secret', 'secret_key', 'token', 'api_key', 'access_key', 'auth', 'authorization']

function formatVal(key: string | number, val: unknown): string {
  const lower = String(key).toLowerCase()
  if (SENSITIVE_KEYS.some((k) => lower === k || lower.endsWith(`_${k}`))) {
    return '******'
  }
  return String(val)
}

function onTypeChange() {
  form.config = {}
  for (const param of currentPluginParams.value) {
    form.config[param.name] = param.type === 'number' ? undefined : ''
  }
}

async function fetchData() {
  loading.value = true
  try {
    const [p, c] = await Promise.all([
      getExecutorPlugins(),
      getConfiguredExecutors(),
    ])
    plugins.value = p
    configured.value = c.map((item) => ({
      ...item,
      config: item.config || {},
      jobCount: item.job_count || 0,
    }))
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  isEditing.value = false
  editingAlias.value = ''
  form.alias = ''
  form.type = ''
  form.config = {}
  dialogVisible.value = true
}

function openEditDialog(row: any) {
  isEditing.value = true
  editingAlias.value = row.alias
  form.alias = row.alias
  form.type = row.type
  form.config = { ...row.config }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.alias.trim() || !form.type) {
    ElMessage.warning('别名和类型不能为空')
    return
  }

  const config: Record<string, unknown> = {}
  for (const param of currentPluginParams.value) {
    const val = form.config[param.name]
    if (val === '' || val === undefined || val === null) {
      if (param.required) {
        ElMessage.warning(`${param.label} 为必填项`)
        return
      }
      continue
    }
    if (param.type === 'json') {
      try { config[param.name] = JSON.parse(val as string) }
      catch { ElMessage.warning(`${param.label} 不是有效的 JSON`); return }
    } else if (param.type === 'number') {
      config[param.name] = Number(val)
    } else {
      config[param.name] = val
    }
  }

  saving.value = true
  try {
    if (isEditing.value) {
      const result = await updateExecutor(editingAlias.value, form.type, config)
      if (result.type_changed) {
        try {
          await ElMessageBox.confirm(
            `执行器类型从原有类型变更为 "${form.type}"，此操作可能导致正在运行的关联任务中断。确定继续？`,
            '确认修改执行器类型',
            { confirmButtonText: '确认修改', cancelButtonText: '取消', type: 'warning' }
          )
        } catch {
          // User cancelled — already saved, just show warning
          ElMessage.warning('执行器类型已修改，请注意可能的任务中断')
        }
      }
      ElMessage.success(result.message || '执行器配置已更新')
    } else {
      await configureExecutor(form.alias.trim(), form.type, config)
      ElMessage.success(`执行器 "${form.alias}" 配置成功`)
    }
    dialogVisible.value = false
    await fetchData()
  } catch (err: any) {
    if (err !== 'cancel') {
      const detail = err?.response?.data?.detail || err?.message
      ElMessage.error(detail || '操作失败')
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete(alias: string) {
  try {
    await removeExecutor(alias)
    ElMessage.success(`执行器 "${alias}" 已删除`)
    await fetchData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '删除失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.executor-config { padding: var(--space-lg) var(--space-xl); max-width: 1280px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-lg);
}
.page-header h2 { margin: 0; font-family: var(--font-heading); font-size: 20px; font-weight: 700; color: var(--text-primary); }
.page-header .desc { margin: 4px 0 0; color: var(--text-muted); font-size: 13px; }

.stats-row { margin-bottom: var(--space-lg); }
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  transition: all var(--transition-fast);
}
.stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.stat-icon {
  width: 44px; height: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.exec-icon { background: var(--color-primary-soft); color: var(--color-primary); }
.job-icon { background: var(--color-success-soft); color: var(--color-success); }
.plugin-icon { background: var(--color-info-soft); color: var(--color-info); }
.stat-value { font-family: var(--font-heading); font-size: 22px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
.stat-label { font-size: 12px; color: var(--text-muted); }

.alias-text { font-weight: 600; }
.alias-cell { display: inline-flex; align-items: center; gap: 6px; }
.config-params { display: flex; flex-wrap: wrap; gap: 4px; }
.param-tag { margin: 0; }
.no-config { color: var(--text-muted); }
</style>
