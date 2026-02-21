/* ============================================================
   speech.js — Chinese TTS voice announcements for Mahjong
   Uses the Web Speech API (speechSynthesis); zero audio files,
   zero backend changes, zero external dependencies.
   ============================================================ */

/* ---------- Tile name → spoken Chinese text ---------- */
const _HANZI = ['一','二','三','四','五','六','七','八','九'];

const TILE_SPEECH = (() => {
  const m = {};
  for (let i = 1; i <= 9; i++) {
    m[`BAMBOO_${i}`]     = `${_HANZI[i-1]}条`;
    m[`CIRCLES_${i}`]   = `${_HANZI[i-1]}饼`;
    m[`CHARACTERS_${i}`]= `${_HANZI[i-1]}万`;
  }
  m['EAST']  = '东风'; m['SOUTH'] = '南风';
  m['WEST']  = '西风'; m['NORTH'] = '北风';
  m['RED']   = '中';   m['GREEN'] = '发财'; m['WHITE'] = '白板';
  m['FLOWER_1'] = '梅花'; m['FLOWER_2'] = '兰花';
  m['FLOWER_3'] = '菊花'; m['FLOWER_4'] = '竹子';
  m['SEASON_1'] = '春';   m['SEASON_2'] = '夏';
  m['SEASON_3'] = '秋';   m['SEASON_4'] = '冬';
  return m;
})();

/**
 * Return the Chinese spoken text for a tile string, or null if unknown.
 */
function tileToSpeech(tileStr) {
  return TILE_SPEECH[tileStr] || null;
}

/* ============================================================
   SpeechEngine class
   ============================================================ */
class SpeechEngine {
  #voice    = null;   // selected zh voice; null = no Chinese TTS available
  #enabled  = true;   // user toggle

  constructor() {
    this._loadPrefs();
    // Voices may load asynchronously (especially Chrome)
    if (typeof speechSynthesis !== 'undefined') {
      speechSynthesis.onvoiceschanged = () => this._pickVoice();
      this._pickVoice();
    }
  }

  /* ---------- Public API ---------- */

  /** Speak text.
   *  priority=true: cancel any current speech first (for action calls). */
  speak(text, priority = false) {
    if (!this.#enabled) return;
    if (typeof speechSynthesis === 'undefined') return;  // Node/jsdom safety
    if (!this.#voice) return;  // no Chinese voice found

    if (priority) {
      speechSynthesis.cancel();
    } else if (speechSynthesis.speaking || speechSynthesis.pending) {
      // Avoid piling up AI discard announcements — skip if busy
      return;
    }

    const utt      = new SpeechSynthesisUtterance(text);
    utt.voice      = this.#voice;
    utt.lang       = 'zh-CN';
    utt.rate       = 0.88;  // deliberate pace — prevents robotic clipping
    utt.pitch      = 1.05;  // very slightly brighter, less flat
    utt.volume     = 1.0;
    speechSynthesis.speak(utt);
  }

  /** Announce a tile by its key string (e.g. "BAMBOO_3"). */
  speakTile(tileStr, priority = false) {
    const text = tileToSpeech(tileStr);
    if (text) this.speak(text, priority);
  }

  enable()   { this.#enabled = true;  this._savePrefs(); }
  disable()  { this.#enabled = false; speechSynthesis?.cancel(); this._savePrefs(); }
  isEnabled(){ return this.#enabled; }

  /** true if a Chinese voice was found on this device. */
  hasVoice() { return this.#voice !== null; }

  /* ---------- Private ---------- */

  _pickVoice() {
    if (typeof speechSynthesis === 'undefined') return;
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return;

    // Priority order (best quality first):
    // 1. Google 普通话 / Google zh-CN  — best quality in Chrome
    // 2. Any "Neural" or "Natural" zh-CN voice
    // 3. zh-CN (any)
    // 4. zh-TW / zh-HK
    // 5. Any zh voice
    const pref = [
      v => /google/i.test(v.name) && /zh[-_]CN/i.test(v.lang),
      v => /google/i.test(v.name) && /^zh/i.test(v.lang),
      v => /(neural|natural)/i.test(v.name) && /zh[-_]CN/i.test(v.lang),
      v => /zh[-_]CN/i.test(v.lang),
      v => /zh[-_]TW/i.test(v.lang) || /zh[-_]HK/i.test(v.lang),
      v => /^zh/i.test(v.lang),
    ];
    for (const test of pref) {
      const found = voices.find(test);
      if (found) { this.#voice = found; return; }
    }
    // No Chinese voice — remain null (silent)
  }

  _loadPrefs() {
    try {
      const raw = localStorage.getItem('mahjong_speech_prefs');
      if (raw) {
        const p = JSON.parse(raw);
        if (typeof p.enabled === 'boolean') this.#enabled = p.enabled;
      }
    } catch (_) {}
  }

  _savePrefs() {
    try {
      localStorage.setItem('mahjong_speech_prefs',
        JSON.stringify({ enabled: this.#enabled }));
    } catch (_) {}
  }
}
