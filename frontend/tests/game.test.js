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

const { getHandTiles, getHandCount, tileToDisplay, formatPhase, autoSelectChow, getAllChows, escapeHtml, TILE_MAP, sortHandTiles, makeTileEl, makeClaimBtn, selectTile } = globalThis._mahjongTestExports

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

describe('getAllChows', () => {
  it('returns [] for null discarded tile', () => {
    expect(getAllChows(null, ['BAMBOO_1'])).toEqual([])
  })

  it('returns [] for honor/flower tiles', () => {
    expect(getAllChows('EAST', ['EAST', 'SOUTH', 'WEST'])).toEqual([])
    expect(getAllChows('RED', ['RED', 'GREEN', 'WHITE'])).toEqual([])
    expect(getAllChows('FLOWER_1', ['FLOWER_1'])).toEqual([])
  })

  it('returns single option when only one chow is possible', () => {
    // Discard BAMBOO_5, hand has 3-4 only
    expect(getAllChows('BAMBOO_5', ['BAMBOO_3', 'BAMBOO_4'])).toEqual([['BAMBOO_3', 'BAMBOO_4']])
    // Discard BAMBOO_5, hand has 6-7 only
    expect(getAllChows('BAMBOO_5', ['BAMBOO_6', 'BAMBOO_7'])).toEqual([['BAMBOO_6', 'BAMBOO_7']])
  })

  it('returns two options when two chows are possible', () => {
    // Discard BAMBOO_5, hand has 3-4 and 4-6 → combos [3,4] and [4,6]
    const result = getAllChows('BAMBOO_5', ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_6'])
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(['BAMBOO_3', 'BAMBOO_4'])
    expect(result).toContainEqual(['BAMBOO_4', 'BAMBOO_6'])
  })

  it('returns all three options when three chows are possible', () => {
    // Discard BAMBOO_5, hand has 3,4,6,7 → [3,4], [4,6], [6,7]
    const result = getAllChows('BAMBOO_5', ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_6', 'BAMBOO_7'])
    expect(result).toHaveLength(3)
    expect(result).toContainEqual(['BAMBOO_3', 'BAMBOO_4'])
    expect(result).toContainEqual(['BAMBOO_4', 'BAMBOO_6'])
    expect(result).toContainEqual(['BAMBOO_6', 'BAMBOO_7'])
  })

  it('returns [] when hand lacks the needed tiles', () => {
    expect(getAllChows('BAMBOO_5', ['BAMBOO_1', 'CIRCLES_4'])).toEqual([])
  })

  it('does not cross suits', () => {
    // Discard BAMBOO_5, hand has CIRCLES 3-4 — different suit, no chow
    expect(getAllChows('BAMBOO_5', ['CIRCLES_3', 'CIRCLES_4'])).toEqual([])
  })

  it('works for CIRCLES and CHARACTERS suits', () => {
    expect(getAllChows('CIRCLES_9', ['CIRCLES_7', 'CIRCLES_8'])).toEqual([['CIRCLES_7', 'CIRCLES_8']])
    expect(getAllChows('CHARACTERS_1', ['CHARACTERS_2', 'CHARACTERS_3'])).toEqual([['CHARACTERS_2', 'CHARACTERS_3']])
  })

  it('handles duplicate tiles correctly', () => {
    // Hand has two BAMBOO_4: both [3,4] and [4,6] combos can each consume one BAMBOO_4.
    // [6,7] is unavailable (no BAMBOO_7), so expect 2 results.
    const result = getAllChows('BAMBOO_5', ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_4', 'BAMBOO_6'])
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(['BAMBOO_3', 'BAMBOO_4'])
    expect(result).toContainEqual(['BAMBOO_4', 'BAMBOO_6'])
  })

  // ── edge-tile and kanchan cases mirroring the backend edge-case suite ──

  it('edge low: discard BAMBOO_1 yields exactly one option [2,3]', () => {
    // Only combo [num+1, num+2] = [2,3] is in range; [num-2,num-1]=[-1,0] and
    // [num-1,num+1]=[0,2] are filtered because 0 < 1.
    const result = getAllChows('BAMBOO_1', ['BAMBOO_2', 'BAMBOO_3'])
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(['BAMBOO_2', 'BAMBOO_3'])
  })

  it('edge high: discard BAMBOO_9 yields exactly one option [7,8]', () => {
    // Only combo [num-2,num-1]=[7,8] is in range; [num-1,num+1]=[8,10] and
    // [num+1,num+2]=[10,11] are filtered because 10 > 9.
    const result = getAllChows('BAMBOO_9', ['BAMBOO_7', 'BAMBOO_8'])
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(['BAMBOO_7', 'BAMBOO_8'])
  })

  it('kanchan (坎张): discard BAMBOO_5 with only BAMBOO_4 and BAMBOO_6 in hand yields [4,6]', () => {
    // [num-2,num-1]=[3,4]: BAMBOO_3 absent → invalid
    // [num-1,num+1]=[4,6]: both in hand → valid
    // [num+1,num+2]=[6,7]: BAMBOO_7 absent → invalid
    const result = getAllChows('BAMBOO_5', ['BAMBOO_4', 'BAMBOO_6'])
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(['BAMBOO_4', 'BAMBOO_6'])
  })

  it('discard BAMBOO_2 with hand [1,3,3,4] yields two options', () => {
    // [num-2,num-1]=[0,1]: 0 out of range → filtered
    // [num-1,num+1]=[1,3]: BAMBOO_1 and BAMBOO_3 in hand → valid
    // [num+1,num+2]=[3,4]: BAMBOO_3 and BAMBOO_4 in hand → valid
    const result = getAllChows('BAMBOO_2', ['BAMBOO_1', 'BAMBOO_3', 'BAMBOO_3', 'BAMBOO_4'])
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(['BAMBOO_1', 'BAMBOO_3'])
    expect(result).toContainEqual(['BAMBOO_3', 'BAMBOO_4'])
  })

  it('discard BAMBOO_8 with hand [6,7,7,9] yields two options', () => {
    // [num-2,num-1]=[6,7]: BAMBOO_6 and BAMBOO_7 in hand → valid
    // [num-1,num+1]=[7,9]: BAMBOO_7 and BAMBOO_9 in hand → valid
    // [num+1,num+2]=[9,10]: 10 out of range → filtered
    const result = getAllChows('BAMBOO_8', ['BAMBOO_6', 'BAMBOO_7', 'BAMBOO_7', 'BAMBOO_9'])
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(['BAMBOO_6', 'BAMBOO_7'])
    expect(result).toContainEqual(['BAMBOO_7', 'BAMBOO_9'])
  })
})

describe('autoSelectChow - edge cases', () => {
  it('returns null for null tile', () => {
    expect(autoSelectChow(null, ['BAMBOO_1'])).toBeNull()
  })

  it('returns the only option for edge-low tile (discard 1)', () => {
    expect(autoSelectChow('BAMBOO_1', ['BAMBOO_2', 'BAMBOO_3'])).toEqual(['BAMBOO_2', 'BAMBOO_3'])
  })

  it('returns the only option for edge-high tile (discard 9)', () => {
    expect(autoSelectChow('BAMBOO_9', ['BAMBOO_7', 'BAMBOO_8'])).toEqual(['BAMBOO_7', 'BAMBOO_8'])
  })

  it('returns the only option for kanchan (discard 5, hand [4,6])', () => {
    expect(autoSelectChow('BAMBOO_5', ['BAMBOO_4', 'BAMBOO_6'])).toEqual(['BAMBOO_4', 'BAMBOO_6'])
  })

  it('returns the first option when multiple chows are available', () => {
    // For discard 2 with hand [1,3,3,4], getAllChows yields [[1,3],[3,4]] in order;
    // autoSelectChow must return the first: [1,3].
    const result = autoSelectChow('BAMBOO_2', ['BAMBOO_1', 'BAMBOO_3', 'BAMBOO_3', 'BAMBOO_4'])
    expect(result).toEqual(['BAMBOO_1', 'BAMBOO_3'])
  })
})

/* ==========================================================
   Mobile UI — makeTileEl touch-action
   ========================================================== */
describe('makeTileEl — touch interaction', () => {
  it('sets touchAction manipulation on clickable tiles', () => {
    const el = makeTileEl('BAMBOO_5', { clickable: true })
    expect(el.style.touchAction).toBe('manipulation')
  })

  it('also sets cursor:pointer on clickable tiles', () => {
    const el = makeTileEl('BAMBOO_3', { clickable: true })
    expect(el.style.cursor).toBe('pointer')
  })

  it('does not set touchAction on non-clickable tiles (default options)', () => {
    const el = makeTileEl('BAMBOO_5')
    expect(el.style.touchAction).toBeFalsy()
  })

  it('does not set touchAction on face-down tiles', () => {
    // faceDown path returns early before the clickable block
    const el = makeTileEl('BAMBOO_5', { faceDown: true })
    expect(el.style.touchAction).toBeFalsy()
  })

  it('does not set touchAction on explicitly non-clickable tiles', () => {
    const el = makeTileEl('EAST', { clickable: false })
    expect(el.style.touchAction).toBeFalsy()
  })
})

/* ==========================================================
   Mobile UI — makeClaimBtn touch-action
   ========================================================== */
describe('makeClaimBtn — touch interaction', () => {
  it('sets touchAction manipulation on every claim button', () => {
    const btn = makeClaimBtn('Pung 碰', 'btn-primary', () => {})
    expect(btn.style.touchAction).toBe('manipulation')
  })

  it('sets touchAction on skip buttons too', () => {
    const btn = makeClaimBtn('Skip 過', 'btn-secondary', () => {})
    expect(btn.style.touchAction).toBe('manipulation')
  })

  it('registers the click handler on the button', () => {
    const handler = vi.fn()
    const btn = makeClaimBtn('Win 胡!', 'btn-danger', handler)
    expect(btn.addEventListener).toHaveBeenCalledWith('click', handler)
  })
})

/* ==========================================================
   Mobile UI — selectTile scrollIntoView
   ========================================================== */
describe('selectTile — scrollIntoView on mobile', () => {
  // Helper: create a minimal tile element mock.
  // Each test uses a distinct tile string to avoid toggle-deselect behaviour
  // (selecting the same tile twice toggles it off).
  function makeMockEl(withScrollIntoView = true) {
    const el = {
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn() },
      style: {},
      dataset: {},
    }
    if (withScrollIntoView) el.scrollIntoView = vi.fn()
    return el
  }

  it('calls scrollIntoView with smooth, center, nearest when available', () => {
    const el = makeMockEl(true)
    selectTile('CHARACTERS_1', el)
    expect(el.scrollIntoView).toHaveBeenCalledOnce()
    expect(el.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      inline: 'center',
      block: 'nearest',
    })
  })

  it('does not throw when element has no scrollIntoView (desktop / JSDOM)', () => {
    const el = makeMockEl(false)
    expect(() => selectTile('CHARACTERS_2', el)).not.toThrow()
  })

  it('adds the selected class to the element', () => {
    const el = makeMockEl(true)
    selectTile('CHARACTERS_3', el)
    expect(el.classList.add).toHaveBeenCalledWith('selected')
  })

  it('scrollIntoView is called even when gameState is null (no discard logic needed)', () => {
    // gameState is null in test environment; the scrollIntoView path is unconditional
    const el = makeMockEl(true)
    selectTile('CHARACTERS_4', el)
    expect(el.scrollIntoView).toHaveBeenCalled()
  })
})
