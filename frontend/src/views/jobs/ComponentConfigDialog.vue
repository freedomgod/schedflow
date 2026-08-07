<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-table v-if="fields.length > 0" :data="fields" size="small" border>
      <el-table-column prop="label" label="参数" width="180" />
      <el-table-column prop="value" label="值">
        <template #default="{ row }">
          <el-tag v-if="row.value === null" size="small" type="info">null</el-tag>
          <template v-else-if="typeof row.value === 'boolean'">
            <el-tag :type="row.value ? 'success' : 'danger'" size="small">{{ row.value ? 'true' : 'false' }}</el-tag>
          </template>
          <template v-else-if="typeof row.value === 'object'">
            <code style="font-size: 12px; word-break: break-all">{{ JSON.stringify(row.value) }}</code>
          </template>
          <span v-else>{{ row.value }}</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="该组件没有可配置的参数" />
  </el-dialog>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  title: string
  fields: Array<{ label: string; value: unknown }>
}>()

defineEmits<{
  'update:visible': [value: boolean]
}>()
</script>
