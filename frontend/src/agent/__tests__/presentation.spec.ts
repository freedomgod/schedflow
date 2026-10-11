import { describe, expect, it } from 'vitest'
import { deduplicateOperationCards } from '../presentation'
import type { AgentMessage } from '../types'
const message = (messageId: string, blocks: AgentMessage['blocks']): AgentMessage => ({ message_id: messageId, role: 'assistant', status: 'completed', blocks })
describe('chat operation card presentation', () => {
  it('renders one card when the same operation has a receipt and execution block', () => {
    const messages = [message('m', [{ type: 'operation_receipt', operation_id: 'o' }, { type: 'execution', operation_id: 'o' }])]
    expect(deduplicateOperationCards(messages)[0].blocks).toEqual([{ type: 'operation_receipt', operation_id: 'o' }])
    expect(messages[0].blocks).toHaveLength(2)
  })
  it('keeps other operations and text while deduplicating updates across messages', () => {
    const messages = [message('receipt', [{ type: 'operation_receipt', operation_id: 'o' }]), message('update', [{ type: 'assistant_text', text: '执行已完成' }, { type: 'execution', operation_id: 'o' }, { type: 'execution', operation_id: 'other' }])]
    expect(deduplicateOperationCards(messages)[1].blocks).toEqual([{ type: 'assistant_text', text: '执行已完成' }, { type: 'execution', operation_id: 'other' }])
  })
  it('omits a duplicate-only message without hiding an empty streaming message', () => {
    const messages = [message('first', [{ type: 'execution', operation_id: 'o' }]), message('duplicate', [{ type: 'operation_receipt', operation_id: 'o' }]), { ...message('streaming', []), status: 'streaming' as const }]
    expect(deduplicateOperationCards(messages).map(item => item.message_id)).toEqual(['first', 'streaming'])
  })
})
