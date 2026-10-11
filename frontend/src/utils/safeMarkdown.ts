import { Marked } from 'marked'

function escapeHtml(text: string): string { return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;') }
function safeUrl(href: string): boolean {
  // Reject entity escapes, control characters and whitespace tricks before URL parsing.
  if (/[\u0000-\u0020\u007f]|&(?:#|[a-z])/i.test(href)) return false
  return /^https?:\/\//i.test(href) || /^mailto:/i.test(href) || /^\/(?!\/)/.test(href) || /^#/.test(href)
}
const markdown = new Marked({
  breaks: true,
  renderer: {
    html({ text }) { return escapeHtml(text) },
    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens)
      return safeUrl(href) ? `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ''} target="_blank" rel="noopener noreferrer">${text}</a>` : text
    },
    // Model-provided image URLs are displayed as text; they cannot make remote requests.
    image({ text }) { return escapeHtml(text) },
  },
})
export function safeMarkdown(text?: string | null): string { return text ? markdown.parse(text, { async: false }) as string : '' }
