/* ============================================================
   game.js – Mahjong Game Board
   ============================================================ */

const API_BASE   = 'http://localhost:8000';
const WS_BASE    = 'ws://localhost:8000';

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
    el.addEventListener('click', () => selectTile(tileStr, el));
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

  // Announce the discarded tile (covers AI discards arriving via game_state)
  if (prevState && state.last_discard && state.last_discard !== prevState.last_discard) {
    getSpeech()?.speakTile(state.last_discard);
  }

  // Detect meld actions (碰/吃/杠) by OTHER players and announce them.
  // Local player's own actions are already announced via sendPung/sendChow/sendKong.
  if (prevState && prevState.players && state.players && myPlayerIdx >= 0) {
    state.players.forEach((player, idx) => {
      if (idx === myPlayerIdx) return;  // self: already announced on send
      const prevMelds = prevState.players[idx]?.melds || [];
      const currMelds = player.melds || [];

      if (currMelds.length > prevMelds.length) {
        // New meld appeared (pung / chow / claimed kong)
        const newMeld = currMelds[currMelds.length - 1];
        if (newMeld && newMeld.length >= 3) {
          if (newMeld[0] === newMeld[1]) {
            getSpeech()?.speak(newMeld.length >= 4 ? '杠' : '碰', 'queue');
          } else {
            getSpeech()?.speak('吃', 'queue');
          }
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
}

function handleActionRequired(msg) {
  if (msg.player_idx === myPlayerIdx) {
    pendingActions = msg.actions || [];
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
          // There may be duplicates; pick the last one (hand is sorted so the
          // drawn tile is usually at the end before sort, but use dataset match).
          const tiles = [...handEl.querySelectorAll('.tile[data-tile]')];
          // Select the last element matching drawn_tile (avoids duplicate ambiguity).
          const tileEl = tiles.filter(el => el.dataset.tile === msg.drawn_tile).at(-1);
          if (tileEl) selectTile(msg.drawn_tile, tileEl);
        }
        // Announce the drawn tile
        getSpeech()?.speakTile(msg.drawn_tile);
      }
    } else {
      setStatus('Your turn — choose an action.', 'info');
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
    getSpeech()?.speak('胡了！', 'immediate');
  } else {
    getSpeech()?.speak('流局', 'immediate');
  }
  showGameOverModal(
    winnerName,
    msg.scores || {},
    msg.cumulative_scores || {},
    msg.round_number,
    msg.han_breakdown || [],
    msg.han_total || 0
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
  // Wall count
  const wallEl = document.getElementById('wall-count');
  if (wallEl) wallEl.textContent = state.wall_remaining ?? state.wall_count ?? '?';

  // Discards for each player
  for (let i = 0; i < 4; i++) {
    const pileEl = document.getElementById(`discard-pile-${i}`);
    if (!pileEl) continue;

    pileEl.innerHTML = '';

    // Label
    const lbl = document.createElement('div');
    lbl.className = 'discard-pile-label';
    lbl.textContent = players[i] ? players[i].id : `P${i + 1}`;
    pileEl.appendChild(lbl);

    const pile = (discards[i] || []);
    // Show last 12 discards to avoid overflow
    const visible = pile.slice(-12);
    visible.forEach(tStr => {
      pileEl.appendChild(makeTileEl(tStr));
    });
  }

  // Last discard highlight
  const lastDiscardEl = document.getElementById('last-discard');
  if (lastDiscardEl) {
    if (state.last_discard) {
      lastDiscardEl.innerHTML = `Last: `;
      lastDiscardEl.appendChild(makeTileEl(state.last_discard));
    } else {
      lastDiscardEl.innerHTML = '';
    }
  }

  // Phase / turn info in center
  const phaseEl = document.getElementById('center-phase');
  if (phaseEl) {
    phaseEl.textContent = formatPhase(state.phase);
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
  getSpeech()?.speakTile(selectedTile, 'immediate');
  sendAction('discard', { tile: selectedTile });
  selectedTile = null;
}

function sendPung() {
  getSpeech()?.speak('碰！', 'immediate');
  sendAction('pung');
  hideClaimOverlay();
}

function sendChow() {
  // Chow requires two companion tiles; for simplicity prompt the user
  // or pick the first valid pair from hand automatically.
  // We'll show a simple UI asking which tiles to chow with.
  const tile = document.getElementById('claim-tile-name')?.dataset?.tile;
  const hand = getHandTiles(gameState?.players?.[myPlayerIdx]);

  // Try to auto-select a valid chow (adjacent tiles)
  const chowTiles = autoSelectChow(tile, hand);
  if (chowTiles) {
    getSpeech()?.speak('吃！', 'immediate');
    sendAction('chow', { tiles: chowTiles });
    hideClaimOverlay();
  } else {
    setStatus('Could not auto-select chow tiles. Please ensure you have the right tiles.', 'error');
  }
}

function autoSelectChow(discardedTile, hand) {
  if (!discardedTile) return null;
  const info = TILE_MAP[discardedTile];
  if (!info || !info.suit) return null; // only suited tiles

  const num = parseInt(info.label.slice(1));
  if (isNaN(num)) return null;
  const suit = info.suit;

  // Possible chow combinations: (n-2,n-1), (n-1,n+1), (n+1,n+2)
  const combos = [
    [num - 2, num - 1],
    [num - 1, num + 1],
    [num + 1, num + 2],
  ];

  const suitMap = { B: 'BAMBOO', C: 'CIRCLES', M: 'CHARACTERS' };
  const prefix  = suitMap[suit];
  if (!prefix) return null;

  for (const combo of combos) {
    if (combo.every(n => n >= 1 && n <= 9)) {
      const needed = combo.map(n => `${prefix}_${n}`);
      const handCopy = [...hand];
      const found = needed.every(t => {
        const idx = handCopy.indexOf(t);
        if (idx !== -1) { handCopy.splice(idx, 1); return true; }
        return false;
      });
      if (found) return needed;
    }
  }
  return null;
}

function sendKong() {
  if (inClaimWindow) {
    // Claiming a kong from another player's discard.
    // Server uses gs.last_discard when no tile is specified.
    getSpeech()?.speak('杠！', 'immediate');
    sendAction('kong');
    hideClaimOverlay();
    return;
  }
  if (selectedTile) {
    // Extend-pung or concealed kong on the selected tile.
    getSpeech()?.speak('杠！', 'immediate');
    sendAction('kong', { tile: selectedTile });
  } else if (gameState) {
    // Self-drawn kong: auto-detect a 4-of-a-kind in hand.
    const hand = getHandTiles(gameState.players?.[myPlayerIdx]);
    const counts = {};
    hand.forEach(t => counts[t] = (counts[t] || 0) + 1);
    const kongTile = Object.keys(counts).find(t => counts[t] >= 4);
    if (kongTile) {
      getSpeech()?.speak('杠！', 'immediate');
      sendAction('kong', { tile: kongTile });
    } else {
      setStatus('Select a tile for Kong.', 'error');
      return;
    }
  }
  hideClaimOverlay();
}

function sendWin() {
  getSpeech()?.speak('胡！', 'immediate');
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
    const b = makeClaimBtn('Chow 吃', 'btn-success', sendChow);
    actionsEl.appendChild(b);
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
function showGameOverModal(winnerName, scores, cumulativeScores, roundNumber, hanBreakdown, hanTotal) {
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

  modal.classList.remove('hidden');
}

/* ============================================================
   STATUS BAR
   ============================================================ */
function setStatus(msg, type) {
  const bar = document.getElementById('status-bar');
  if (!bar) return;

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
});

// Allow unit testing in Node/Vitest
if (typeof globalThis !== 'undefined' && typeof window === 'undefined') {
  globalThis._mahjongTestExports = { getHandTiles, getHandCount, tileToDisplay, formatPhase, autoSelectChow, escapeHtml, TILE_MAP, sortHandTiles, TILE_SVG_MAP };
}
