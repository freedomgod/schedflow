import { describe, expect, it } from 'vitest'
import { safeMarkdown } from '../../utils/safeMarkdown'

describe('safe Markdown', () => {
  it('escapes raw HTML and removes executable links and SVG payloads', () => {
    const output = safeMarkdown('<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[click](javascript:alert(1))\n[encoded](jav&#x61;script:alert(1))\n![image](data:image/svg+xml;base64,PHN2Zz4=)')
    expect(output).not.toContain('<script>')
    expect(output).not.toContain('<img')
    expect(output).not.toContain('href="javascript:')
    expect(output).not.toContain('href="jav&#')
    expect(output).not.toContain('src="data:')
  })
  it('preserves safe markdown and applies noopener to external links', () => {
    const output = safeMarkdown('**Ready** [docs](https://example.com/?q="unsafe") `a < b`')
    expect(output).toContain('<strong>Ready</strong>')
    expect(output).toContain('rel="noopener noreferrer"')
    expect(output).toContain('a &lt; b')
  })
})
