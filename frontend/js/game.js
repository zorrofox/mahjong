/* ============================================================
   game.js – Mahjong Game Board
   ============================================================ */

// 自动适配本地开发（localhost:8000）和生产环境（当前域名）
const _isLocal   = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE   = _isLocal ? `http://${window.location.host}` : '';
const WS_BASE    = _isLocal
  ? `ws://${window.location.host}`
  : `wss://${window.location.host}`;

/* ---------- URL params ---------- */
const urlParams  = new URLSearchParams(window.location.search);
const ROOM_ID    = urlParams.get('room')   || '';
const PLAYER_ID  = urlParams.get('player') || '';

/* ---------- App State ---------- */
let ws             = null;
let reconnectTimer = null;
let gameState      = null;
let myPlayerIdx    = -1;
let selectedTile   = null;
let pendingActions = [];
let inClaimWindow  = false;
let statusDismissTimer = null;
let claimCountdownTimer = null;
// When true, the post-game board reveals all players' hands face-up.
// Set by the Close button on the game-over modal; reset when a new game starts.
window._endReveal = false;
// Tracks which claim action the local player most recently sent ('chow' | 'pung' |
// 'kong' | 'win' | null).  Used in handleGameState to decide whether a meld that
// appeared for ANOTHER player should cancel a pending local claim sound.
let _myClaimSent = null;

// Tracks whether the local player just sent a discard or a win claim.
// Used to suppress redundant sound announcements from server broadcasts.
let _myDiscardSent = null;
let _myWinSent = false;

// Double-tap detection for mobile (touchend-based, shared across all hand tiles).
let _dblTapTimer = null;
let _dblTapTile  = null;

// Discard pile spatial layout: set once after myPlayerIdx is known, never again.
// Running on every game_state causes repeated style recalculations and flicker.
let _discardLayoutReady = false;

// Deal animation: track which round we last animated so the same round_number
// arriving multiple times (reconnect, board re-render) doesn't re-trigger.
let _lastDealRound = -1;

// Bao (宝牌) state — Dalian ruleset treasure tile mechanism.
let _baoTile = null;          // 当前宝牌，null 表示未揭示
let _tenpaiPlayers = [];      // 已宣听玩家索引列表
let _hideBao = false;         // 玩家选择「不看宝」时为 true，屏蔽所有宝牌视觉展示

/* ---------- Speech engine singleton ---------- */
let _speech = null;
function getSpeech() {
  if (_speech === null && typeof SpeechEngine !== 'undefined') {
    _speech = new SpeechEngine();
  }
  return _speech;
}

/* ============================================================
   TILE DISPLAY
   ============================================================ */
const TILE_MAP = (() => {
  const m = {};
  const HANZI = ['一','二','三','四','五','六','七','八','九'];

  // Bamboo 1-9 (条子)
  for (let i = 1; i <= 9; i++) {
    m[`BAMBOO_${i}`] = { text: HANZI[i-1], sub: '条', label: `B${i}`, cls: 'tile-bamboo', suit: 'B' };
  }
  // Circles 1-9 (筒子/饼)
  for (let i = 1; i <= 9; i++) {
    m[`CIRCLES_${i}`] = { text: HANZI[i-1], sub: '饼', label: `C${i}`, cls: 'tile-circles', suit: 'C' };
  }
  // Characters 1-9 (万字)
  for (let i = 1; i <= 9; i++) {
    m[`CHARACTERS_${i}`] = { text: HANZI[i-1], sub: '萬', label: `M${i}`, cls: 'tile-characters', suit: 'M' };
  }
  // Winds
  m['EAST']  = { text: '東', label: 'E',  cls: 'tile-wind' };
  m['SOUTH'] = { text: '南', label: 'S',  cls: 'tile-wind' };
  m['WEST']  = { text: '西', label: 'W',  cls: 'tile-wind' };
  m['NORTH'] = { text: '北', label: 'N',  cls: 'tile-wind' };
  // Dragons
  m['RED']   = { text: '中', label: '中', cls: 'tile-dragon tile-red' };
  m['GREEN'] = { text: '發', label: '發', cls: 'tile-dragon tile-green' };
  m['WHITE'] = { text: '白', label: '白', cls: 'tile-dragon tile-white' };
  // Flowers
  m['FLOWER_1'] = { text: '梅', label: '梅', cls: 'tile-flower' };
  m['FLOWER_2'] = { text: '蘭', label: '蘭', cls: 'tile-flower' };
  m['FLOWER_3'] = { text: '菊', label: '菊', cls: 'tile-flower' };
  m['FLOWER_4'] = { text: '竹', label: '竹', cls: 'tile-flower' };
  // Seasons
  m['SEASON_1'] = { text: '春', label: '春', cls: 'tile-season' };
  m['SEASON_2'] = { text: '夏', label: '夏', cls: 'tile-season' };
  m['SEASON_3'] = { text: '秋', label: '秋', cls: 'tile-season' };
  m['SEASON_4'] = { text: '冬', label: '冬', cls: 'tile-season' };

  return m;
})();

/**
 * Normalize player.hand from server format to a plain tile array.
 * Server sends: {tiles:[...], hidden:false} for own hand,
 *               {hidden:true, count:N}      for opponents.
 * Returns [] for hidden hands (count shown separately via getHandCount).
 */
function getHandTiles(player) {
  if (!player) return [];
  const h = player.hand;
  if (!h) return [];
  if (Array.isArray(h)) return h;          // legacy / direct array
  if (h.hidden) return [];                 // opponent hidden hand
  return h.tiles || [];                   // own hand: {tiles:[...], hidden:false}
}

/**
 * Return a sorted copy of a hand tile array.
 * Sort order: Bamboo (B) → Circles (C) → Characters (M) → Winds/Dragons/Flowers/Seasons.
 * Within each suit, tiles are sorted by their label (B1 < B2 … < B9).
 * The original array is not mutated.
 */
const _SUIT_ORDER = { B: 0, C: 1, M: 2 };
function sortHandTiles(hand) {
  return [...hand].sort((a, b) => {
    const ia = TILE_MAP[a] || {};
    const ib = TILE_MAP[b] || {};
    const sa = ia.suit !== undefined ? _SUIT_ORDER[ia.suit] : 3;
    const sb = ib.suit !== undefined ? _SUIT_ORDER[ib.suit] : 3;
    if (sa !== sb) return sa - sb;
    return (ia.label || a).localeCompare(ib.label || b);
  });
}

/**
 * Return the number of tiles in a player's hand (works for hidden hands too).
 */
function getHandCount(player) {
  if (!player) return 0;
  const h = player.hand;
  if (!h) return 0;
  if (Array.isArray(h)) return h.length;
  if (h.hidden) return h.count || 0;
  return (h.tiles || []).length;
}

/**
 * Convert tile string to display info.
 * Returns { text, label, cls } or a fallback.
 */
function tileToDisplay(tileStr) {
  if (!tileStr) return { text: '?', label: '?', cls: '' };
  const info = TILE_MAP[tileStr];
  if (info) return info;
  return { text: tileStr.slice(0, 3), label: tileStr, cls: '' };
}

/* ============================================================
   TILE IMAGE MAP  (Wikimedia Cangjie6 oblique SVG tiles)
   Files are in frontend/tiles/{TILE_KEY}.svg
   ============================================================ */
const TILE_SVG_MAP = (() => {
  const m = {};
  ['BAMBOO','CIRCLES','CHARACTERS'].forEach(suit => {
    for (let i = 1; i <= 9; i++) m[`${suit}_${i}`] = `tiles/${suit}_${i}.svg`;
  });
  ['EAST','SOUTH','WEST','NORTH','RED','GREEN','WHITE'].forEach(k => { m[k] = `tiles/${k}.svg`; });
  ['FLOWER_1','FLOWER_2','FLOWER_3','FLOWER_4',
   'SEASON_1','SEASON_2','SEASON_3','SEASON_4'].forEach(k => { m[k] = `tiles/${k}.svg`; });
  return m;
})();

/* ============================================================
   REMOVED: inline SVG generators (_makeBamboo1SVG, _makeBambooSVG, _makeCircleSVG)
   All tile rendering now uses <img> tags pointing to Cangjie6 oblique SVG files.
   ============================================================ */

/**
 * Build a tile DOM element.
 * Uses Cangjie6 oblique SVG images from frontend/tiles/.
 * Falls back to text if image is missing.
 * @param {string} tileStr  e.g. "BAMBOO_1", "EAST", "RED"
 * @param {object} options  { clickable, selected, faceDown }
 */
function makeTileEl(tileStr, options = {}) {
  const el = document.createElement('span');
  el.classList.add('tile');

  if (options.faceDown) {
    el.classList.add('tile-back');
    el.title = 'Face-down tile';
    return el;
  }

  const info    = tileToDisplay(tileStr);
  const svgPath = TILE_SVG_MAP[tileStr];

  if (svgPath) {
    const img = document.createElement('img');
    img.src = svgPath;
    img.alt = info.label || tileStr;
    img.classList.add('tile-img');
    img.onerror = () => {
      el.removeChild(img);
      el.innerHTML = `<span class="tile-main">${escapeHtml(info.text || tileStr)}</span>`;
    };
    el.appendChild(img);
  } else {
    el.innerHTML = `<span class="tile-main">${escapeHtml(info.text || tileStr)}</span>`;
  }

  el.title = info.label || tileStr;
  el.dataset.tile = tileStr;

  if (options.winning) el.classList.add('tile-winning');
  if (options.selected) el.classList.add('selected');
  if (options.clickable) {
    el.style.cursor = 'pointer';
    el.style.touchAction = 'manipulation'; // 消除 iOS 300ms 点击延迟
    el.addEventListener('click', () => selectTile(tileStr, el));

    // ── 双击出牌（桌面）──────────────────────────────────────
    // dblclick 在桌面可靠；移动端由 touchend 另行处理。
    el.addEventListener('dblclick', () => {
      if (!pendingActions.includes('discard') || inClaimWindow) return;
      if (selectedTile !== tileStr) selectTile(tileStr, el);
      sendDiscard();
    });

    // ── 双击出牌（移动端：自定义 touchend 时间差检测）───────
    // touch-action:manipulation 会阻止浏览器生成 dblclick，
    // 因此用 touchend 手动检测 300ms 内的两次点击。
    el.addEventListener('touchend', (e) => {
      if (_dblTapTimer && _dblTapTile === tileStr) {
        // 第二次点击在 300ms 内 → 双击
        clearTimeout(_dblTapTimer);
        _dblTapTimer = null;
        _dblTapTile  = null;
        // 阻止后续合成的 click 事件（防止 toggle 取消选中）
        e.preventDefault();
        if (!pendingActions.includes('discard') || inClaimWindow) return;
        if (selectedTile !== tileStr) selectTile(tileStr, el);
        sendDiscard();
      } else {
        // 第一次点击 → 等待第二次
        clearTimeout(_dblTapTimer);
        _dblTapTile  = tileStr;
        _dblTapTimer = setTimeout(() => {
          _dblTapTimer = null;
          _dblTapTile  = null;
        }, 300);
      }
    }, { passive: false }); // passive:false 才能调用 preventDefault
  }

  return el;
}

/* ============================================================
   WEBSOCKET
   ============================================================ */
function connect() {
  if (!ROOM_ID || !PLAYER_ID) {
    setStatus('Missing room or player ID. Please go back to the lobby.', 'error');
    return;
  }

  setConnStatus('connecting');
  const url = `${WS_BASE}/ws/${ROOM_ID}/${PLAYER_ID}`;
  ws = new WebSocket(url);

  ws.onopen = () => {
    clearTimeout(reconnectTimer);
    setConnStatus('connected');
    setStatus('Connected. Waiting for game state…', 'info');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerMessage(msg);
    } catch (err) {
      console.error('WS parse error:', err, event.data);
    }
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
    setConnStatus('disconnected');
  };

  ws.onclose = () => {
    setConnStatus('disconnected');
    setStatus('Connection lost. Reconnecting in 2 seconds…', 'error');
    reconnectTimer = setTimeout(connect, 2000);
  };
}

function sendAction(type, data = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('Not connected to server.', 'error');
    return;
  }
  const msg = { type, ...data };
  ws.send(JSON.stringify(msg));
}

/* ============================================================
   MESSAGE HANDLERS
   ============================================================ */
function handleServerMessage(msg) {
  switch (msg.type) {
    case 'game_state':
      handleGameState(msg.state);
      break;
    case 'bao_declared':
      handleBaoDeclared(msg);
      break;
    case 'action_required':
      handleActionRequired(msg);
      break;
    case 'claim_window':
      handleClaimWindow(msg);
      break;
    case 'game_over':
      handleGameOver(msg);
      break;
    case 'error':
      setStatus('Error: ' + (msg.message || 'Unknown error'), 'error');
      break;
    case 'room_update':
      // Lobby-only broadcast; no action needed on the game page.
      break;
    default:
      console.warn('Unknown message type:', msg.type);
  }
}

function handleGameState(state) {
  // Detect any discard (by anyone, including AI) before updating gameState
  const prevState = gameState;
  gameState = state;

  // Resolve my player index from the players array
  if (myPlayerIdx === -1 && state.players) {
    myPlayerIdx = state.players.findIndex(p => p.id === PLAYER_ID);
  }

  // Show ruleset badge in topbar
  const rulesetBadge = document.getElementById('ruleset-badge');
  if (rulesetBadge && state.ruleset) {
    if (state.ruleset === 'dalian') {
      rulesetBadge.textContent = '大连穷胡';
      rulesetBadge.style.background = '#7a4a10';
      rulesetBadge.style.color = '#f0c060';
    } else {
      rulesetBadge.textContent = '港式';
      rulesetBadge.style.background = '#0d3d5e';
      rulesetBadge.style.color = '#80d0f0';
    }
    rulesetBadge.style.display = 'inline';
  }

  // Auto-close the game-over modal when another player restarts the game.
  // Without this, the modal stays visible for non-initiators after restart.
  if (state.phase !== 'ended') {
    const modal = document.getElementById('game-over-modal');
    if (modal && !modal.classList.contains('hidden')) {
      modal.classList.add('hidden');
    }
    // Reset end-of-game reveal mode so a fresh game renders normally.
    window._endReveal = false;
  } else {
    // Game ended: immediately reveal all players' tiles on the board.
    // The modal background is transparent, so the board is visible behind it.
    window._endReveal = true;
  }

  // Announce the discarded tile (covers AI discards arriving via game_state).
  // Bug fix: use 'queue' instead of default 'skip' so the tile name is not
  // silently dropped when another sound (e.g. local player's '碰！') is
  // still playing at the moment this game_state arrives.
  if (prevState && state.last_discard && state.last_discard !== prevState.last_discard) {
    if (state.last_discard !== _myDiscardSent) {
      playDiscardEffect();
      getSpeech()?.speakTile(state.last_discard, 'queue');
    }
    _myDiscardSent = null;
  }

  // Detect meld actions (碰/吃/杠) by OTHER players and announce them.
  // Local player's own actions are already announced via sendPung/sendChow/sendKong.
  if (prevState && prevState.players && state.players && myPlayerIdx >= 0) {
    state.players.forEach((player, idx) => {
      if (idx === myPlayerIdx) return;  // self: already announced on send
      const prevMelds = prevState.players[idx]?.melds || [];
      const currMelds = player.melds || [];

      if (currMelds.length > prevMelds.length) {
        // New meld appeared (pung / chow / claimed kong).
        const newMeld = currMelds[currMelds.length - 1];
        if (newMeld && newMeld.length >= 3) {
          const sound = newMeld[0] === newMeld[1]
            ? (newMeld.length >= 4 ? '杠' : '碰')
            : '吃';
          // Bug fix: if the local player had just submitted a claim action
          // (sendChow → '吃！' queued/playing) but ANOTHER player's meld
          // won instead, use 'immediate' to cancel the local '吃！' and
          // announce the actual winner's action.  Otherwise use 'queue' so
          // the sound plays naturally after the discard tile name.
          const mode = _myClaimSent ? 'immediate' : 'queue';
          if (sound === '碰') playPungEffect();
          else if (sound === '吃') playChowEffect();
          else                     playKongEffect();
          getSpeech()?.speak(sound, mode);
        }
      } else if (currMelds.length === prevMelds.length) {
        // Check for extend-pung → kong (same meld count, but one meld grew to 4)
        currMelds.forEach((meld, mi) => {
          if (prevMelds[mi] && meld.length === 4 && prevMelds[mi].length === 3) {
            playKongEffect();
            getSpeech()?.speak('杠', 'queue');
          }
        });
      }
    });
    // Clear the claim flag regardless of outcome (own claim succeeded → no other
    // player's meld was detected above; another player won → already used & reset).
    _myClaimSent = null;
  }

  // Hide claim overlay when we receive a fresh game state
  hideClaimOverlay();
  inClaimWindow = false;
  pendingActions = [];
  selectedTile = null;

  // Detect a freshly-dealt hand so we can play the dealing animation.
  // Only fires when a previous state existed and the round number ticked up
  // (covers "Play Again" restarts).  Pure reconnects (prevState=null) are
  // excluded — no need to re-animate an already-running game.
  const newRound  = state.round_number  ?? 0;
  const prevRound = prevState?.round_number ?? 0;
  const isDealEvent =
    prevState !== null &&
    state.phase !== 'ended' &&
    newRound > prevRound &&
    newRound !== _lastDealRound;

  if (isDealEvent) _lastDealRound = newRound;

  // 同步宝牌状态（重连/新局开始/规则集切换时均须同步）
  // 注：必须在 state.bao_tile==null 时也主动清空，否则大连局重开后旧宝牌继续高亮
  const newBao = state.bao_tile || null;
  if (newBao !== _baoTile) {
    _baoTile = newBao;
    updateBaoBadge(newBao);
  }
  _tenpaiPlayers = state.tenpai_players || [];

  // 新局开始（phase=drawing 且无宝牌）时重置「不看宝」选项
  if (!newBao && state.phase === 'drawing') _hideBao = false;
  updateHideBaoBtn();

  renderBoard(state);
  updateActionButtonsForState(state);

  // Fade the board back in (removes the instant-hide class set by "Play Again").
  const boardEl = document.querySelector('.board-wrapper');
  if (boardEl?.classList.contains('board-dealing')) {
    requestAnimationFrame(() => boardEl.classList.remove('board-dealing'));
  }

  // Trigger tile-by-tile deal animation after the new frame has painted.
  if (isDealEvent) {
    requestAnimationFrame(() => _triggerDealAnimation());
  }
}

function handleActionRequired(msg) {
  if (msg.player_idx === myPlayerIdx) {
    // 立即记录 pendingActions（双击出牌等逻辑依赖此值），
    // 但延迟显示操作按钮，等待上一轮 AI 动作的语音播完，
    // 使音效与界面操作在时序上保持一致（最长等 1.5 秒）。
    pendingActions = msg.actions || [];

    const showUI = () => {
      updateActionButtons(pendingActions);

      if (pendingActions.includes('discard')) {
        setStatus('Your turn — select a tile to discard.', 'info');

        // Auto-select the just-drawn tile when the server tells us which it is.
        if (msg.drawn_tile) {
          // Deselect any previous selection first.
          const prev = document.querySelector('.my-hand .tile.selected');
          if (prev) prev.classList.remove('selected');
          selectedTile = null;

          // Find the drawn tile element in the hand and select it.
          const handEl = document.getElementById('my-hand');
          if (handEl) {
            const tiles = [...handEl.querySelectorAll('.tile[data-tile]')];
            const tileEl = tiles.filter(el => el.dataset.tile === msg.drawn_tile).at(-1);
            if (tileEl) selectTile(msg.drawn_tile, tileEl);
          }
          // 不播报自己摸到的牌牌名（避免每次摸牌都念）
        }
      } else {
        setStatus('Your turn — choose an action.', 'info');
      }
    };

    const speech = getSpeech();
    if (speech && speech.isSpeaking()) {
      speech.onSilent(showUI, 1500); // 最长等 1.5 秒
    } else {
      showUI();
    }
  } else {
    pendingActions = [];
    updateActionButtons([]);
    const who = getPlayerName(msg.player_idx);
    setStatus(`Waiting for ${who}…`);
  }
}

function handleClaimWindow(msg) {
  inClaimWindow = true;
  pendingActions = msg.actions || [];

  // 声索窗口打开时，清除所有普通操作按钮（防止出牌按钮与声索窗口并存）
  updateActionButtons([]);

  showClaimOverlay(msg.tile, pendingActions, msg.timeout || 30);
  // Announce the tile available to claim
  getSpeech()?.speakTile(msg.tile);

  setStatus(`Claim opportunity: ${tileToDisplay(msg.tile).label}`);
}

/* ============================================================
   BAO (宝牌) HANDLERS — Dalian ruleset treasure tile
   ============================================================ */
function handleBaoDeclared(msg) {
  // 若 bao_tile 为 null，说明我是非听牌玩家（不应知道宝牌），忽略内容
  if (msg.bao_tile !== null && msg.bao_tile !== undefined) {
    _baoTile = msg.bao_tile;
  }

  // player_idx >= 0 且非重摇：记录首个听牌玩家
  if (msg.player_idx >= 0 && !_tenpaiPlayers.includes(msg.player_idx)) {
    _tenpaiPlayers.push(msg.player_idx);
  }

  updateBaoBadge(_baoTile);

  // new_tenpai=true：我是刚达到听牌的玩家，宝牌已存在 → 弹窗提示并语音告知
  if (msg.new_tenpai) {
    if (!_hideBao) {
      getSpeech()?.speak('看宝', 'queue');
      showBaoAnnounce(msg.player_idx, null, _baoTile, false, true);
    }
    return;
  }

  // 正常弹窗（首次揭示或换宝）
  if (!_hideBao) {
    showBaoAnnounce(msg.player_idx, msg.dice, _baoTile, msg.rerolled, false);
    getSpeech()?.speak(msg.rerolled ? '换宝！' : '看宝', 'immediate');
  }
}

function updateBaoBadge(tileStr) {
  const badge = document.getElementById('bao-badge');
  const text  = document.getElementById('bao-tile-text');
  if (!badge || !text) return;
  if (tileStr && !_hideBao) {
    const info = tileToDisplay(tileStr);
    text.textContent = info ? info.char || info.text || tileStr : tileStr;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
    text.textContent = '';
  }
}

/** 更新「看宝/不看宝」切换按钮的显示状态 */
function updateHideBaoBtn() {
  const btn = document.getElementById('btn-hide-bao');
  if (!btn) return;
  // 只在大连规则且游戏进行中显示
  const isDalian = gameState?.ruleset === 'dalian';
  const inGame   = gameState?.phase && gameState.phase !== 'waiting';
  btn.style.display = (isDalian && inGame) ? '' : 'none';
  btn.textContent   = _hideBao ? '不看宝' : '看宝';
  btn.title         = _hideBao ? '当前：不显示宝牌信息（点击切换为看宝）'
                               : '当前：显示宝牌信息（点击切换为不看宝）';
  btn.style.opacity = _hideBao ? '0.6' : '1';
}

function showBaoAnnounce(playerIdx, dice, tileStr, rerolled, newTenpai = false) {
  const el       = document.getElementById('bao-announce');
  const diceRow  = document.getElementById('bao-dice-row');
  const diceEl   = document.getElementById('bao-dice-text');
  const whoEl    = document.getElementById('bao-who-text');
  const tileEl   = document.getElementById('bao-tile-el');
  if (!el) return;

  if (newTenpai) {
    // 后续上听：宝牌已存在，告知玩家当前生效宝牌
    if (diceRow) diceRow.style.display = 'none';
    if (whoEl) whoEl.textContent = '你已上听！当前生效宝牌：';
  } else {
    if (diceRow) diceRow.style.display = '';
    if (diceEl) diceEl.textContent = dice ? '骰子点数: ' + dice : '';
    if (whoEl) {
      if (rerolled) {
        whoEl.textContent = '宝牌已被打出 3 张，重新选宝！';
      } else {
        const playerName = gameState?.players?.[playerIdx]?.id || ('玩家' + (playerIdx + 1));
        whoEl.textContent = escapeHtml(playerName) + ' 首先听牌';
      }
    }
  }

  if (tileEl) {
    tileEl.innerHTML = '';
    const t = makeTileEl(tileStr);
    t.style.width = '38px';
    t.style.height = '54px';
    tileEl.appendChild(t);
  }

  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3500);
}

function handleGameOver(msg) {
  // 游戏结束：宝牌公开揭示（若本局有宝牌，显示在 badge；结算弹窗展示）
  if (msg.bao_tile) {
    _baoTile = msg.bao_tile;
    updateBaoBadge(msg.bao_tile);
  } else {
    // 无宝牌（港式或宝牌未触发）→ 重置
    _baoTile = null;
    updateBaoBadge(null);
  }
  _tenpaiPlayers = [];

  const hasWinnerCheck = msg.winner_idx !== null && msg.winner_idx !== undefined && msg.winner_idx >= 0;
  // null + 1 = 1 in JS, so compute name only when there's actually a winner
  const winnerName = hasWinnerCheck
    ? (msg.winner_id || `Player ${msg.winner_idx + 1}`)
    : null;

  // Derive win type from win_ron flag and han breakdown.
  // win_ron: true=荣和, false=自摸, null/undefined=流局
  // Priority: 冲宝 > 摸宝 > 抢杠胡 > 杠上开花/嶺上開花 > 夹胡 > 庄家 > 自摸/点炮
  const hasWinner = hasWinnerCheck;
  let winType = null;  // null means draw (流局)
  if (hasWinner) {
    const bd = msg.han_breakdown || [];
    const has = name => bd.some(h => h.name_cn === name);
    if (has('冲宝')) {
      winType = '冲宝';
    } else if (has('摸宝')) {
      winType = '摸宝';
    } else if (has('抢杠胡')) {
      winType = '抢杠胡';
    } else if (has('杠上开花')) {
      winType = '杠上开花';
    } else if (has('嶺上開花')) {
      winType = '嶺上開花';
    } else if (has('夹胡')) {
      winType = '夹胡';
    } else if (has('庄家')) {
      winType = '庄家';
    } else if (msg.win_ron === false) {
      winType = '自摸';
    } else {
      winType = '点炮';
    }
  }

  // Don't replay sounds when reconnecting to an already-finished game.
  if (!msg.is_reconnect) {
    if (hasWinner) {
      const winTypeText = winType ? `${winType}！` : '';
      if (!_myWinSent) {
        getSpeech()?.speak(`胡！${winTypeText}`, 'immediate');
        playWinEffect();   // 程序化音效：锣 → 五声音阶 → 和弦 → 闪烁
      } else {
        // Local player already heard "胡！" — queue the win type only.
        getSpeech()?.speak(winTypeText, 'queue');
      }
    } else {
      playDrawEffect();
      getSpeech()?.speak('流局', 'immediate');
    }
  }
  _myWinSent = false;

  // Determine restart authority.
  // is_reconnect: any human who rejoins an ended room may start the next game
  //   (offline players will be replaced by AI automatically).
  // Normal end-of-game: only the NEXT dealer (or any human if dealer is AI).
  let canRestart;
  if (msg.is_reconnect) {
    canRestart = true;
  } else {
    const nextDealerIdx = msg.next_dealer_idx ?? gameState?.dealer_idx ?? 0;
    const dealerIsAI = gameState?.players?.[nextDealerIdx]?.id?.startsWith('ai_player_') ?? true;
    canRestart = myPlayerIdx === nextDealerIdx || dealerIsAI;
  }

  // chip_changes is computed by the backend at settlement time and persisted on
  // the Room, so it's correct even for reconnects (where prevChips == newChips).
  const chipChanges = msg.chip_changes || {};

  // Resolve current-round dealer player ID from dealer_idx.
  const dealerIdx = msg.dealer_idx ?? gameState?.dealer_idx ?? 0;
  const dealerId  = gameState?.players?.[dealerIdx]?.id ?? null;

  showGameOverModal(
    winnerName,
    msg.scores || {},
    msg.cumulative_scores || {},
    msg.round_number,
    msg.han_breakdown || [],
    msg.han_total || 0,
    canRestart,
    chipChanges,
    dealerId,
    winType,
    msg.bao_tile || null,         // 大连宝牌：胡牌后公开揭示
    msg.kong_log || [],           // 大连杠钱明细
    msg.kong_chip_changes || {}   // 大连各玩家杠钱专项变动
  );
  setStatus(hasWinner ? `Game over! Winner: ${winnerName}` : 'Game over! 流局 Draw', 'success');
  disableAllActionButtons();
}

/* ============================================================
   RENDER BOARD
   ============================================================ */
function renderBoard(state) {
  if (!state || !state.players) return;

  const players  = state.players;
  const discards = state.discards || [];
  const numPlayers = players.length;

  // Map positions: bottom = me, top = opposite, left/right = sides
  // Positions are relative to myPlayerIdx
  const positions = ['bottom', 'right', 'top', 'left'];

  // Render each player
  for (let i = 0; i < 4; i++) {
    const relIdx = (i - myPlayerIdx + 4) % 4;
    const pos    = positions[relIdx];
    const player = players[i];

    if (pos === 'bottom') {
      renderMyHand(player, i, state);
    } else {
      renderOpponent(player, i, pos, state, discards[i] || []);
    }
  }

  // Center table
  renderCenterTable(state, discards, players);

  // Status update for current turn (if no pending action message overrode it)
  if (pendingActions.length === 0 && !inClaimWindow) {
    const phase = state.phase || '';
    const currentTurnIdx = state.current_turn ?? -1;

    if (phase === 'waiting' || phase === 'lobby') {
      setStatus('Waiting for players. Click "Start Game" when ready.');
    } else if (currentTurnIdx === myPlayerIdx) {
      setStatus('Your turn.');
    } else {
      setStatus(`Waiting for ${getPlayerName(currentTurnIdx)}…`);
    }
  }
}

/* ---------- My Hand ---------- */
function renderMyHand(player, playerIdx, state) {
  const handEl   = document.getElementById('my-hand');
  const meldsEl  = document.getElementById('my-melds');
  const labelEl  = document.getElementById('my-label');

  if (labelEl) {
    const chips = (state.cumulative_scores || {})[player.id] ?? '–';
    const isDealer = (state.dealer_idx === playerIdx);
    const dealerBadge = isDealer ? '<span class="dealer-badge">庄</span>' : '';
    labelEl.innerHTML = `<span class="player-name">${escapeHtml(player.id)}${dealerBadge}</span>
      <span class="player-score">筹码: ${chips}</span>`;
  }

  // Render hand tiles
  handEl.innerHTML = '';
  const hand = getHandTiles(player);
  sortHandTiles(hand).forEach(tileStr => {
    const el = makeTileEl(tileStr, { clickable: true, selected: tileStr === selectedTile });
    // 宝牌高亮（不看宝模式下不高亮）
    if (_baoTile && !_hideBao && tileStr === _baoTile) {
      el.classList.add('bao-highlight');
    }
    handEl.appendChild(el);
  });

  // Render melds
  meldsEl.innerHTML = '';
  (player.melds || []).forEach(meld => {
    const group = document.createElement('span');
    group.classList.add('meld-group');
    meld.forEach(t => group.appendChild(makeTileEl(t)));
    meldsEl.appendChild(group);
  });

  // Flowers
  (player.flowers || []).forEach(t => {
    const el = makeTileEl(t);
    el.style.marginLeft = '4px';
    meldsEl.appendChild(el);
  });

  // Highlight my area if it's my turn
  const myArea = document.getElementById('area-bottom');
  if (myArea) {
    myArea.classList.toggle('active-turn', state.current_turn === playerIdx);
  }
}

/* ---------- Opponent ---------- */
function renderOpponent(player, playerIdx, position, state, discardPile) {
  const areaId = `area-${position}`;
  const area = document.getElementById(areaId);
  if (!area) return;

  area.classList.toggle('active-turn', state.current_turn === playerIdx);

  // Label
  let labelEl = area.querySelector('.player-label');
  if (!labelEl) {
    labelEl = document.createElement('div');
    labelEl.className = 'player-label';
    area.insertBefore(labelEl, area.firstChild);
  }
  const chips = (state.cumulative_scores || {})[player.id] ?? '–';
  const isDealer = (state.dealer_idx === playerIdx);
  const dealerBadge = isDealer ? '<span class="dealer-badge">庄</span>' : '';
  labelEl.innerHTML = `<span class="player-name">${escapeHtml(player.id)}${dealerBadge}</span>
    <span class="player-score">筹码: ${chips}</span>`;

  // Hand (face-down tiles)
  let handEl = area.querySelector('.opponent-hand');
  if (!handEl) {
    handEl = document.createElement('div');
    handEl.className = 'opponent-hand';
    area.appendChild(handEl);
  }
  handEl.innerHTML = '';
  const tileCount = getHandCount(player);
  for (let i = 0; i < tileCount; i++) {
    handEl.appendChild(makeTileEl('?', { faceDown: true }));
  }

  // Melds (shown face-up)
  let meldsEl = area.querySelector('.opp-melds');
  if (!meldsEl) {
    meldsEl = document.createElement('div');
    meldsEl.className = 'opp-melds';
    meldsEl.style.display = 'flex';
    meldsEl.style.flexWrap = 'wrap';
    meldsEl.style.gap = '2px';
    meldsEl.style.justifyContent = 'center';
    meldsEl.style.marginTop = '2px';
    area.appendChild(meldsEl);
  }
  meldsEl.innerHTML = '';
  (player.melds || []).forEach(meld => {
    const group = document.createElement('span');
    group.classList.add('meld-group');
    meld.forEach(t => {
      const te = makeTileEl(t);
      te.style.width  = '18px';
      te.style.height = '24px';
      te.style.fontSize = '0.55rem';
      group.appendChild(te);
    });
    meldsEl.appendChild(group);
  });
}

/* ---------- Center Table ---------- */
function renderCenterTable(state, discards, players) {
  // Wall count — guard against same-value writes.
  const wallEl = document.getElementById('wall-count');
  if (wallEl) {
    const wallTxt = String(state.wall_remaining ?? state.wall_count ?? '?');
    if (wallEl.textContent !== wallTxt) wallEl.textContent = wallTxt;
  }

  // Assign each discard pile to its spatial grid-area — ONE TIME ONLY.
  // myPlayerIdx is fixed for the entire session; re-running every frame
  // triggers repeated style recalculation and causes visual flicker.
  if (!_discardLayoutReady && myPlayerIdx >= 0) {
    const areaByRel = ['my-pile', 'right-pile', 'top-pile', 'left-pile'];
    for (let i = 0; i < 4; i++) {
      const rel = (i - myPlayerIdx + 4) % 4;
      const el  = document.getElementById(`discard-pile-${i}`);
      if (!el) continue;
      el.style.gridArea = areaByRel[rel];
      el.classList.toggle('my-discard-pile', rel === 0);
    }
    _discardLayoutReady = true;
  }

  // Discards for each player — incremental update to avoid SVG re-decode flicker.
  // Helper: compare two string arrays for equality.
  const _arrEq = (a, b) => a.length === b.length && a.every((v, k) => v === b[k]);

  for (let i = 0; i < 4; i++) {
    const pileEl = document.getElementById(`discard-pile-${i}`);
    if (!pileEl) continue;

    const pile    = (discards[i] || []);
    const visible = pile.slice(-12); // show at most last 12 tiles

    // Update the label text without touching tiles (guard against no-op writes).
    const lblText = players[i] ? players[i].id : `P${i + 1}`;
    let lbl = pileEl.querySelector('.discard-pile-label');
    if (lbl) {
      if (lbl.textContent !== lblText) lbl.textContent = lblText;
    } else {
      lbl = document.createElement('div');
      lbl.className = 'discard-pile-label';
      lbl.textContent = lblText;
      pileEl.prepend(lbl);
    }

    // Determine what tiles are currently in the DOM.
    const existingTileEls  = [...pileEl.querySelectorAll(':scope > .tile')];
    const existingKeys     = existingTileEls.map(el => el.dataset.tile);

    if (_arrEq(existingKeys, visible)) {
      // Identical — nothing to do.
    } else if (visible.length === existingKeys.length + 1 &&
               _arrEq(existingKeys, visible.slice(0, -1))) {
      // Normal discard: one tile appended at the end.
      pileEl.appendChild(makeTileEl(visible[visible.length - 1]));
    } else if (visible.length === existingKeys.length - 1 &&
               _arrEq(visible, existingKeys.slice(0, -1))) {
      // Tile was claimed (pung / chow / kong): remove the last DOM element.
      existingTileEls[existingTileEls.length - 1].remove();
    } else if (visible.length === existingKeys.length &&
               _arrEq(existingKeys.slice(1), visible.slice(0, -1))) {
      // Sliding window: pile grew past 12. Remove first element, append new last.
      existingTileEls[0].remove();
      pileEl.appendChild(makeTileEl(visible[visible.length - 1]));
    } else {
      // Full rebuild: new game or other structural change.
      pileEl.innerHTML = '';
      const rebuildLbl = document.createElement('div');
      rebuildLbl.className = 'discard-pile-label';
      rebuildLbl.textContent = lblText;
      pileEl.appendChild(rebuildLbl);
      visible.forEach(tStr => pileEl.appendChild(makeTileEl(tStr)));
    }
  }

  // Last discard highlight — update img.src in-place to avoid flash.
  // Recreating the <img> element via innerHTML causes a blank frame while
  // the browser decodes the new SVG; updating src reuses the existing element.
  const lastDiscardEl = document.getElementById('last-discard');
  if (lastDiscardEl) {
    if (state.last_discard) {
      const existingTile = lastDiscardEl.querySelector('.tile:not(.bao-in-lastdiscard)');
      if (!existingTile) {
        // First appearance — create from scratch.
        lastDiscardEl.innerHTML = 'Last: ';
        delete lastDiscardEl.dataset.baoKey;  // 清空宝牌缓存，下方重建
        lastDiscardEl.appendChild(makeTileEl(state.last_discard));
      } else if (existingTile.dataset.tile !== state.last_discard) {
        // Tile changed — update img.src in-place (no DOM reconstruction).
        const newSrc = TILE_SVG_MAP[state.last_discard];
        const img    = existingTile.querySelector('.tile-img');
        if (img && newSrc) {
          img.src = newSrc;
          img.alt = tileToDisplay(state.last_discard).label || state.last_discard;
        } else {
          // Fallback text tile (no SVG): rebuild only this element.
          lastDiscardEl.innerHTML = 'Last: ';
          delete lastDiscardEl.dataset.baoKey;
          lastDiscardEl.appendChild(makeTileEl(state.last_discard));
        }
        existingTile.dataset.tile = state.last_discard;
      }
    } else {
      if (lastDiscardEl.innerHTML !== '') {
        lastDiscardEl.innerHTML = '';
        delete lastDiscardEl.dataset.baoKey;
      }
    }

    // 大连：听牌玩家在 Last 牌旁显示当前生效宝牌（金色高亮小图样）
    // _hideBao=true 时隐藏宝牌展示（玩家选择不看宝）
    const canSeeBao = !!(state.ruleset === 'dalian' && _baoTile && !_hideBao
                         && (state.tenpai_players || []).includes(myPlayerIdx));
    const baoKey = canSeeBao ? _baoTile : '';
    if (lastDiscardEl.dataset.baoKey !== baoKey) {
      lastDiscardEl.dataset.baoKey = baoKey;
      // 移除旧的宝牌展示元素
      lastDiscardEl.querySelectorAll('.bao-in-lastdiscard, .bao-sep-in-lastdiscard')
                   .forEach(e => e.remove());
      if (canSeeBao) {
        const sep = document.createElement('span');
        sep.className = 'bao-sep-in-lastdiscard';
        sep.style.cssText = 'color:#ffd700;font-weight:bold;margin-left:10px;font-size:0.78rem;';
        sep.textContent = '宝:';
        const bt = makeTileEl(_baoTile);
        bt.classList.add('bao-in-lastdiscard', 'bao-highlight');
        bt.style.width = '22px';
        bt.style.height = '32px';
        lastDiscardEl.appendChild(sep);
        lastDiscardEl.appendChild(bt);
      }
    }
  }

  // Phase / turn info in center — guard against same-value writes.
  const phaseEl = document.getElementById('center-phase');
  if (phaseEl) {
    const phaseTxt = formatPhase(state.phase);
    if (phaseEl.textContent !== phaseTxt) phaseEl.textContent = phaseTxt;
  }
}

function formatPhase(phase) {
  if (!phase) return '';
  const map = {
    waiting: 'Waiting',
    dealing: 'Dealing',
    drawing: 'Drawing',
    discarding: 'Discarding',
    claiming: 'Claiming',
    finished: 'Finished',
    lobby: 'Lobby',
  };
  return map[phase.toLowerCase()] || phase;
}

/* ============================================================
   ACTION BUTTONS
   ============================================================ */
const ACTION_BTNS = {
  discard: 'btn-discard',
  pung:    'btn-pung',
  chow:    'btn-chow',
  kong:    'btn-kong',
  win:     'btn-win',
  skip:    'btn-skip',
  start_game: 'btn-start',
};

function updateActionButtonsForState(state) {
  const phase = (state.phase || '').toLowerCase();
  const isMyTurn = state.current_turn === myPlayerIdx;

  // Start Game button: visible in waiting/lobby phase
  setButtonVisible('btn-start', phase === 'waiting' || phase === 'lobby');

  // During normal play
  if (phase !== 'waiting' && phase !== 'lobby') {
    // Discard: my turn + discarding phase + tile selected
    const canDiscard = isMyTurn && phase === 'discarding' && !!selectedTile;
    setButtonEnabled('btn-discard', canDiscard);

    // Claim buttons hidden unless we get action_required or claim_window
    if (!inClaimWindow && pendingActions.length === 0) {
      setButtonEnabled('btn-pung', false);
      setButtonEnabled('btn-chow', false);
      setButtonEnabled('btn-kong', false);
      setButtonEnabled('btn-win',  false);
      setButtonEnabled('btn-skip', false);
    }
  }
}

function updateActionButtons(actions) {
  const actionSet = new Set(actions);

  // Discard
  const canDiscard = actionSet.has('discard') && !!selectedTile;
  setButtonEnabled('btn-discard', canDiscard);
  setButtonVisible('btn-discard', actionSet.has('discard'));

  // Claim actions
  ['pung', 'chow', 'kong', 'win', 'skip'].forEach(act => {
    setButtonEnabled(act === 'skip' ? 'btn-skip' : `btn-${act}`, actionSet.has(act));
    setButtonVisible(act === 'skip' ? 'btn-skip' : `btn-${act}`, actionSet.has(act));
  });

  // Start game hidden during active play
  setButtonVisible('btn-start', false);
}

function disableAllActionButtons() {
  Object.values(ACTION_BTNS).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = true;
  });
}

function setButtonEnabled(id, enabled) {
  const el = document.getElementById(id);
  if (el) el.disabled = !enabled;
}

function setButtonVisible(id, visible) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden', !visible);
}

/* ============================================================
   TILE SELECTION
   ============================================================ */
function selectTile(tileStr, el) {
  // Toggle selection
  if (selectedTile === tileStr) {
    selectedTile = null;
    el.classList.remove('selected');
  } else {
    // Deselect previous
    const prev = document.querySelector('.my-hand .tile.selected');
    if (prev) prev.classList.remove('selected');

    selectedTile = tileStr;
    el.classList.add('selected');
  }

  // Re-evaluate discard button
  if (gameState) {
    const phase = (gameState.phase || '').toLowerCase();
    const isMyTurn = gameState.current_turn === myPlayerIdx;
    const canDiscard = (isMyTurn && phase === 'discarding' && !!selectedTile)
                    || (pendingActions.includes('discard') && !!selectedTile);
    setButtonEnabled('btn-discard', canDiscard);
  }

  // 手机端：选中的牌自动滚动到手牌区中央，方便查看
  if (el && el.scrollIntoView) {
    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }
}

/* ============================================================
   WIN SOUND EFFECT  (Web Audio API — zero audio files)

   Four-layer procedural fanfare:
   ① Deep gong  ② Pentatonic rising arpeggio (C E G A C)
   ③ Full triumphant chord  ④ Sparkle cascade
   ============================================================ */

/* ============================================================
   SHARED AUDIO CONTEXT

   Mobile browsers (especially iOS Safari) require AudioContext
   to be created or resumed within a synchronous user gesture.
   We maintain a single shared context: initialized on first
   touch/click, kept alive, and resumed if suspended (e.g. after
   the app is backgrounded).  All SFX functions use _getAC()
   instead of creating a new context on every call.
   ============================================================ */

let _sharedAudioCtx = null;

function _getAC() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!_sharedAudioCtx) {
    try { _sharedAudioCtx = new AC(); } catch (_) { return null; }
  }
  if (_sharedAudioCtx.state === 'suspended') {
    _sharedAudioCtx.resume().catch(() => {});
  }
  return _sharedAudioCtx;
}

// Unlock the shared AudioContext on the first user gesture so that
// subsequent calls from WebSocket handlers (non-gesture) also produce sound.
if (typeof document !== 'undefined') {
  const _unlockAudio = () => _getAC();
  document.addEventListener('touchstart', _unlockAudio, { passive: true });
  document.addEventListener('click',      _unlockAudio, { passive: true });
}

/* ============================================================
   MELD SOUND EFFECTS (Web Audio API)
   ============================================================ */

function playDiscardEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const t = ctx.currentTime;
    // Short, crisp tile-on-table click (~120ms)
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.value = 300;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.18, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.12);
    o.connect(g);
    g.connect(ctx.destination);
    o.start(t);
    o.stop(t + 0.15);
  } catch (_) {}
}

function playChowEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const t = ctx.currentTime;
    // A quick rising two-note sequence (like picking up something swiftly)
    // C5 -> E5
    function beep(freq, start) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'sine';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(0.3, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, start + 0.3);
      o.connect(g);
      g.connect(ctx.destination);
      o.start(start);
      o.stop(start + 0.35);
    }
    beep(523.25, t);
    beep(659.25, t + 0.1);
  } catch (_) {}
}

function playPungEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const t = ctx.currentTime;
    // A resonant double-strike (like two tiles clacking together)
    function clack(freq, start) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'triangle';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(0.4, start + 0.01);
      g.gain.exponentialRampToValueAtTime(0.001, start + 0.25);
      o.connect(g);
      g.connect(ctx.destination);
      o.start(start);
      o.stop(start + 0.3);
    }
    clack(440, t);
    clack(440, t + 0.12);
  } catch (_) {}
}

function playKongEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const t = ctx.currentTime;
    // A heavy, powerful metallic strike (like a gong or heavy object)
    function strike(freq, start, duration, vol) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'square';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(vol, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, start + duration);
      o.connect(g);
      g.connect(ctx.destination);
      o.start(start);
      o.stop(start + duration + 0.1);
    }
    strike(220, t, 0.6, 0.4);
    strike(110, t, 0.8, 0.5);
    strike(330, t + 0.05, 0.5, 0.2); // metallic overtone
  } catch (_) {}
}

function playWinEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const master = ctx.createGain();
    master.gain.value = 0.45;
    master.connect(ctx.destination);

    const t = ctx.currentTime;

    /**
     * Play a sine oscillator with a sharp attack and exponential release.
     * @param {number} freq     Frequency in Hz
     * @param {number} start    Start time (AudioContext time)
     * @param {number} decay    Duration until gain fades to ~0
     * @param {number} peak     Peak gain (0–1)
     * @param {string} [type]   Oscillator type (default 'sine')
     */
    function osc(freq, start, decay, peak, type = 'sine') {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = type;
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, start);
      g.gain.linearRampToValueAtTime(peak, start + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, start + decay);
      o.connect(g);
      g.connect(master);
      o.start(start);
      o.stop(start + decay + 0.05);
    }

    /** Bell tone = fundamental + inharmonic overtone (classic bell ratio 2.76) */
    function bell(freq, start, decay, peak) {
      osc(freq,        start, decay,        peak);
      osc(freq * 2.76, start, decay * 0.55, peak * 0.35);
    }

    // ── ① Deep resonant gong (t = 0 s) ────────────────────────
    osc(55,  t, 3.0, 1.0);   // sub-bass rumble
    osc(110, t, 2.2, 0.75);
    osc(220, t, 1.4, 0.50);
    osc(440, t, 0.7, 0.25);

    // ── ② Rising pentatonic arpeggio (t = 0.12 – 0.60 s) ──────
    // C5 E5 G5 A5 C6  (Chinese pentatonic scale, celebratory feel)
    [523, 659, 784, 880, 1047].forEach((freq, i) => {
      bell(freq, t + 0.12 + i * 0.1, 0.85, 0.60);
    });

    // ── ③ Triumphant full chord (t = 0.85 s) ──────────────────
    [131, 165, 196, 262].forEach(f => osc(f, t + 0.85, 2.2, 0.50));   // bass
    [523, 659, 784].forEach(f => bell(f, t + 0.85, 2.0, 0.45));        // mid
    [1047, 1319, 1568].forEach(f => bell(f, t + 0.90, 1.6, 0.25));     // high

    // ── ④ Sparkle cascade (t = 0.92 – 1.28 s) ─────────────────
    [2093, 2637, 3136, 3729, 4186, 3729, 3136, 2637, 2093, 2637, 4186]
      .forEach((f, i) => osc(f, t + 0.92 + i * 0.035, 0.16, 0.18));
  } catch (_) {}
}

function playDrawEffect() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const t = ctx.currentTime;
    // Two descending tones: neutral, slightly melancholic (流局 / draw)
    function tone(freq, start, duration) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'sine';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(0.28, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, start + duration);
      o.connect(g);
      g.connect(ctx.destination);
      o.start(start);
      o.stop(start + duration + 0.05);
    }
    tone(440, t,        0.4);   // A4
    tone(330, t + 0.35, 0.5);   // E4
  } catch (_) {}
}

/* ============================================================
   SEND ACTIONS
   ============================================================ */
function sendDiscard() {
  if (!selectedTile) {
    setStatus('Please select a tile to discard.', 'error');
    return;
  }
  // Announce the tile being discarded (priority: player action)
  _myDiscardSent = selectedTile;
  playDiscardEffect();
  getSpeech()?.speakTile(selectedTile, 'immediate');
  sendAction('discard', { tile: selectedTile });
  selectedTile = null;
}

function sendPung() {
  _myClaimSent = 'pung';
  playPungEffect();
  getSpeech()?.speak('碰！', 'immediate');
  sendAction('pung');
  hideClaimOverlay();
}

function sendChow(handTiles) {
  // handTiles: optional 2-element array of the hand tiles to use.
  // When omitted (single-option path), auto-selects the only valid combo.
  const tile = document.getElementById('claim-tile-name')?.dataset?.tile;
  let chowTiles;
  if (Array.isArray(handTiles) && handTiles.length === 2) {
    chowTiles = handTiles;
  } else {
    const hand = getHandTiles(gameState?.players?.[myPlayerIdx]);
    chowTiles = autoSelectChow(tile, hand);
  }
  if (chowTiles) {
    _myClaimSent = 'chow';
    playChowEffect();
    getSpeech()?.speak('吃！', 'immediate');
    sendAction('chow', { tiles: chowTiles });
    hideClaimOverlay();
  } else {
    setStatus('Could not auto-select chow tiles. Please ensure you have the right tiles.', 'error');
  }
}

function autoSelectChow(discardedTile, hand) {
  const results = getAllChows(discardedTile, hand);
  return results.length > 0 ? results[0] : null;
}

/**
 * Return every valid chow combination for a discarded tile.
 * Each entry is a 2-element array of hand tiles needed (the third tile
 * is the discarded tile sent by the server).
 */
function getAllChows(discardedTile, hand) {
  if (!discardedTile) return [];
  const info = TILE_MAP[discardedTile];
  if (!info || !info.suit) return [];

  const num = parseInt(info.label.slice(1));
  if (isNaN(num)) return [];
  const suit = info.suit;

  // Three positions for the discarded tile in a sequence:
  //   last   (n-2, n-1, n)  → hand needs [n-2, n-1]
  //   middle (n-1, n, n+1)  → hand needs [n-1, n+1]
  //   first  (n, n+1, n+2)  → hand needs [n+1, n+2]
  const combos = [
    [num - 2, num - 1],
    [num - 1, num + 1],
    [num + 1, num + 2],
  ];

  const suitMap = { B: 'BAMBOO', C: 'CIRCLES', M: 'CHARACTERS' };
  const prefix  = suitMap[suit];
  if (!prefix) return [];

  const results = [];
  for (const combo of combos) {
    if (combo.every(n => n >= 1 && n <= 9)) {
      const needed = combo.map(n => `${prefix}_${n}`);
      const handCopy = [...hand];
      const found = needed.every(t => {
        const idx = handCopy.indexOf(t);
        if (idx !== -1) { handCopy.splice(idx, 1); return true; }
        return false;
      });
      if (found) results.push(needed);
    }
  }
  return results;
}

function sendKong() {
  if (inClaimWindow) {
    // Claiming a kong from another player's discard.
    // Server uses gs.last_discard when no tile is specified.
    _myClaimSent = 'kong';
    playKongEffect();
    getSpeech()?.speak('杠！', 'immediate');
    sendAction('kong');
    hideClaimOverlay();
    return;
  }

  // Self-drawn or extend-pung kong (discarding phase).
  // Determine which tile to kong, in priority order:
  //   1. The currently highlighted (selected) tile — only if it actually qualifies.
  //      (The auto-selected "drawn tile" may NOT be the 4-of-a-kind tile; validating
  //       it first prevents sending a wrong tile to the server when the player clicks
  //       Kong in a later turn after skipping Kong in an earlier one.)
  //   2. Extend-pung (加杠): a tile in hand that matches an existing pung meld.
  //   3. Concealed kong (暗杠): a tile appearing 4 times in hand.
  const hand  = getHandTiles(gameState?.players?.[myPlayerIdx]);
  const melds = gameState?.players?.[myPlayerIdx]?.melds || [];

  let tileToKong = null;

  // Validate selectedTile before using it: it must have 4 copies in hand (暗杠)
  // or match an existing pung meld with at least 1 copy in hand (加杠).
  if (selectedTile) {
    const selCount = hand.filter(t => t === selectedTile).length;
    const hasPungMeld = melds.some(
      m => m.length === 3 && m[0] === m[1] && m[1] === m[2] && m[0] === selectedTile
    );
    if (selCount >= 4 || (hasPungMeld && selCount >= 1)) {
      tileToKong = selectedTile;
    }
  }

  if (!tileToKong) {
    // Try extend-pung first: find a tile in hand that completes a pung meld.
    for (const meld of melds) {
      if (meld.length === 3 && meld[0] === meld[1] && meld[1] === meld[2]
          && hand.includes(meld[0])) {
        tileToKong = meld[0];
        break;
      }
    }
  }

  if (!tileToKong) {
    // Fall back to concealed kong: 4 identical tiles in hand.
    const counts = {};
    hand.forEach(t => counts[t] = (counts[t] || 0) + 1);
    tileToKong = Object.keys(counts).find(t => counts[t] >= 4) || null;
  }

  if (tileToKong) {
    playKongEffect();
    getSpeech()?.speak('杠！', 'immediate');
    sendAction('kong', { tile: tileToKong });
    // Do NOT call hideClaimOverlay() here: we are not in a claim window.
    // pendingActions must stay intact until the server responds with
    // game_state + action_required.  Calling hideClaimOverlay() would clear
    // pendingActions and leave the player with no buttons if the server
    // rejects the kong (e.g. wrong tile).
  } else {
    setStatus('Select the tile you want to Kong.', 'error');
  }
}

function sendWin() {
  _myClaimSent = 'win';
  _myWinSent = true;
  getSpeech()?.speak('胡！', 'immediate');
  playWinEffect(); // 提前播放特效，增加反馈的即时性
  sendAction('win');
  hideClaimOverlay();
}

function sendSkip() {
  sendAction('skip');
  hideClaimOverlay();
  inClaimWindow = false;
  pendingActions = [];
}

function sendStartGame() {
  sendAction('start_game');
}

/* ============================================================
   CLAIM WINDOW OVERLAY
   ============================================================ */
function showClaimOverlay(tileStr, actions, timeout) {
  // 声索窗口出现时，立即关闭宝牌弹窗（避免重叠）
  const baoEl = document.getElementById('bao-announce');
  if (baoEl) baoEl.style.display = 'none';

  const overlay  = document.getElementById('claim-overlay');
  const tileDisp = document.getElementById('claim-tile-display');
  const tileName = document.getElementById('claim-tile-name');
  const actionsEl = document.getElementById('claim-actions-btns');

  if (!overlay) return;

  // Show tile
  tileDisp.innerHTML = '';
  tileDisp.appendChild(makeTileEl(tileStr));

  // Store tile for chow
  if (tileName) {
    tileName.dataset.tile = tileStr;
    tileName.textContent  = tileToDisplay(tileStr).label;
  }

  // Build action buttons
  actionsEl.innerHTML = '';
  const actionSet = new Set(actions);

  if (actionSet.has('pung')) {
    const b = makeClaimBtn('Pung 碰', 'btn-primary', sendPung);
    actionsEl.appendChild(b);
  }
  if (actionSet.has('chow')) {
    const hand = getHandTiles(gameState?.players?.[myPlayerIdx]);
    const allChows = getAllChows(tileStr, hand);
    if (allChows.length <= 1) {
      // Zero or one option: single generic button (auto-selects the combo).
      const b = makeClaimBtn('Chow 吃', 'btn-success', sendChow);
      actionsEl.appendChild(b);
    } else {
      // Multiple options: one button per combination showing the 3-tile sequence.
      allChows.forEach(handTiles => {
        // Build sorted 3-tile sequence: hand tiles + discarded tile, order by number.
        const allThree = [...handTiles, tileStr].sort((a, b) => {
          const na = parseInt((TILE_MAP[a]?.label || '0').slice(1));
          const nb = parseInt((TILE_MAP[b]?.label || '0').slice(1));
          return na - nb;
        });
        const seqText = allThree.map(t => TILE_MAP[t]?.text || t).join('');
        const b = makeClaimBtn(`吃 ${seqText}`, 'btn-success', () => sendChow(handTiles));
        actionsEl.appendChild(b);
      });
    }
  }
  if (actionSet.has('kong')) {
    const b = makeClaimBtn('Kong 槓', 'btn-info', sendKong);
    actionsEl.appendChild(b);
  }
  if (actionSet.has('win')) {
    const b = makeClaimBtn('Win 胡!', 'btn-danger', sendWin);
    actionsEl.appendChild(b);
  }
  // Always show Skip
  const skipBtn = makeClaimBtn('Skip 過', 'btn-secondary', sendSkip);
  actionsEl.appendChild(skipBtn);

  // Start countdown — auto-skip when it reaches 0
  _startClaimCountdown(Math.floor(timeout || 30));

  overlay.classList.remove('hidden');
}

function makeClaimBtn(text, cls, handler) {
  const btn = document.createElement('button');
  btn.className = `btn ${cls}`;
  btn.textContent = text;
  btn.style.touchAction = 'manipulation'; // 消除 iOS 300ms 点击延迟
  btn.addEventListener('click', handler);
  return btn;
}

function _startClaimCountdown(seconds) {
  _clearClaimCountdown();
  _updateClaimCountdownDisplay(seconds);
  claimCountdownTimer = setInterval(() => {
    seconds -= 1;
    _updateClaimCountdownDisplay(seconds);
    if (seconds <= 0) {
      _clearClaimCountdown();
      sendSkip();
    }
  }, 1000);
}

function _clearClaimCountdown() {
  if (claimCountdownTimer !== null) {
    clearInterval(claimCountdownTimer);
    claimCountdownTimer = null;
  }
}

function _updateClaimCountdownDisplay(seconds) {
  const el = document.getElementById('claim-countdown');
  if (el) el.textContent = seconds;
  const bar = document.getElementById('claim-countdown-bar');
  if (bar) bar.classList.toggle('urgent', seconds <= 10);
}

function hideClaimOverlay() {
  const overlay = document.getElementById('claim-overlay');
  if (overlay) overlay.classList.add('hidden');
  _clearClaimCountdown();
}

/* ============================================================
   GAME OVER MODAL
   ============================================================ */
function showGameOverModal(winnerName, scores, cumulativeScores, roundNumber, hanBreakdown, hanTotal, canRestart = true, chipChanges = {}, dealerId = null, winType = null, baoTile = null, kongLog = [], kongChipChanges = {}) {
  const modal     = document.getElementById('game-over-modal');
  const winnerEl  = document.getElementById('winner-name');
  const scoresEl  = document.getElementById('scores-body');
  const roundEl   = document.getElementById('round-number-label');
  const hanSect   = document.getElementById('han-breakdown-section');
  const hanBody   = document.getElementById('han-body');
  const hanTotalEl = document.getElementById('han-total');

  if (!modal) return;

  // Winner row: show only when there is an actual winner; hide for draws.
  const winnerRowEl = winnerEl ? winnerEl.closest('.winner-name') : null;
  if (winType && winnerName) {
    winnerEl.textContent = winnerName;
    if (winnerRowEl) winnerRowEl.style.display = '';
  } else {
    if (winnerRowEl) winnerRowEl.style.display = 'none';
  }

  // Win type / draw label beneath the winner name.
  const winTypeEl = document.getElementById('win-type-label');
  if (winTypeEl) {
    if (winType) {
      const winTypeMap = {
        '自摸': '自摸 Tsumo', '点炮': '点炮 Ron',
        '嶺上開花': '嶺上開花 Lingshang', '杠上开花': '杠上开花 Kong Win',
        '冲宝': '冲宝 Chong Bao', '摸宝': '摸宝 Mo Bao',
        '抢杠胡': '抢杠胡 Rob Kong', '夹胡': '夹胡 Kanchan',
        '庄家': '庄家胡 Dealer Win',
      };
      winTypeEl.textContent = winTypeMap[winType] || winType;
      winTypeEl.style.display = '';
    } else {
      winTypeEl.textContent = '流局 Draw';
      winTypeEl.style.display = '';
    }
  }

  if (roundEl && roundNumber) {
    roundEl.textContent = `第 ${roundNumber} 局 / Round ${roundNumber}`;
  }

  // ── 大连宝牌：胡牌后公开展示 ───────────────────────────────
  const baoSection = document.getElementById('bao-result-section');
  if (baoTile && baoSection) {
    baoSection.innerHTML = '';
    const label = document.createElement('div');
    label.style.cssText = 'font-size:0.82rem;color:var(--text-muted);margin-bottom:4px;';
    label.textContent = '本局宝牌 / Treasure Tile';
    const tileWrap = document.createElement('div');
    tileWrap.style.cssText = 'display:flex;justify-content:center;margin:4px 0 8px;';
    const t = makeTileEl(baoTile);
    t.style.width = '34px'; t.style.height = '48px';
    tileWrap.appendChild(t);
    baoSection.appendChild(label);
    baoSection.appendChild(tileWrap);
    baoSection.style.display = 'block';
  } else if (baoSection) {
    baoSection.style.display = 'none';
  }

  // ── 大连杠钱明细 ────────────────────────────────────────────
  const kongSection = document.getElementById('kong-result-section');
  if (kongSection) {
    kongSection.innerHTML = '';
    const hasKongChips = Object.values(kongChipChanges).some(v => v !== 0);
    if (hasKongChips) {
      // 大连：从 kong_log 汇总各杠牌者类型和次数
      // 港式：kong_log 为空，仅展示筹码变动
      const kongerMap = {};  // player_idx → {min, an}
      (kongLog || []).forEach(k => {
        if (!kongerMap[k.player_idx]) kongerMap[k.player_idx] = { min: 0, an: 0 };
        kongerMap[k.player_idx][k.type]++;
      });

      const title = document.createElement('div');
      title.style.cssText = 'font-size:0.82rem;color:var(--text-muted);margin-bottom:4px;text-align:center;';
      title.textContent = '杠钱 / Kong Chips';
      kongSection.appendChild(title);

      const tbl = document.createElement('table');
      tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.82rem;margin-bottom:4px;';

      const players = gameState?.players || [];
      players.forEach((p, idx) => {
        const delta = kongChipChanges[p.id] ?? 0;
        if (delta === 0) return;
        const tr = document.createElement('tr');
        let detail = '';
        if (kongerMap[idx]) {
          const parts = [];
          if (kongerMap[idx].min > 0) parts.push(`明杠×${kongerMap[idx].min}`);
          if (kongerMap[idx].an  > 0) parts.push(`暗杠×${kongerMap[idx].an}`);
          detail = parts.join(' ');
        }
        const deltaStr = delta > 0 ? `+${delta}` : `${delta}`;
        const deltaClass = delta > 0 ? 'chip-gain' : 'chip-loss';
        tr.innerHTML = `<td style="padding:1px 4px">${escapeHtml(p.id)}</td>`
                     + `<td style="padding:1px 4px;color:var(--text-muted)">${escapeHtml(detail)}</td>`
                     + `<td style="padding:1px 4px;text-align:right" class="${deltaClass}">${deltaStr}</td>`;
        tbl.appendChild(tr);
      });

      kongSection.appendChild(tbl);
      kongSection.style.display = 'block';
    } else {
      kongSection.style.display = 'none';
    }
  }

  // ── Fan (Han) breakdown table ──────────────────────────────
  if (hanSect && hanBody && hanBreakdown && hanBreakdown.length > 0) {
    hanBody.innerHTML = '';
    hanBreakdown.forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${escapeHtml(item.name_cn)} <span style="color:var(--text-muted);font-size:0.8em">${escapeHtml(item.name_en)}</span></td><td>+${item.fan}</td>`;
      hanBody.appendChild(tr);
    });
    if (hanTotalEl) hanTotalEl.textContent = `${hanTotal} 番`;
    hanSect.classList.remove('hidden');
  } else if (hanSect) {
    hanSect.classList.add('hidden');
  }

  // ── Chip scores table ──────────────────────────────────────
  scoresEl.innerHTML = '';
  const allPids = Object.keys(cumulativeScores || scores);
  allPids.sort((a, b) => ((cumulativeScores || {})[b] ?? 0) - ((cumulativeScores || {})[a] ?? 0));
  allPids.forEach(pid => {
    const delta = chipChanges[pid] ?? 0;
    const deltaStr = delta > 0 ? `+${delta}` : `${delta}`;
    const deltaClass = delta > 0 ? 'chip-gain' : delta < 0 ? 'chip-loss' : 'chip-zero';
    const chips = (cumulativeScores || {})[pid] ?? '–';
    const dealerBadge = pid === dealerId ? ' <span class="dealer-badge">庄</span>' : '';
    const tr = document.createElement('tr');
    if (pid === winnerName) tr.classList.add('winner-row');
    tr.innerHTML = `<td>${escapeHtml(pid)}${dealerBadge}</td><td class="${deltaClass}">${deltaStr}</td><td>${chips}</td>`;
    scoresEl.appendChild(tr);
  });

  // Control "Play Again" button based on dealer authority.
  // Only the dealer (庄家) may restart; others see a disabled hint.
  const playAgainBtn = document.getElementById('btn-play-again');
  if (playAgainBtn) {
    if (canRestart) {
      playAgainBtn.disabled = false;
      playAgainBtn.title = '';
      playAgainBtn.textContent = 'Play Again 再来一局';
    } else {
      playAgainBtn.disabled = true;
      playAgainBtn.title = '只有庄家可以重开 / Only the dealer can restart';
      playAgainBtn.textContent = '等待庄家重开…';
    }
  }

  modal.classList.remove('hidden');
}

/* ============================================================
   STATUS BAR
   ============================================================ */
function setStatus(msg, type) {
  const bar = document.getElementById('status-bar');
  if (!bar) return;

  // Guard: skip DOM writes when content and type are identical.
  const newClass = type ? `status-bar ${type}` : 'status-bar';
  if (bar.textContent === msg && bar.className === newClass) return;

  bar.textContent = msg;
  bar.className   = 'status-bar';
  if (type) bar.classList.add(type);

  clearTimeout(statusDismissTimer);
  if (type === 'error') {
    statusDismissTimer = setTimeout(() => {
      if (bar.classList.contains('error')) {
        bar.textContent = '';
        bar.className   = 'status-bar';
      }
    }, 5000);
  }
}

function setConnStatus(state) {
  const dot  = document.getElementById('conn-dot');
  const text = document.getElementById('conn-text');
  if (!dot || !text) return;

  dot.className = 'conn-indicator ' + state;
  text.textContent = state === 'connected'    ? 'Connected'
                   : state === 'connecting'   ? 'Connecting…'
                   : 'Disconnected';
}

/* ============================================================
   HELPERS
   ============================================================ */
function getPlayerName(idx) {
  if (gameState && gameState.players && gameState.players[idx]) {
    return gameState.players[idx].id || `Player ${idx + 1}`;
  }
  return `Player ${idx + 1}`;
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ============================================================
   BOOT
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // Show room/player info in topbar
  const roomInfoEl = document.getElementById('room-info');
  if (roomInfoEl) {
    roomInfoEl.textContent = `Room: ${ROOM_ID} | Player: ${PLAYER_ID}`;
  }

  // Speech toggle button
  // 「看宝/不看宝」切换按钮
  const btnHideBao = document.getElementById('btn-hide-bao');
  if (btnHideBao) {
    btnHideBao.addEventListener('click', () => {
      _hideBao = !_hideBao;
      updateHideBaoBtn();
      updateBaoBadge(_hideBao ? null : _baoTile);
      // 重新渲染以刷新 last-discard 宝牌和手牌高亮
      if (gameState) renderBoard(gameState);
    });
  }

  const btnSpeech  = document.getElementById('btn-speech');
  const speechIcon = document.getElementById('speech-icon');
  const sp = getSpeech();
  if (btnSpeech) {
    // Sync icon with persisted state
    if (sp && !sp.isEnabled()) {
      speechIcon && (speechIcon.textContent = '🔇');
      btnSpeech.classList.add('muted');
    }
    btnSpeech.addEventListener('click', () => {
      const engine = getSpeech();
      if (!engine) return;
      if (engine.isEnabled()) {
        engine.disable();
        speechIcon && (speechIcon.textContent = '🔇');
        btnSpeech.classList.add('muted');
      } else {
        engine.enable();
        speechIcon && (speechIcon.textContent = '🔊');
        btnSpeech.classList.remove('muted');
      }
    });
  }

  // Wire up action buttons
  document.getElementById('btn-discard')?.addEventListener('click', sendDiscard);
  document.getElementById('btn-pung')   ?.addEventListener('click', sendPung);
  document.getElementById('btn-chow')   ?.addEventListener('click', sendChow);
  document.getElementById('btn-kong')   ?.addEventListener('click', sendKong);
  document.getElementById('btn-win')    ?.addEventListener('click', sendWin);
  document.getElementById('btn-skip')   ?.addEventListener('click', sendSkip);
  document.getElementById('btn-start')  ?.addEventListener('click', sendStartGame);

  // Game-over modal buttons
  document.getElementById('btn-play-again')?.addEventListener('click', () => {
    document.getElementById('game-over-modal')?.classList.add('hidden');
    // Instantly hide the board so the innerHTML re-render is invisible,
    // then let the CSS transition fade it back in with the new tiles.
    document.querySelector('.board-wrapper')?.classList.add('board-dealing');
    sendAction('restart_game');
  });
  document.getElementById('btn-back-lobby')?.addEventListener('click', () => {
    window.location.href = 'index.html';
  });
  document.getElementById('btn-close-modal')?.addEventListener('click', () => {
    document.getElementById('game-over-modal')?.classList.add('hidden');
    // Tiles are already revealed (set by handleGameState when phase=ended).
    // Force a re-render so any pending tilesKey cache gets flushed.
    if (gameState && gameState.phase === 'ended') {
      renderBoard(gameState);
    }
  });

  // Start hidden state
  ['btn-pung','btn-chow','btn-kong','btn-win','btn-skip'].forEach(id => {
    setButtonVisible(id, false);
    setButtonEnabled(id, false);
  });
  setButtonEnabled('btn-discard', false);

  // Connect WebSocket
  connect();

  // 手机端：手牌区左右滑动时阻止页面上下滚动穿透
  const myHandEl = document.getElementById('my-hand');
  if (myHandEl) {
    let touchStartX = 0;
    let touchStartY = 0;
    myHandEl.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
    }, { passive: true });
    myHandEl.addEventListener('touchmove', (e) => {
      const dx = Math.abs(e.touches[0].clientX - touchStartX);
      const dy = Math.abs(e.touches[0].clientY - touchStartY);
      // 以横向滑动为主时阻止页面纵向滚动
      if (dx > dy) {
        e.preventDefault();
      }
    }, { passive: false }); // passive:false 才能 preventDefault
  }
});

/* ============================================================
   DEALING ANIMATION + SOUND EFFECTS
   ============================================================ */

/**
 * Shuffling sound: filtered white-noise burst (~450ms) — simulates tiles
 * being mixed on a table.
 */
function _playShuffleSound() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const sr  = ctx.sampleRate;
    const len = Math.floor(sr * 0.45);
    const buf = ctx.createBuffer(1, len, sr);
    const d   = buf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      // Envelope: fast attack (10%), long decay; slight random amplitude flutter
      const t   = i / len;
      const env = t < 0.10 ? t / 0.10 : Math.pow(1 - (t - 0.10) / 0.90, 1.8);
      d[i] = (Math.random() * 2 - 1) * env * (0.6 + Math.random() * 0.4);
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    // Band-pass centred ~900 Hz to get the papery tile-shuffle timbre
    const bp  = ctx.createBiquadFilter();
    bp.type   = 'bandpass';
    bp.frequency.value = 900;
    bp.Q.value         = 1.2;
    const hp  = ctx.createBiquadFilter();
    hp.type   = 'highpass';
    hp.frequency.value = 300;
    const g   = ctx.createGain();
    g.gain.value = 0.45;
    src.connect(bp); bp.connect(hp); hp.connect(g); g.connect(ctx.destination);
    src.start();
  } catch (_) {}
}

/**
 * Single tile-place sound: short woody click/clack.
 * Noise transient + decaying sine for the resonant body.
 */
function _playTileClackSound() {
  const ctx = _getAC();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    // Noise transient (the sharp "clack" attack)
    const nLen = Math.floor(ctx.sampleRate * 0.04);
    const nBuf = ctx.createBuffer(1, nLen, ctx.sampleRate);
    const nd   = nBuf.getChannelData(0);
    for (let i = 0; i < nLen; i++) {
      nd[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / nLen, 4);
    }
    const noise = ctx.createBufferSource();
    noise.buffer = nBuf;
    // Tonal body: tile resonance (600–850 Hz, decays in ~100ms)
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(680 + Math.random() * 170, now);
    osc.frequency.exponentialRampToValueAtTime(280, now + 0.09);
    const oscG = ctx.createGain();
    oscG.gain.setValueAtTime(0.18, now);
    oscG.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
    const noiseG = ctx.createGain();
    noiseG.gain.value = 0.3;
    const master = ctx.createGain();
    master.gain.value = 0.75;
    osc.connect(oscG);   oscG.connect(master);
    noise.connect(noiseG); noiseG.connect(master);
    master.connect(ctx.destination);
    noise.start(now);
    osc.start(now); osc.stop(now + 0.13);
  } catch (_) {}
}

/**
 * Main dealing animation.  Called once per new hand, after renderBoard()
 * has painted the fresh tiles.
 *
 * Timeline:
 *   t =   0 ms  shuffle sound + TTS "发牌" + center shimmer
 *   t = 280 ms  tiles begin appearing: my hand from below, opponents
 *               from their respective directions.  Each tile is staggered
 *               by STAGGER ms with an audible clack.
 */
function _triggerDealAnimation() {
  const DELAY   = 280;  // ms before first tile appears
  const STAGGER = 68;   // ms between consecutive tiles

  // ── sounds & TTS ──────────────────────────────────────────────────────
  _playShuffleSound();
  getSpeech()?.speak('发牌', 'immediate');

  // Shimmer the center table
  const centerEl = document.querySelector('.center-table');
  if (centerEl) {
    centerEl.classList.remove('dealing-shimmer'); // reset if already set
    void centerEl.offsetWidth;                    // force reflow to restart
    centerEl.classList.add('dealing-shimmer');
    centerEl.addEventListener('animationend',
      () => centerEl.classList.remove('dealing-shimmer'), { once: true });
  }

  // ── helper: stamp one tile with animation + clack sound ───────────────
  function animTile(tile, cssClass, delayMs) {
    tile.style.animationDelay = `${delayMs}ms`;
    tile.classList.add(cssClass);
    setTimeout(_playTileClackSound, delayMs);
    tile.addEventListener('animationend', () => {
      tile.classList.remove(cssClass);
      tile.style.animationDelay = '';
    }, { once: true });
  }

  // ── my hand (slide up from below, face-up) ────────────────────────────
  const myHand = document.getElementById('my-hand');
  if (myHand) {
    [...myHand.querySelectorAll('.tile')].forEach((tile, i) =>
      animTile(tile, 'deal-in-bottom', DELAY + i * STAGGER));
  }

  // ── opponent hands (face-down tiles, from their direction) ────────────
  const oppConfig = [
    { id: 'top-hand',   cls: 'deal-in-top'   },
    { id: 'left-hand',  cls: 'deal-in-left'  },
    { id: 'right-hand', cls: 'deal-in-right' },
  ];
  oppConfig.forEach(({ id, cls }) => {
    const el = document.getElementById(id);
    if (!el) return;
    [...el.querySelectorAll('.tile-back')].forEach((tile, i) =>
      animTile(tile, cls, DELAY + 40 + i * (STAGGER - 18)));
  });
}

// Allow unit testing in Node/Vitest
if (typeof globalThis !== 'undefined' && typeof window === 'undefined') {
  const _resetSharedAC = () => { _sharedAudioCtx = null; };
  globalThis._mahjongTestExports = { getHandTiles, getHandCount, tileToDisplay, formatPhase, autoSelectChow, getAllChows, escapeHtml, TILE_MAP, sortHandTiles, TILE_SVG_MAP, makeTileEl, makeClaimBtn, selectTile, showGameOverModal, playDiscardEffect, playDrawEffect, _resetSharedAC };
}
