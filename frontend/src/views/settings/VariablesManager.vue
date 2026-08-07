<template>
  <div class="variables-manager">
    <div class="section-header">
      <span class="section-title">自定义变量</span>
      <el-button type="primary" size="small" @click="showDialog()">新建变量</el-button>
    </div>
    <p class="section-desc">用于任务参数传递，创建后在任务编辑时可通过下拉选择引用。</p>

    <el-table :data="settingsStore.variables" style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="变量名" width="200" />
      <el-table-column prop="value" label="值" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDialog(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑变量' : '新建变量'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="变量名" prop="name">
          <el-input v-model="form.name" placeholder="如 DEFAULT_TIMEOUT" />
        </el-form-item>
        <el-form-item label="值" prop="value">
          <el-input v-model="form.value" placeholder="如 30" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import type { VariableItem } from '@/api/settings'

const settingsStore = useSettingsStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const editing = ref<VariableItem | null>(null)

const form = reactive({ name: '', value: '', description: '' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入变量名', trigger: 'blur' }],
  value: [{ required: true, message: '请输入值', trigger: 'blur' }],
}

function showDialog(item?: VariableItem) {
  editing.value = item || null
  form.name = item?.name || ''
  form.value = item?.value || ''
  form.description = item?.description || ''
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editing.value) {
      await settingsStore.updateVariable(editing.value.id, {
        name: form.name, value: form.value, description: form.description || undefined,
      })
      ElMessage.success('变量已更新')
    } else {
      await settingsStore.createVariable({
        name: form.name, value: form.value, description: form.description || undefined,
      })
      ElMessage.success('变量已创建')
    }
    dialogVisible.value = false
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此变量？', '确认', { type: 'warning' })
  } catch {
    return
  }
  await settingsStore.deleteVariable(id)
  ElMessage.success('变量已删除')
}

onMounted(() => {
  loading.value = true
  settingsStore.fetchVariables().finally(() => { loading.value = false })
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
