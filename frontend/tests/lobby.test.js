import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import vm from 'vm'

const __dirname = dirname(fileURLToPath(import.meta.url))

// Mock browser globals
const mockDocument = {
  addEventListener: vi.fn(),
  getElementById: vi.fn(() => null),
  createElement: vi.fn(() => ({
    classList: { add: vi.fn(), toggle: vi.fn() },
    style: {},
    addEventListener: vi.fn(),
    appendChild: vi.fn(),
    innerHTML: '',
    textContent: '',
    className: '',
  })),
}

const sandbox = {
  globalThis: globalThis,
  window: { location: { href: '' } },
  document: mockDocument,
  localStorage: { getItem: vi.fn(() => null), setItem: vi.fn() },
  fetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })),
  prompt: vi.fn(() => null),
  alert: vi.fn(),
  setInterval: vi.fn(() => 0),
  clearInterval: vi.fn(),
  encodeURIComponent: globalThis.encodeURIComponent,
  console: globalThis.console,
  JSON: globalThis.JSON,
  Array: globalThis.Array,
  Object: globalThis.Object,
  String: globalThis.String,
  Math: globalThis.Math,
  Date: globalThis.Date,
  Promise: globalThis.Promise,
}

const filePath = join(__dirname, '../js/lobby.js')
const code = readFileSync(filePath, 'utf8')

// Patch the export guard so it fires with window defined
const patchedCode = code.replace(
  /if \(typeof globalThis !== 'undefined' && typeof window === 'undefined'\)/,
  "if (typeof globalThis !== 'undefined')"
)

vm.runInNewContext(patchedCode, sandbox, { filename: filePath })

const { getStatusClass, formatStatus, escapeHtml, escapeAttr } = globalThis._lobbyTestExports

/* ==========================================================
   getStatusClass
   ========================================================== */
describe('getStatusClass', () => {
  it('returns empty string for falsy input', () => {
    expect(getStatusClass(null)).toBe('')
    expect(getStatusClass(undefined)).toBe('')
    expect(getStatusClass('')).toBe('')
  })

  it('maps waiting to status-waiting', () => {
    expect(getStatusClass('waiting')).toBe('status-waiting')
  })

  it('maps playing to status-playing', () => {
    expect(getStatusClass('playing')).toBe('status-playing')
  })

  it('maps finished to status-finished', () => {
    expect(getStatusClass('finished')).toBe('status-finished')
    expect(getStatusClass('ended')).toBe('status-finished')
  })

  it('handles mixed case', () => {
    expect(getStatusClass('WAITING')).toBe('status-waiting')
    expect(getStatusClass('Playing')).toBe('status-playing')
    expect(getStatusClass('FINISHED')).toBe('status-finished')
  })

  it('returns empty string for unknown status', () => {
    expect(getStatusClass('unknown')).toBe('')
    expect(getStatusClass('started')).toBe('')
  })
})

/* ==========================================================
   formatStatus
   ========================================================== */
describe('formatStatus', () => {
  it('returns Unknown for falsy input', () => {
    expect(formatStatus(null)).toBe('Unknown')
    expect(formatStatus(undefined)).toBe('Unknown')
    expect(formatStatus('')).toBe('Unknown')
  })

  it('maps known statuses', () => {
    expect(formatStatus('waiting')).toBe('Waiting 等待中')
    expect(formatStatus('playing')).toBe('Playing 游戏中')
    expect(formatStatus('finished')).toBe('Finished 已结束')
    expect(formatStatus('ended')).toBe('Finished 已结束')
  })

  it('handles mixed case', () => {
    expect(formatStatus('WAITING')).toBe('Waiting 等待中')
    expect(formatStatus('Playing')).toBe('Playing 游戏中')
  })

  it('returns raw string for unknown status', () => {
    expect(formatStatus('custom')).toBe('custom')
  })
})

/* ==========================================================
   escapeHtml (lobby.js version)
   ========================================================== */
describe('escapeHtml', () => {
  it('returns empty string for null/undefined', () => {
    expect(escapeHtml(null)).toBe('')
    expect(escapeHtml(undefined)).toBe('')
  })

  it('escapes & < > "', () => {
    expect(escapeHtml('&')).toBe('&amp;')
    expect(escapeHtml('<')).toBe('&lt;')
    expect(escapeHtml('>')).toBe('&gt;')
    expect(escapeHtml('"')).toBe('&quot;')
  })

  it('escapes combined characters', () => {
    expect(escapeHtml('<b>"hi"&</b>')).toBe('&lt;b&gt;&quot;hi&quot;&amp;&lt;/b&gt;')
  })

  it('passes through normal strings', () => {
    expect(escapeHtml('hello')).toBe('hello')
  })

  it('converts numbers to string', () => {
    expect(escapeHtml(42)).toBe('42')
  })
})

/* ==========================================================
   escapeAttr
   ========================================================== */
describe('escapeAttr', () => {
  it('escapes single quotes', () => {
    expect(escapeAttr("it's")).toBe("it\\'s")
  })

  it('handles strings without single quotes', () => {
    expect(escapeAttr('hello')).toBe('hello')
  })

  it('escapes multiple single quotes', () => {
    expect(escapeAttr("a'b'c")).toBe("a\\'b\\'c")
  })

  it('converts non-string to string', () => {
    expect(escapeAttr(123)).toBe('123')
  })
})
