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

// Double-tap detection for mobile (touchend-based, shared across all hand tiles).
let _dblTapTimer = null;
let _dblTapTile  = null;

// Discard pile spatial layout: set once after myPlayerIdx is known, never again.
// Running on every game_state causes repeated style recalculations and flicker.
let _discardLayoutReady = false;

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

  // Auto-close the game-over modal when another player restarts the game.
  // Without this, the modal stays visible for non-initiators after restart.
  if (state.phase !== 'ended') {
    const modal = document.getElementById('game-over-modal');
    if (modal && !modal.classList.contains('hidden')) {
      modal.classList.add('hidden');
    }
  }

  // Announce the discarded tile (covers AI discards arriving via game_state).
  // Bug fix: use 'queue' instead of default 'skip' so the tile name is not
  // silently dropped when another sound (e.g. local player's '碰！') is
  // still playing at the moment this game_state arrives.
  if (prevState && state.last_discard && state.last_discard !== prevState.last_discard) {
    getSpeech()?.speakTile(state.last_discard, 'queue');
  }

  // Detect meld actions (碰/吃/杠) by ALL players and announce them.
  if (prevState && prevState.players && state.players && myPlayerIdx >= 0) {
    state.players.forEach((player, idx) => {
      const prevMelds = prevState.players[idx]?.melds || [];
      const currMelds = player.melds || [];

      if (currMelds.length > prevMelds.length) {
        // New meld appeared (pung / chow / claimed kong).
        const newMeld = currMelds[currMelds.length - 1];
        if (newMeld && newMeld.length >= 3) {
          const sound = newMeld[0] === newMeld[1]
            ? (newMeld.length >= 4 ? '杠' : '碰')
            : '吃';
          getSpeech()?.speak(sound, 'queue');
        }
      } else if (currMelds.length === prevMelds.length) {
        // Check for extend-pung → kong (same meld count, but one meld grew to 4)
        currMelds.forEach((meld, mi) => {
          if (prevMelds[mi] && meld.length === 4 && prevMelds[mi].length === 3) {
            getSpeech()?.speak('杠', 'queue');
          }
        });
      }
    });
  }

  // Hide claim overlay when we receive a fresh game state
  hideClaimOverlay();
  inClaimWindow = false;
  pendingActions = [];
  selectedTile = null;

  renderBoard(state);
  updateActionButtonsForState(state);

  // If the board was hidden for a new-game deal transition, fade it back in now.
  // requestAnimationFrame ensures the render has painted before we start the transition.
  const boardEl = document.querySelector('.board-wrapper');
  if (boardEl?.classList.contains('board-dealing')) {
    requestAnimationFrame(() => {
      boardEl.classList.remove('board-dealing'); // CSS transition: opacity 0 → 1
    });
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

  showClaimOverlay(msg.tile, pendingActions, msg.timeout || 30);
  // Announce the tile available to claim
  getSpeech()?.speakTile(msg.tile);

  setStatus(`Claim opportunity: ${tileToDisplay(msg.tile).label}`);
}

function handleGameOver(msg) {
  const winnerName = msg.winner_id || `Player ${msg.winner_idx + 1}`;
  // Announce win or draw
  if (msg.winner_idx !== null && msg.winner_idx !== undefined && msg.winner_idx >= 0) {
    getSpeech()?.speak('胡！', 'immediate');
    playWinEffect();   // 程序化音效：锣 → 五声音阶 → 和弦 → 闪烁
  } else {
    getSpeech()?.speak('流局', 'immediate');
  }

  // Determine restart authority: only the dealer (庄家) may click "Play Again".
  // If the dealer seat is occupied by an AI, any human player may restart
  // (since the AI won't act).  Single-player sessions always allow restart.
  const dealerIdx = gameState?.dealer_idx ?? 0;
  const dealerIsAI = gameState?.players?.[dealerIdx]?.id?.startsWith('ai_player_') ?? true;
  const canRestart = myPlayerIdx === dealerIdx || dealerIsAI;

  showGameOverModal(
    winnerName,
    msg.scores || {},
    msg.cumulative_scores || {},
    msg.round_number,
    msg.han_breakdown || [],
    msg.han_total || 0,
    canRestart
  );
  setStatus(`Game over! Winner: ${winnerName}`, 'success');
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
      const existingTile = lastDiscardEl.querySelector('.tile');
      if (!existingTile) {
        // First appearance — create from scratch.
        lastDiscardEl.innerHTML = 'Last: ';
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
          lastDiscardEl.appendChild(makeTileEl(state.last_discard));
        }
        existingTile.dataset.tile = state.last_discard;
      }
    } else {
      if (lastDiscardEl.innerHTML !== '') lastDiscardEl.innerHTML = '';
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
function playWinEffect() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  let ctx;
  try { ctx = new AC(); } catch (_) { return; }

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

  // Auto-close AudioContext when the effect has finished
  setTimeout(() => { try { ctx.close(); } catch (_) {} }, 4800);
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
  sendAction('discard', { tile: selectedTile });
  selectedTile = null;
}

function sendPung() {
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
    sendAction('kong');
    hideClaimOverlay();
    return;
  }

  // Self-drawn or extend-pung kong (discarding phase).
  // Determine which tile to kong, in priority order:
  //   1. The currently highlighted (selected) tile.
  //   2. Extend-pung (加杠): a tile in hand that matches an existing pung meld.
  //   3. Concealed kong (暗杠): a tile appearing 4 times in hand.
  const hand  = getHandTiles(gameState?.players?.[myPlayerIdx]);
  const melds = gameState?.players?.[myPlayerIdx]?.melds || [];

  let tileToKong = selectedTile || null;

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
function showGameOverModal(winnerName, scores, cumulativeScores, roundNumber, hanBreakdown, hanTotal, canRestart = true) {
  const modal     = document.getElementById('game-over-modal');
  const winnerEl  = document.getElementById('winner-name');
  const scoresEl  = document.getElementById('scores-body');
  const roundEl   = document.getElementById('round-number-label');
  const hanSect   = document.getElementById('han-breakdown-section');
  const hanBody   = document.getElementById('han-body');
  const hanTotalEl = document.getElementById('han-total');

  if (!modal) return;

  winnerEl.textContent = winnerName;

  if (roundEl && roundNumber) {
    roundEl.textContent = `第 ${roundNumber} 局 / Round ${roundNumber}`;
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
    const roundScore = scores[pid] ?? 0;
    const chips = (cumulativeScores || {})[pid] ?? '–';
    const tr = document.createElement('tr');
    if (pid === winnerName) tr.classList.add('winner-row');
    tr.innerHTML = `<td>${escapeHtml(pid)}</td><td>${roundScore}</td><td>${chips}</td>`;
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

// Allow unit testing in Node/Vitest
if (typeof globalThis !== 'undefined' && typeof window === 'undefined') {
  globalThis._mahjongTestExports = { getHandTiles, getHandCount, tileToDisplay, formatPhase, autoSelectChow, getAllChows, escapeHtml, TILE_MAP, sortHandTiles, TILE_SVG_MAP, makeTileEl, makeClaimBtn, selectTile, showGameOverModal };
}
