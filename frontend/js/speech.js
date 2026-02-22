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
    m[`BAMBOO_${i}`]      = `${_HANZI[i-1]}条`;
    m[`CIRCLES_${i}`]     = `${_HANZI[i-1]}饼`;
    m[`CHARACTERS_${i}`]  = `${_HANZI[i-1]}万`;
  }
  m['EAST']  = '东风'; m['SOUTH'] = '南风';
  m['WEST']  = '西风'; m['NORTH'] = '北风';
  m['RED']   = '红中';   m['GREEN'] = '发财'; m['WHITE'] = '白板';
  m['FLOWER_1'] = '梅花'; m['FLOWER_2'] = '兰花';
  m['FLOWER_3'] = '菊花'; m['FLOWER_4'] = '竹子';
  m['SEASON_1'] = '春';   m['SEASON_2'] = '夏';
  m['SEASON_3'] = '秋';   m['SEASON_4'] = '冬';
  return m;
})();

function tileToSpeech(tileStr) {
  return TILE_SPEECH[tileStr] || null;
}

/* ============================================================
   SpeechEngine class
   ============================================================ */
class SpeechEngine {
  #voice      = null;
  #enabled    = true;
  #active     = false;   // true while an utterance is being spoken
  #queue      = [];      // at most 1 pending action announcement
  #silentCbs  = [];      // callbacks waiting for TTS to go silent

  constructor() {
    this._loadPrefs();
    if (typeof speechSynthesis !== 'undefined') {
      speechSynthesis.onvoiceschanged = () => this._pickVoice();
      this._pickVoice();
    }
  }

  /* ---------- Public API ---------- */

  /**
   * Speak text with one of three modes:
   *
   *   'skip'      (default) — skip if already speaking (tile names from AI discards).
   *   'queue'               — enqueue to play right after the current utterance ends
   *                           (opponent 碰/吃/杠 so they follow the tile-name).
   *   'immediate'           — cancel current speech + clear queue, play now
   *                           (own 碰/吃/杠/胡, own discard tile name).
   */
  speak(text, mode = 'skip') {
    if (!this.#enabled) return;
    if (typeof speechSynthesis === 'undefined') return;
    if (!this.#voice) return;

    if (mode === 'immediate') {
      speechSynthesis.cancel();
      this.#queue  = [];
      this.#active = false;
      this.#speakNow(text);
    } else if (mode === 'queue') {
      if (!this.#active && !speechSynthesis.speaking) {
        this.#speakNow(text);
      } else {
        // Replace any queued action — only keep the most recent
        this.#queue = [text];
      }
    } else {
      // 'skip': speak only if nothing is playing
      if (!this.#active && !speechSynthesis.speaking && !speechSynthesis.pending) {
        this.#speakNow(text);
      }
    }
  }

  /** Announce a tile by its key string (e.g. "BAMBOO_3"). */
  speakTile(tileStr, mode = 'skip') {
    const text = tileToSpeech(tileStr);
    if (text) this.speak(text, mode);
  }

  enable()    { this.#enabled = true;  this._savePrefs(); }
  disable()   {
    this.#enabled = false;
    this.#queue   = [];
    speechSynthesis?.cancel();
    this._savePrefs();
    this.#fireSilentCbs(); // 禁用时视为静默，立即触发所有等待回调
  }
  isEnabled() { return this.#enabled; }
  hasVoice()  { return this.#voice !== null; }

  /**
   * 返回 true 表示 TTS 正在播报（或队列中有待播内容）。
   * 未启用 / 无语音时始终返回 false。
   */
  isSpeaking() {
    if (!this.#enabled || !this.#voice) return false;
    if (typeof speechSynthesis === 'undefined')  return false;
    return this.#active || speechSynthesis.speaking;
  }

  /**
   * 当 TTS 播完并静默时执行 callback。
   * 若当前已静默则立即执行；否则最多等待 maxWaitMs 毫秒（默认 1500ms）
   * 以防语音卡住导致界面永久冻结。
   *
   * 典型用途：人类玩家收到 action_required 时，等上一轮 AI 的语音播完
   * 再显示操作按钮，使音效与界面操作在时序上保持一致。
   */
  onSilent(callback, maxWaitMs = 1500) {
    if (!this.isSpeaking()) {
      callback();
      return;
    }
    // 安全超时：避免 TTS 意外卡住时界面永久等待
    const timer = setTimeout(() => {
      this.#silentCbs = this.#silentCbs.filter(c => c !== wrapped);
      callback();
    }, maxWaitMs);
    const wrapped = () => { clearTimeout(timer); callback(); };
    this.#silentCbs.push(wrapped);
  }

  /* ---------- Private ---------- */

  /** Drain and invoke all pending onSilent callbacks. */
  #fireSilentCbs() {
    const cbs = this.#silentCbs.splice(0);
    cbs.forEach(cb => cb());
  }

  #speakNow(text) {
    if (typeof speechSynthesis === 'undefined') return;
    if (speechSynthesis.state === 'suspended') speechSynthesis.resume?.();

    const utt   = new SpeechSynthesisUtterance(text);
    utt.voice   = this.#voice;
    utt.lang    = 'zh-CN';
    utt.rate    = 0.88;
    utt.pitch   = 1.05;
    utt.volume  = 1.0;

    this.#active = true;

    utt.onend = () => {
      this.#active = false;
      if (this.#queue.length > 0) {
        this.#speakNow(this.#queue.shift());
      } else {
        this.#fireSilentCbs(); // 队列耗尽 → 触发等待回调
      }
    };
    utt.onerror = () => {
      this.#active = false;
      this.#queue  = [];
      this.#fireSilentCbs(); // 出错也触发，避免 UI 卡住
    };

    speechSynthesis.speak(utt);
  }

  _pickVoice() {
    if (typeof speechSynthesis === 'undefined') return;
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return;

    // Priority: Google zh-CN (best) → other Google zh → Neural zh-CN → plain zh-CN → zh-TW/HK → any zh
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
