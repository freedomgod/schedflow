<template>
  <div class="trigger-config">
    <el-form-item label="触发器类型">
      <el-select
        :model-value="triggerType"
        placeholder="选择触发器类型"
        style="width: 100%"
        @update:model-value="$emit('update:triggerType', $event)"
      >
        <el-option label="Cron" value="cron" />
        <el-option label="Date" value="date" />
        <el-option label="Interval" value="interval" />
        <el-option label="Calendar Interval (JSON)" value="calendarinterval" />
        <el-option label="And (JSON)" value="and" />
        <el-option label="Or (JSON)" value="or" />
      </el-select>
    </el-form-item>

    <!-- Cron fields -->
    <template v-if="triggerType === 'cron'">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="年">
            <el-input v-model="localArgs.year" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="月">
            <el-input v-model="localArgs.month" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="日">
            <el-input v-model="localArgs.day" placeholder="*" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="周">
            <el-input v-model="localArgs.week" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="星期几">
            <el-input v-model="localArgs.day_of_week" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="时">
            <el-input v-model="localArgs.hour" placeholder="*" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="分">
            <el-input v-model="localArgs.minute" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="秒">
            <el-input v-model="localArgs.second" placeholder="*" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="抖动 (秒)">
            <el-input-number v-model="localArgs.jitter" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="开始时间">
            <el-date-picker
              v-model="localArgs.start_date"
              type="datetime"
              placeholder="选择开始时间"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="结束时间">
            <el-date-picker
              v-model="localArgs.end_date"
              type="datetime"
              placeholder="选择结束时间"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </template>

    <!-- Date field -->
    <template v-if="triggerType === 'date'">
      <el-form-item label="运行时间" required>
        <el-date-picker
          v-model="localArgs.run_date"
          type="datetime"
          placeholder="选择运行时间"
          style="width: 100%"
        />
      </el-form-item>
    </template>

    <!-- Interval fields -->
    <template v-if="triggerType === 'interval'">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="周">
            <el-input-number v-model="localArgs.weeks" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="天">
            <el-input-number v-model="localArgs.days" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="时">
            <el-input-number v-model="localArgs.hours" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="分">
            <el-input-number v-model="localArgs.minutes" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="秒">
            <el-input-number v-model="localArgs.seconds" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="抖动 (秒)">
            <el-input-number v-model="localArgs.jitter" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="开始时间">
            <el-date-picker
              v-model="localArgs.start_date"
              type="datetime"
              placeholder="选择开始时间"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="结束时间">
            <el-date-picker
              v-model="localArgs.end_date"
              type="datetime"
              placeholder="选择结束时间"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </template>

    <!-- JSON fallback for calendarinterval / and / or -->
    <template v-if="isJsonFallback">
      <el-form-item label="触发器参数">
        <el-input
          v-model="jsonText"
          type="textarea"
          :rows="4"
          placeholder='{"key": "value"}'
        />
      </el-form-item>
    </template>

    <span v-if="triggerType === 'cron'" class="form-tip">支持 Cron/Crontab 表达式，* 表示所有值。格式: 秒 分 时 日 月 星期几</span>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'

interface TriggerArgs {
  // Cron fields
  year: string
  month: string
  day: string
  week: string
  day_of_week: string
  hour: string
  minute: string
  second: string
  start_date: Date | null
  end_date: Date | null
  jitter: number | undefined
  // Date field
  run_date: Date | null
  // Interval fields
  weeks: number | undefined
  days: number | undefined
  hours: number | undefined
  minutes: number | undefined
  seconds: number | undefined
}

const props = defineProps<{
  triggerType: string
}>()

const emit = defineEmits<{
  'update:triggerType': [value: string]
  'update:triggerArgs': [args: Record<string, unknown>]
}>()

function defaultArgs(): TriggerArgs {
  return {
    year: '',
    month: '',
    day: '',
    week: '',
    day_of_week: '',
    hour: '',
    minute: '',
    second: '',
    start_date: null,
    end_date: null,
    jitter: undefined,
    run_date: null,
    weeks: undefined,
    days: undefined,
    hours: undefined,
    minutes: undefined,
    seconds: undefined,
  }
}

const localArgs = reactive<TriggerArgs>(defaultArgs())
const jsonText = ref('')

const JSON_FALLBACK_TYPES = ['calendarinterval', 'and', 'or']

const isJsonFallback = computed(() => JSON_FALLBACK_TYPES.includes(props.triggerType))

function dateToISO(val: Date | null): string | undefined {
  if (val instanceof Date) return val.toISOString()
  return undefined
}

function isNotEmpty(val: unknown): boolean {
  return val !== '' && val !== undefined && val !== null
}

function buildArgs(): Record<string, unknown> {
  if (isJsonFallback.value) {
    if (jsonText.value.trim()) {
      try {
        return JSON.parse(jsonText.value)
      } catch {
        return {}
      }
    }
    return {}
  }

  const result: Record<string, unknown> = {}

  if (props.triggerType === 'cron') {
    const cronFields = [
      'year', 'month', 'day', 'week', 'day_of_week',
      'hour', 'minute', 'second',
    ] as const
    for (const f of cronFields) {
      if (isNotEmpty(localArgs[f])) {
        result[f] = localArgs[f]
      }
    }
    const sd = dateToISO(localArgs.start_date)
    if (sd) result.start_date = sd
    const ed = dateToISO(localArgs.end_date)
    if (ed) result.end_date = ed
    if (localArgs.jitter !== undefined && localArgs.jitter !== null) {
      result.jitter = localArgs.jitter
    }
  } else if (props.triggerType === 'date') {
    const rd = dateToISO(localArgs.run_date)
    if (rd) result.run_date = rd
  } else if (props.triggerType === 'interval') {
    const intervalFields = ['weeks', 'days', 'hours', 'minutes', 'seconds'] as const
    for (const f of intervalFields) {
      if (localArgs[f] !== undefined && localArgs[f] !== null) {
        result[f] = localArgs[f]
      }
    }
    const sd = dateToISO(localArgs.start_date)
    if (sd) result.start_date = sd
    const ed = dateToISO(localArgs.end_date)
    if (ed) result.end_date = ed
    if (localArgs.jitter !== undefined && localArgs.jitter !== null) {
      result.jitter = localArgs.jitter
    }
  }

  return result
}

function resetFields() {
  Object.assign(localArgs, defaultArgs())
  jsonText.value = ''
}

watch(() => props.triggerType, () => {
  resetFields()
})

watch(jsonText, (val) => {
  if (isJsonFallback.value) {
    try {
      const parsed = JSON.parse(val)
      emit('update:triggerArgs', parsed)
    } catch {
      // JSON parse error — do not emit
    }
  }
})

function setTriggerArgs(args: Record<string, unknown>) {
  Object.assign(localArgs, defaultArgs())
  jsonText.value = ''

  if (isJsonFallback.value) {
    jsonText.value = JSON.stringify(args, null, 2)
    return
  }

  if (props.triggerType === 'cron') {
    const strKeys = ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second']
    for (const k of strKeys) {
      if (args[k] != null) (localArgs as any)[k] = String(args[k])
    }
    if (args.start_date) localArgs.start_date = new Date(args.start_date as string)
    if (args.end_date) localArgs.end_date = new Date(args.end_date as string)
    if (args.jitter != null) localArgs.jitter = Number(args.jitter)
  } else if (props.triggerType === 'date') {
    if (args.run_date) localArgs.run_date = new Date(args.run_date as string)
  } else if (props.triggerType === 'interval') {
    const numKeys = ['weeks', 'days', 'hours', 'minutes', 'seconds']
    for (const k of numKeys) {
      if (args[k] != null) (localArgs as any)[k] = Number(args[k])
    }
    if (args.start_date) localArgs.start_date = new Date(args.start_date as string)
    if (args.end_date) localArgs.end_date = new Date(args.end_date as string)
    if (args.jitter != null) localArgs.jitter = Number(args.jitter)
  }
}

defineExpose({
  getTriggerArgs: buildArgs,
  setTriggerArgs,
})
</script>

<style scoped>
.form-tip {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}

.trigger-config .el-form-item {
  margin-bottom: 18px;
}
</style>
