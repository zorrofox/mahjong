import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import vm from 'vm'

const __dirname = dirname(fileURLToPath(import.meta.url))

// Mock browser globals before loading game.js
const mockWindow = {
  location: { search: '', href: '' },
}
const mockDocument = {
  addEventListener: vi.fn(),
  getElementById: vi.fn(() => null),
  createElement: vi.fn(() => ({
    classList: { add: vi.fn(), toggle: vi.fn(), remove: vi.fn() },
    style: {},
    addEventListener: vi.fn(),
    appendChild: vi.fn(),
    insertBefore: vi.fn(),
    dataset: {},
    innerHTML: '',
    textContent: '',
  })),
  querySelector: vi.fn(() => null),
}

const sandbox = {
  globalThis: globalThis,
  window: mockWindow,
  document: mockDocument,
  WebSocket: class { constructor() {} static OPEN = 1 },
  localStorage: { getItem: vi.fn(() => null), setItem: vi.fn() },
  URLSearchParams: globalThis.URLSearchParams,
  setTimeout: globalThis.setTimeout,
  clearTimeout: globalThis.clearTimeout,
  console: globalThis.console,
  JSON: globalThis.JSON,
  Array: globalThis.Array,
  Object: globalThis.Object,
  String: globalThis.String,
  Set: globalThis.Set,
  Math: globalThis.Math,
  parseInt: globalThis.parseInt,
  isNaN: globalThis.isNaN,
}

const filePath = join(__dirname, '../js/game.js')
const code = readFileSync(filePath, 'utf8')

// Patch the export guard so it fires even with window defined
const patchedCode = code.replace(
  /if \(typeof globalThis !== 'undefined' && typeof window === 'undefined'\)/,
  "if (typeof globalThis !== 'undefined')"
)

vm.runInNewContext(patchedCode, sandbox, { filename: filePath })

const { getHandTiles, getHandCount, tileToDisplay, formatPhase, autoSelectChow, escapeHtml, TILE_MAP, sortHandTiles } = globalThis._mahjongTestExports

/* ==========================================================
   getHandTiles
   ========================================================== */
describe('getHandTiles', () => {
  it('returns [] for null/undefined player', () => {
    expect(getHandTiles(null)).toEqual([])
    expect(getHandTiles(undefined)).toEqual([])
  })

  it('returns [] for player with no hand', () => {
    expect(getHandTiles({})).toEqual([])
    expect(getHandTiles({ hand: null })).toEqual([])
  })

  it('returns [] for hidden opponent hand', () => {
    expect(getHandTiles({ hand: { hidden: true, count: 13 } })).toEqual([])
  })

  it('returns tiles array for visible hand object', () => {
    const tiles = ['BAMBOO_1', 'CIRCLES_5']
    expect(getHandTiles({ hand: { tiles, hidden: false } })).toEqual(tiles)
  })

  it('returns array directly for legacy array hand', () => {
    const tiles = ['EAST', 'WEST']
    expect(getHandTiles({ hand: tiles })).toEqual(tiles)
  })

  it('returns [] when hand object has no tiles key', () => {
    expect(getHandTiles({ hand: { hidden: false } })).toEqual([])
  })
})

/* ==========================================================
   getHandCount
   ========================================================== */
describe('getHandCount', () => {
  it('returns 0 for null/undefined player', () => {
    expect(getHandCount(null)).toBe(0)
    expect(getHandCount(undefined)).toBe(0)
  })

  it('returns 0 for player with no hand', () => {
    expect(getHandCount({})).toBe(0)
    expect(getHandCount({ hand: null })).toBe(0)
  })

  it('returns count from hidden hand', () => {
    expect(getHandCount({ hand: { hidden: true, count: 13 } })).toBe(13)
  })

  it('returns 0 for hidden hand without count', () => {
    expect(getHandCount({ hand: { hidden: true } })).toBe(0)
  })

  it('returns length from visible hand tiles', () => {
    expect(getHandCount({ hand: { tiles: ['A', 'B', 'C'], hidden: false } })).toBe(3)
  })

  it('returns length from legacy array hand', () => {
    expect(getHandCount({ hand: ['X', 'Y'] })).toBe(2)
  })
})

/* ==========================================================
   tileToDisplay
   ========================================================== */
describe('tileToDisplay', () => {
  it('returns fallback for null/undefined', () => {
    expect(tileToDisplay(null)).toEqual({ text: '?', label: '?', cls: '' })
    expect(tileToDisplay(undefined)).toEqual({ text: '?', label: '?', cls: '' })
    expect(tileToDisplay('')).toEqual({ text: '?', label: '?', cls: '' })
  })

  it('maps BAMBOO tiles correctly', () => {
    const HANZI = ['一','二','三','四','五','六','七','八','九']
    for (let i = 1; i <= 9; i++) {
      const info = tileToDisplay(`BAMBOO_${i}`)
      expect(info.text).toBe(HANZI[i-1])
      expect(info.sub).toBe('条')
      expect(info.label).toBe(`B${i}`)
      expect(info.cls).toBe('tile-bamboo')
      expect(info.suit).toBe('B')
    }
  })

  it('maps CIRCLES tiles correctly', () => {
    const HANZI = ['一','二','三','四','五','六','七','八','九']
    for (let i = 1; i <= 9; i++) {
      const info = tileToDisplay(`CIRCLES_${i}`)
      expect(info.text).toBe(HANZI[i-1])
      expect(info.sub).toBe('饼')
      expect(info.label).toBe(`C${i}`)
      expect(info.cls).toBe('tile-circles')
      expect(info.suit).toBe('C')
    }
  })

  it('maps CHARACTERS tiles correctly', () => {
    const HANZI = ['一','二','三','四','五','六','七','八','九']
    for (let i = 1; i <= 9; i++) {
      const info = tileToDisplay(`CHARACTERS_${i}`)
      expect(info.text).toBe(HANZI[i-1])
      expect(info.sub).toBe('萬')
      expect(info.label).toBe(`M${i}`)
      expect(info.cls).toBe('tile-characters')
      expect(info.suit).toBe('M')
    }
  })

  it('maps wind tiles', () => {
    expect(tileToDisplay('EAST').text).toBe('東')
    expect(tileToDisplay('SOUTH').text).toBe('南')
    expect(tileToDisplay('WEST').text).toBe('西')
    expect(tileToDisplay('NORTH').text).toBe('北')
  })

  it('maps dragon tiles', () => {
    expect(tileToDisplay('RED').text).toBe('中')
    expect(tileToDisplay('GREEN').text).toBe('發')
    expect(tileToDisplay('WHITE').text).toBe('白')
  })

  it('maps flower tiles', () => {
    expect(tileToDisplay('FLOWER_1').text).toBe('梅')
    expect(tileToDisplay('FLOWER_2').text).toBe('蘭')
    expect(tileToDisplay('FLOWER_3').text).toBe('菊')
    expect(tileToDisplay('FLOWER_4').text).toBe('竹')
  })

  it('maps season tiles', () => {
    expect(tileToDisplay('SEASON_1').text).toBe('春')
    expect(tileToDisplay('SEASON_2').text).toBe('夏')
    expect(tileToDisplay('SEASON_3').text).toBe('秋')
    expect(tileToDisplay('SEASON_4').text).toBe('冬')
  })

  it('returns fallback for unknown tile', () => {
    const info = tileToDisplay('UNKNOWN_TILE')
    expect(info.text).toBe('UNK')
    expect(info.label).toBe('UNKNOWN_TILE')
    expect(info.cls).toBe('')
  })
})

/* ==========================================================
   TILE_MAP completeness
   ========================================================== */
describe('TILE_MAP', () => {
  it('has 42 entries (9*3 + 4 winds + 3 dragons + 4 flowers + 4 seasons)', () => {
    expect(Object.keys(TILE_MAP).length).toBe(27 + 4 + 3 + 4 + 4)
  })
})

/* ==========================================================
   formatPhase
   ========================================================== */
describe('formatPhase', () => {
  it('returns empty string for falsy input', () => {
    expect(formatPhase(null)).toBe('')
    expect(formatPhase(undefined)).toBe('')
    expect(formatPhase('')).toBe('')
  })

  it('maps known phases', () => {
    expect(formatPhase('waiting')).toBe('Waiting')
    expect(formatPhase('dealing')).toBe('Dealing')
    expect(formatPhase('drawing')).toBe('Drawing')
    expect(formatPhase('discarding')).toBe('Discarding')
    expect(formatPhase('claiming')).toBe('Claiming')
    expect(formatPhase('finished')).toBe('Finished')
    expect(formatPhase('lobby')).toBe('Lobby')
  })

  it('handles mixed case input', () => {
    expect(formatPhase('DRAWING')).toBe('Drawing')
    expect(formatPhase('Claiming')).toBe('Claiming')
  })

  it('returns raw string for unknown phase', () => {
    expect(formatPhase('custom_phase')).toBe('custom_phase')
  })
})

/* ==========================================================
   autoSelectChow
   ========================================================== */
describe('autoSelectChow', () => {
  it('returns null for null discarded tile', () => {
    expect(autoSelectChow(null, ['BAMBOO_1'])).toBeNull()
  })

  it('returns null for honor tiles (no suit)', () => {
    expect(autoSelectChow('EAST', ['EAST', 'SOUTH', 'WEST'])).toBeNull()
    expect(autoSelectChow('RED', ['RED', 'GREEN', 'WHITE'])).toBeNull()
  })

  it('returns null for flower/season tiles', () => {
    expect(autoSelectChow('FLOWER_1', ['FLOWER_1'])).toBeNull()
    expect(autoSelectChow('SEASON_2', ['SEASON_2'])).toBeNull()
  })

  it('selects (n-2, n-1) combo', () => {
    expect(autoSelectChow('BAMBOO_5', ['BAMBOO_3', 'BAMBOO_4', 'CIRCLES_1'])).toEqual(['BAMBOO_3', 'BAMBOO_4'])
    expect(autoSelectChow('CIRCLES_9', ['CIRCLES_7', 'CIRCLES_8'])).toEqual(['CIRCLES_7', 'CIRCLES_8'])
    expect(autoSelectChow('CHARACTERS_9', ['CHARACTERS_7', 'CHARACTERS_8'])).toEqual(['CHARACTERS_7', 'CHARACTERS_8'])
  })

  it('returns null when hand lacks needed tiles', () => {
    expect(autoSelectChow('BAMBOO_5', ['BAMBOO_1', 'CIRCLES_9'])).toBeNull()
  })

  it('does not cross suits', () => {
    expect(autoSelectChow('BAMBOO_5', ['CIRCLES_3', 'CIRCLES_4'])).toBeNull()
  })
})

/* ==========================================================
   escapeHtml (game.js version)
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

  it('escapes combined special characters', () => {
    expect(escapeHtml('<script>"alert&1"</script>')).toBe(
      '&lt;script&gt;&quot;alert&amp;1&quot;&lt;/script&gt;'
    )
  })

  it('returns normal strings unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world')
  })

  it('converts non-string to string', () => {
    expect(escapeHtml(123)).toBe('123')
  })
})

/* ==========================================================
   sortHandTiles
   ========================================================== */
describe('sortHandTiles', () => {
  it('returns empty array for empty input', () => {
    expect(sortHandTiles([])).toEqual([])
  })

  it('does not mutate the original array', () => {
    const hand = ['WEST', 'BAMBOO_5', 'CIRCLES_1']
    const original = [...hand]
    sortHandTiles(hand)
    expect(hand).toEqual(original)
  })

  it('sorts bamboo before circles before characters', () => {
    const hand = ['CHARACTERS_1', 'CIRCLES_1', 'BAMBOO_1']
    const sorted = sortHandTiles(hand)
    expect(sorted).toEqual(['BAMBOO_1', 'CIRCLES_1', 'CHARACTERS_1'])
  })

  it('sorts numbers within same suit in ascending order', () => {
    const hand = ['BAMBOO_9', 'BAMBOO_1', 'BAMBOO_5', 'BAMBOO_3']
    const sorted = sortHandTiles(hand)
    expect(sorted).toEqual(['BAMBOO_1', 'BAMBOO_3', 'BAMBOO_5', 'BAMBOO_9'])
  })

  it('places honor tiles (winds/dragons) after suit tiles', () => {
    const hand = ['EAST', 'BAMBOO_3', 'RED', 'CIRCLES_7']
    const sorted = sortHandTiles(hand)
    // Suit tiles first, then honors
    expect(sorted.indexOf('BAMBOO_3')).toBeLessThan(sorted.indexOf('EAST'))
    expect(sorted.indexOf('CIRCLES_7')).toBeLessThan(sorted.indexOf('RED'))
  })

  it('places flower/season tiles after suit tiles', () => {
    const hand = ['FLOWER_1', 'BAMBOO_2', 'SEASON_3', 'CHARACTERS_9']
    const sorted = sortHandTiles(hand)
    expect(sorted.indexOf('BAMBOO_2')).toBeLessThan(sorted.indexOf('FLOWER_1'))
    expect(sorted.indexOf('CHARACTERS_9')).toBeLessThan(sorted.indexOf('SEASON_3'))
  })

  it('sorts a mixed realistic hand correctly', () => {
    const hand = [
      'EAST', 'BAMBOO_7', 'CIRCLES_3', 'CHARACTERS_1',
      'BAMBOO_2', 'CIRCLES_9', 'CHARACTERS_5', 'RED',
    ]
    const sorted = sortHandTiles(hand)
    // All bamboo before circles before characters before honors
    const bIdx  = sorted.findIndex(t => t.startsWith('BAMBOO'))
    const cIdx  = sorted.findIndex(t => t.startsWith('CIRCLES'))
    const mIdx  = sorted.findIndex(t => t.startsWith('CHARACTERS'))
    const honorIdx = sorted.findIndex(t => t === 'EAST' || t === 'RED')
    expect(bIdx).toBeLessThan(cIdx)
    expect(cIdx).toBeLessThan(mIdx)
    expect(mIdx).toBeLessThan(honorIdx)
  })

  it('sorts all nine bamboo tiles in order', () => {
    const hand = ['BAMBOO_9','BAMBOO_8','BAMBOO_7','BAMBOO_6','BAMBOO_5',
                  'BAMBOO_4','BAMBOO_3','BAMBOO_2','BAMBOO_1']
    const sorted = sortHandTiles(hand)
    expect(sorted).toEqual(['BAMBOO_1','BAMBOO_2','BAMBOO_3','BAMBOO_4','BAMBOO_5',
                            'BAMBOO_6','BAMBOO_7','BAMBOO_8','BAMBOO_9'])
  })
})
