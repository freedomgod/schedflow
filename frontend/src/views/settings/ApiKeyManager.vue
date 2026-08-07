<template>
  <div class="apikey-manager">
    <div class="section-header">
      <span class="section-title">API Key 管理</span>
      <el-button type="primary" size="small" @click="showCreateDialog">新建 Key</el-button>
    </div>
    <p class="section-desc">用于本地脚本或第三方系统通过 API 调用，在请求头 X-API-Key 中传递。</p>

    <el-table :data="keys" style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="key_prefix" label="Key 标识" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_used_at" label="最后使用" />
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button link type="primary" @click="toggleActive(row)">
            {{ row.is_active ? '禁用' : '启用' }}
          </el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="新建 API Key" width="500px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="如 自动化脚本" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showKeyVisible" title="API Key 已创建" width="500px">
      <p style="color: var(--color-warning); margin-bottom: 12px;">
        请复制以下 Key，此 Key 仅显示一次，关闭后将无法再次查看。
      </p>
      <el-input v-model="newPlainKey" readonly style="margin-bottom: 12px" />
      <el-button type="primary" @click="copyAndClose">复制并关闭</el-button>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getApiKeys, createApiKey, updateApiKey, deleteApiKey,
} from '@/api/auth'
import type { ApiKeyItem } from '@/api/auth'

const keys = ref<ApiKeyItem[]>([])
const loading = ref(false)
const creating = ref(false)
const createVisible = ref(false)
const showKeyVisible = ref(false)
const newPlainKey = ref('')
const createFormRef = ref<FormInstance>()

const createForm = reactive({ name: '' })
const createRules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

async function fetchKeys() {
  loading.value = true
  try {
    keys.value = await getApiKeys()
  } finally {
    loading.value = false
  }
}

function showCreateDialog() {
  createForm.name = ''
  createVisible.value = true
}

async function handleCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  creating.value = true
  try {
    const result = await createApiKey(createForm.name)
    newPlainKey.value = result.plain_key
    createVisible.value = false
    showKeyVisible.value = true
    await fetchKeys()
  } finally {
    creating.value = false
  }
}

async function copyAndClose() {
  await navigator.clipboard.writeText(newPlainKey.value)
  ElMessage.success('已复制到剪贴板')
  showKeyVisible.value = false
}

async function toggleActive(row: ApiKeyItem) {
  await updateApiKey(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '已禁用' : '已启用')
  await fetchKeys()
}

async function handleDelete(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此 API Key？相关调用将立即失效。', '确认', { type: 'warning' })
  } catch {
    return
  }
  await deleteApiKey(id)
  ElMessage.success('已删除')
  await fetchKeys()
}

onMounted(() => {
  fetchKeys()
})
</script>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
}
.section-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0 0 16px;
}
</style>
