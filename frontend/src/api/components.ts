import client from './client'
import type { Job, RescheduleParams } from '@/types'

interface ComponentItem {
  name: string
}

export interface JobstorePluginParam {
  name: string
  type: 'string' | 'number' | 'json'
  required: boolean
  label: string
  placeholder: string
}

export interface JobstorePlugin {
  name: string
  params: JobstorePluginParam[]
}

export interface ConfiguredJobstore {
  alias: string
  type: string
  job_count: number
}

export interface ExecutorPluginParam {
  name: string
  type: 'string' | 'number' | 'json'
  required: boolean
  label: string
  placeholder: string
}

export interface ExecutorPlugin {
  name: string
  params: ExecutorPluginParam[]
}

export interface ConfiguredExecutor {
  alias: string
  type: string
  config: Record<string, unknown> | null
  job_count: number
}

export interface ExecutorUpdateResponse {
  alias: string
  plugin_type: string
  config: Record<string, unknown>
  type_changed: boolean
  message: string
}

export interface JobstoreUpdateResponse {
  alias: string
  plugin_type: string
  config: Record<string, unknown>
  needs_migration: boolean
  affected_jobs_count: number
  old_plugin_type: string
  message: string
}

export interface JobstoreMigrateResponse {
  alias: string
  migrated_count: number
  message: string
  error?: string
}

export function getTriggers(): Promise<ComponentItem[]> {
  return client.get('/components/triggers')
}

export function getExecutors(): Promise<ComponentItem[]> {
  return client.get('/components/executors')
}

export function getJobstores(): Promise<ComponentItem[]> {
  return client.get('/components/jobstores')
}

export function rescheduleJob(jobId: string, params: RescheduleParams): Promise<Job> {
  return client.post(`/components/jobs/${jobId}/reschedule`, params)
}

export function getJobstorePlugins(): Promise<JobstorePlugin[]> {
  return client.get('/components/jobstores/plugins')
}

export function getConfiguredJobstores(): Promise<ConfiguredJobstore[]> {
  return client.get('/components/jobstores/configured')
}

export function configureJobstore(alias: string, type: string, config: Record<string, unknown>): Promise<void> {
  return client.post(`/components/jobstores/configure/${alias}`, { type, config })
}

export function removeJobstore(alias: string): Promise<void> {
  return client.delete(`/components/jobstores/configure/${alias}`)
}

export async function updateExecutor(
  alias: string,
  type: string,
  config: Record<string, unknown>
): Promise<ExecutorUpdateResponse> {
  return client.put(`/components/executors/configure/${alias}`, { type, config }) as Promise<ExecutorUpdateResponse>
}

export async function updateJobstore(
  alias: string,
  type: string,
  config: Record<string, unknown>
): Promise<JobstoreUpdateResponse> {
  return client.put(`/components/jobstores/configure/${alias}`, { type, config }) as Promise<JobstoreUpdateResponse>
}

export async function migrateJobstore(alias: string): Promise<JobstoreMigrateResponse> {
  return client.post(`/components/jobstores/configure/${alias}/migrate`) as Promise<JobstoreMigrateResponse>
}

export interface ComponentConfig {
  name: string
  type: string
  config: Record<string, unknown> | null
}

export interface JobstoreDetailConfig {
  alias: string
  type: string
  config: Record<string, unknown>
}

export function getExecutorConfigs(): Promise<ComponentConfig[]> {
  return client.get('/components/executors/configured')
}

export function getJobstoreConfig(alias: string): Promise<JobstoreDetailConfig> {
  return client.get(`/components/jobstores/configured/${alias}`)
}

export function getExecutorPlugins(): Promise<ExecutorPlugin[]> {
  return client.get('/components/executors/plugins')
}

export async function getConfiguredExecutors(): Promise<ConfiguredExecutor[]> {
  return client.get('/components/executors/configured') as Promise<ConfiguredExecutor[]>
}

export function configureExecutor(alias: string, type: string, config: Record<string, unknown>): Promise<void> {
  return client.post(`/components/executors/configure/${alias}`, { type, config })
}

export function removeExecutor(alias: string): Promise<void> {
  return client.delete(`/components/executors/configure/${alias}`)
}
