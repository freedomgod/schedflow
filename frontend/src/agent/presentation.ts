import type { AgentMessage } from './types'
/** Receipt and execution blocks share one live card keyed by durable operation ID. */
export function deduplicateOperationCards(messages: AgentMessage[]): AgentMessage[] {
  const seen = new Set<string>()
  return messages.flatMap(message => {
    const blocks = message.blocks.filter(block => {
      if (block.type !== 'operation_receipt' && block.type !== 'execution') return true
      if (seen.has(block.operation_id)) return false
      seen.add(block.operation_id)
      return true
    })
    return blocks.length === 0 && message.blocks.length > 0 ? [] : [{ ...message, blocks }]
  })
}
