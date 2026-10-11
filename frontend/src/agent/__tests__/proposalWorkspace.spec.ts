import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import type { AgentConfig } from '../types'
vi.mock('../api', () => ({ agentApi: {}, streamTurn: vi.fn() }))
vi.mock('../../views/jobs/WorkflowEditor.vue', () => ({ default: { render: () => null } }))
vi.mock('../../views/agent/OperationCard.vue', () => ({ default: { render: () => null } }))
import ProposalWorkspace from '../../views/agent/ProposalWorkspace.vue'
import { useAgentStore } from '../../stores/agent'

async function render(config: AgentConfig, pending = false) {
  const pinia = createPinia(); const store = useAgentStore(pinia)
  store.config = config; store.configPending = pending
  store.proposals.p = { proposal_id: 'p', version: 1, status: 'awaiting_confirmation', action: 'run', before: null, after: null, payload: {}, diff: [] }
  const app = createSSRApp({ render: () => h(ProposalWorkspace, { proposalId: 'p' }) }); app.use(pinia)
  app.component('el-switch', { render: () => null })
  return renderToString(app)
}
describe('Proposal confirmation availability', () => {
  it.each([
    [{ enabled: false, configured: true, model: 'test' }, false, 'Agent 已停用'],
    [{ enabled: true, configured: false, model: 'test' }, false, '模型服务尚未配置'],
    [{ enabled: true, configured: true, model: 'test' }, true, '正在更新 Agent 启用状态'],
  ] as const)('disables confirmation and explains config state %o', async (config, pending, hint) => {
    const html = await render(config, pending)
    const button = html.match(/<button[^>]*class="btn-primary"[^>]*>/)?.[0]
    expect(button).toContain('disabled')
    expect(html).toContain(hint)
    expect(html).not.toContain('候选已过期')
  })
  it('keeps confirmation available for an enabled configured Agent', async () => {
    const html = await render({ enabled: true, configured: true, model: 'test' })
    expect(html.match(/<button[^>]*class="btn-primary"[^>]*>/)?.[0]).not.toContain('disabled')
  })
})
