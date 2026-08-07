<template>
  <div class="storage-config">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h2>存储器配置</h2>
        <p class="desc">管理系统任务数据的存储后端，修改存储配置可能需要迁移已有任务数据</p>
      </div>
      <el-button type="primary" @click="openAddDialog">
        <el-icon><Plus /></el-icon> 新增存储器
      </el-button>
    </div>

    <!-- Stats Row -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon store-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><ellipse cx="10" cy="5" rx="8" ry="3" stroke="currentColor" stroke-width="1.5"/><path d="M2 5v4c0 1.66 3.58 3 8 3s8-1.34 8-3V5" stroke="currentColor" stroke-width="1.5"/><path d="M2 9v4c0 1.66 3.58 3 8 3s8-1.34 8-3V9" stroke="currentColor" stroke-width="1.5"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ configured.length }}</div>
            <div class="stat-label">已配置存储器</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon job-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="6" x2="13" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ totalJobCount }}</div>
            <div class="stat-label">存储任务总数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon plugin-icon"><svg width="22" height="22" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/><path d="M10 2v2M10 16v2M3.5 3.5l1.5 1.5M15 15l1.5 1.5M2 10h2M16 10h2M3.5 16.5l1.5-1.5M15 5l1.5-1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
          <div class="stat-body">
            <div class="stat-value">{{ plugins.length }}</div>
            <div class="stat-label">可用存储类型</div>
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
            <el-tag size="small" type="success" effect="light">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配置参数" min-width="240">
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
        <el-table-column label="任务数" width="100" align="center">
          <template #default="{ row }">
            <el-badge :value="row.jobCount || 0" :type="row.jobCount > 0 ? 'primary' : 'info'" show-zero />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm
              v-if="row.alias !== 'default'"
              title="确定删除此存储器？如有任务数据将丢失"
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
      :title="isEditing ? '编辑存储器' : '新增存储器'"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="别名" required>
          <el-input v-model="form.alias" :disabled="isEditing" placeholder="存储器别名" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type" placeholder="选择存储类型" style="width: 100%" @change="onTypeChange">
            <el-option v-for="p in plugins" :key="p.name" :label="p.name" :value="p.name" />
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
          {{ isEditing ? '保存配置' : '新增' }}
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
  getJobstorePlugins,
  getConfiguredJobstores,
  configureJobstore,
  removeJobstore,
  updateJobstore,
  migrateJobstore,
  getJobstoreConfig,
  type JobstorePlugin,
  type JobstorePluginParam,
  type ConfiguredJobstore,
} from '@/api/components'

const plugins = ref<JobstorePlugin[]>([])
const configured = ref<(ConfiguredJobstore & { config?: Record<string, unknown>; jobCount?: number })[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingAlias = ref('')

const form = reactive({
  alias: '',
  type: '',
  config: {} as Record<string, unknown>,
})

const currentPluginParams = computed<JobstorePluginParam[]>(() => {
  const plugin = plugins.value.find((p) => p.name === form.type)
  return plugin?.params || []
})

const totalJobCount = computed(() =>
  configured.value.reduce((sum, item) => sum + (item.jobCount || 0), 0)
)

const SENSITIVE_KEYS = ['password', 'passwd', 'pwd', 'secret', 'secret_key', 'token', 'api_key', 'access_key', 'auth', 'authorization']

function formatVal(key: string, val: unknown): string {
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
      getJobstorePlugins(),
      getConfiguredJobstores(),
    ])
    plugins.value = p
    // Load detailed config for each configured jobstore
    const detailed = await Promise.all(
      c.map(async (item) => {
        try {
          const detail = await getJobstoreConfig(item.alias)
          return { ...item, config: detail.config || {}, jobCount: item.job_count || 0 }
        } catch {
          return { ...item, config: {}, jobCount: item.job_count || 0 }
        }
      })
    )
    configured.value = detailed
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
  form.config = { ...row.config } || {}
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
      const result = await updateJobstore(editingAlias.value, form.type, config)

      if (result.needs_migration && result.affected_jobs_count > 0) {
        // Show migration confirmation dialog
        try {
          await ElMessageBox.confirm(
            `存储配置已变更，检测到 ${result.affected_jobs_count} 个任务需要迁移到新存储。\n\n` +
            '⚠ 重要提示：\n' +
            '• 取消迁移或迁移失败后，使用原存储后端的任务将被删除\n' +
            '• 请确认新存储配置正确后再执行迁移\n' +
            '• 迁移操作不可撤销',
            '需要迁移任务数据',
            {
              confirmButtonText: '确认迁移',
              cancelButtonText: '取消迁移（将删除任务）',
              type: 'warning',
              distinguishCancelAndClose: true,
            }
          )

          // User confirmed migration
          try {
            const migrateResult = await migrateJobstore(editingAlias.value)
            ElMessage.success(migrateResult.message || '迁移成功')
          } catch (migErr: any) {
            ElMessage.error(migErr?.response?.data?.detail || '迁移失败')
          }
        } catch (action: any) {
          if (action === 'cancel') {
            ElMessage.warning(
              `已取消迁移，使用原存储后端的 ${result.affected_jobs_count} 个任务已被删除`
            )
          }
          // 'close' means user clicked X — do nothing
        }
      } else {
        ElMessage.success(result.message || '存储器配置已更新')
      }
    } else {
      await configureJobstore(form.alias.trim(), form.type, config)
      ElMessage.success(`存储器 "${form.alias}" 配置成功`)
    }
    dialogVisible.value = false
    await fetchData()
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      const detail = err?.response?.data?.detail || err?.message
      ElMessage.error(detail || '操作失败')
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete(alias: string) {
  try {
    await removeJobstore(alias)
    ElMessage.success(`存储器 "${alias}" 已删除`)
    await fetchData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '删除失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.storage-config { padding: var(--space-lg) var(--space-xl); max-width: 1280px; }

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
.store-icon { background: var(--color-primary-soft); color: var(--color-primary); }
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
