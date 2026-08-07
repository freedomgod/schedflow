<template>
  <div class="edge-config">
    <div class="panel-header">
      <span class="panel-title">边配置</span>
      <el-button :icon="Close" text size="small" @click="emit('update:visible', false)" />
    </div>
    <div class="panel-body">
      <el-form label-position="top" :model="form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="请输入边名称" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入边描述"
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
import { reactive, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import type { EdgeProperties } from '@/types/workflow'

const props = defineProps<{
  visible: boolean
  edgeData: EdgeProperties | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  save: [data: EdgeProperties]
  delete: []
}>()

const form = reactive<EdgeProperties>({
  name: '',
  description: '',
})

function resetForm() {
  form.name = ''
  form.description = ''
}

watch(
  () => props.edgeData,
  (data) => {
    if (data) {
      form.name = data.name ?? ''
      form.description = data.description ?? ''
    } else {
      resetForm()
    }
  },
  { immediate: true },
)

function handleSave() {
  const data: EdgeProperties = {
    name: form.name || undefined,
    description: form.description || undefined,
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
.edge-config {
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
</style>
