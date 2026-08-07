<template>
  <div class="node-config">
    <div class="panel-header">
      <span class="panel-title">节点配置</span>
      <el-button :icon="Close" text size="small" @click="emit('update:visible', false)" />
    </div>
    <div class="panel-body">
      <el-form label-position="top" :model="form">
        <el-form-item label="节点名称">
          <el-input v-model="form.name" placeholder="请输入节点名称" />
        </el-form-item>

        <el-form-item label="节点描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="请输入节点描述"
          />
        </el-form-item>

        <el-form-item label="任务类型">
          <el-select v-model="form.type" placeholder="选择任务类型" @change="onTypeChange">
            <el-option label="Python Callable (module:func)" value="python_callable" />
            <el-option label="Python 脚本文件" value="python" />
            <el-option label="Python 代码片段" value="python_script" />
            <el-option label="Bash" value="bash" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="form.type === 'python_callable'" label="函数引用" required>
          <el-input
            v-model="form.func_ref"
            placeholder="例如: mypackage.module:function_name"
          />
        </el-form-item>

        <el-form-item v-if="form.type === 'python'" label="脚本文件路径" required>
          <el-input
            v-model="form.script_path"
            placeholder="例如: /home/user/scripts/my_script.py"
          />
        </el-form-item>

        <el-form-item v-if="form.type === 'python_script'" label="Python 代码片段" required>
          <el-input
            v-model="form.script"
            type="textarea"
            :rows="5"
            placeholder="输入 Python 代码..."
            class="code-input"
          />
        </el-form-item>

        <el-form-item v-if="form.type === 'bash'" label="Bash 命令" required>
          <el-input
            v-model="form.command"
            type="textarea"
            :rows="4"
            placeholder="输入 bash 命令..."
            class="code-input"
          />
        </el-form-item>

        <el-form-item v-if="form.type === 'python_callable'" label="关键字参数 (kwargs)">
          <div class="kwargs-table">
            <div class="kwargs-header">
              <span class="kwargs-col-key">参数名</span>
              <span class="kwargs-col-type">类型</span>
              <span class="kwargs-col-value">值</span>
              <span class="kwargs-col-action">删除</span>
            </div>
            <div
              v-for="(row, index) in form.kwargs"
              :key="index"
              class="kwargs-row"
            >
              <el-input
                v-model="row.key"
                class="kwargs-col-key"
                placeholder="参数名"
              />
              <el-select
                v-model="row.type"
                class="kwargs-col-type"
              >
                <el-option label="string" value="string" />
                <el-option label="number" value="number" />
                <el-option label="boolean" value="boolean" />
              </el-select>
              <el-autocomplete
                v-model="row.value"
                class="kwargs-col-value"
                placeholder="值"
                :fetch-suggestions="(q: string, cb: any) => searchVariables(q, cb)"
                :trigger-on-focus="true"
                value-key="value"
                clearable
              >
                <template #default="{ item }">
                  <div class="var-suggestion">{{ item.label }}</div>
                </template>
              </el-autocomplete>
              <el-button
                :icon="Delete"
                class="kwargs-col-action"
                circle
                size="small"
                type="danger"
                @click="removeKwarg(index)"
              />
            </div>
            <el-button
              type="primary"
              text
              @click="addKwarg"
            >
              添加参数
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="完成回调">
          <el-input
            v-model="form.done_callback_ref"
            placeholder="例如: mypackage.module:callback_function（可选）"
          />
        </el-form-item>

        <el-form-item label="最大重试次数">
          <el-input-number
            v-model="form.stop_max_attempt_number"
            :min="1"
            :max="99"
          />
        </el-form-item>
      </el-form>
    </div>
    <div class="panel-footer">
      <el-button type="danger" plain @click="handleDelete">删除</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch, onMounted } from 'vue'
import { Delete, Close } from '@element-plus/icons-vue'
import type { TaskNodeProperties, KeyValuePair, TaskType } from '@/types/workflow'
import { useSettingsStore } from '@/stores/settings'

const props = defineProps<{
  visible: boolean
  nodeData: TaskNodeProperties | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  save: [data: TaskNodeProperties]
  delete: []
}>()

const settingsStore = useSettingsStore()

onMounted(() => {
  settingsStore.fetchVariables()
})

function searchVariables(query: string, cb: (results: { value: string; label: string }[]) => void) {
  const vars = settingsStore.variables
  if (!query) {
    cb(vars.map(v => ({ value: v.value, label: `${v.name}: ${v.value}` })))
    return
  }
  const q = query.toLowerCase()
  cb(
    vars
      .filter(v => v.name.toLowerCase().includes(q) || v.value.toLowerCase().includes(q))
      .map(v => ({ value: v.value, label: `${v.name}: ${v.value}` }))
  )
}

const form = reactive<TaskNodeProperties>({
  name: '',
  description: '',
  func_ref: '',
  type: 'python_callable',
  script_path: '',
  script: '',
  command: '',
  kwargs: [],
  done_callback_ref: '',
  stop_max_attempt_number: undefined,
})

function resetForm() {
  form.name = ''
  form.description = ''
  form.func_ref = ''
  form.type = 'python_callable'
  form.script_path = ''
  form.script = ''
  form.command = ''
  form.kwargs = []
  form.done_callback_ref = ''
  form.stop_max_attempt_number = undefined
}

function onTypeChange(_newType: TaskType) {
  // Clear type-specific fields on type switch
  form.func_ref = ''
  form.script_path = ''
  form.script = ''
  form.command = ''
  form.kwargs = []
}

watch(
  () => props.nodeData,
  (data) => {
    if (data) {
      form.name = data.name
      form.description = data.description ?? ''
      form.type = data.type || 'python_callable'
      form.func_ref = data.func_ref || ''
      form.script_path = data.script_path || ''
      form.script = data.script || ''
      form.command = data.command || ''
      form.kwargs = (data.kwargs || []).map((k) => ({ ...k }))
      form.done_callback_ref = data.done_callback_ref ?? ''
      form.stop_max_attempt_number = data.stop_max_attempt_number
    } else {
      resetForm()
    }
  },
  { immediate: true },
)

function addKwarg() {
  form.kwargs.push({ key: '', value: '', type: 'string' })
}

function removeKwarg(index: number) {
  form.kwargs.splice(index, 1)
}

function handleSave() {
  const data: TaskNodeProperties = {
    name: form.name,
    description: form.description,
    type: form.type,
    func_ref: form.func_ref,
    script_path: form.script_path,
    script: form.script,
    command: form.command,
    kwargs: form.kwargs.filter((k) => k.key.trim() !== ''),
    done_callback_ref: form.done_callback_ref,
    stop_max_attempt_number: form.stop_max_attempt_number,
  }
  emit('save', data)
  emit('update:visible', false)
}

function handleDelete() {
  emit('delete')
  emit('update:visible', false)
}
</script>

<style scoped>
.node-config {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 0;
  flex-shrink: 0;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.panel-footer {
  display: flex;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.code-input :deep(textarea) {
  font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
  font-size: 13px;
  background: #1e1e1e;
  color: #4ec9b0;
}

.kwargs-table {
  width: 100%;
}

.kwargs-header {
  display: grid;
  grid-template-columns: 2fr 1fr 2fr 36px;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.kwargs-row {
  display: grid;
  grid-template-columns: 2fr 1fr 2fr 36px;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.kwargs-col-key {
  /* grid column auto */
}

.kwargs-col-type {
  /* grid column auto */
}

.kwargs-col-value {
  /* grid column auto */
}

.kwargs-col-action {
  /* grid column auto */
}

.var-suggestion {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
</style>
