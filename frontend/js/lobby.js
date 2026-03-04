/* ============================================================
   lobby.js – Mahjong Lobby
   ============================================================ */

// 自动适配本地开发和生产环境
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? `http://${window.location.host}`
  : '';
let playerId = null;
let refreshTimer = null;

/* ---------- Initialisation ---------- */
function init() {
  playerId = localStorage.getItem('mahjong_player_id');
  if (!playerId) {
    playerId = 'p_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    localStorage.setItem('mahjong_player_id', playerId);
  }

  const pidEl = document.getElementById('player-id-display');
  if (pidEl) pidEl.textContent = playerId;

  document.getElementById('btn-create-room').addEventListener('click', createRoom);

  fetchRooms();
  refreshTimer = setInterval(fetchRooms, 3000);
}

/* ---------- Fetch & render rooms ---------- */
async function fetchRooms() {
  try {
    const res = await fetch(`${API_BASE}/api/rooms`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rooms = await res.json();
    renderRooms(rooms);
    updateRefreshTime();
  } catch (err) {
    console.error('fetchRooms error:', err);
    showTableError('Could not load rooms. Retrying…');
  }
}

function renderRooms(rooms) {
  const tbody = document.getElementById('rooms-tbody');
  tbody.innerHTML = '';

  if (!rooms || rooms.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="no-rooms">No rooms yet. Create one to get started!</td></tr>`;
    return;
  }

  rooms.forEach(room => {
    const tr = document.createElement('tr');
    const playerCount = room.player_count ?? (room.players ? room.players.length : 0);
    const maxPlayers  = room.max_players ?? 4;
    const statusClass = getStatusClass(room.status);
    const isEnded     = room.status === 'ended' || room.status === 'finished';

    // Show the current player's chip balance (if the room has cumulative scores)
    const scores = room.cumulative_scores || {};
    const myChips = scores[playerId];
    const chipsCell = myChips !== undefined
      ? `<span style="color:var(--accent);font-weight:700">${myChips}</span>`
      : '–';

    // Button: ended rooms show "Rejoin 重回" to return to game page (Play Again button is there)
    const btnLabel  = isEnded ? 'Rejoin 重回' : 'Join';
    const btnClass  = isEnded ? 'btn-secondary' : 'btn-primary';

    const rulesetLabel = room.ruleset === 'dalian'
      ? '<span style="color:#e0a050;font-weight:700">大连</span>'
      : '<span style="color:#60b8e0">港式</span>';

    tr.innerHTML = `
      <td>${escapeHtml(room.name || room.id)}</td>
      <td>${rulesetLabel}</td>
      <td>${playerCount}/${maxPlayers}</td>
      <td><span class="${statusClass}">${formatStatus(room.status)}</span></td>
      <td>${chipsCell}</td>
      <td>
        <button class="btn btn-sm ${btnClass}"
                onclick="joinRoom('${escapeAttr(room.id)}')">
          ${btnLabel}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function getStatusClass(status) {
  if (!status) return '';
  const s = status.toLowerCase();
  if (s === 'waiting')            return 'status-waiting';
  if (s === 'playing')            return 'status-playing';
  if (s === 'finished' || s === 'ended') return 'status-finished';
  return '';
}

function formatStatus(status) {
  if (!status) return 'Unknown';
  const map = {
    waiting:  'Waiting 等待中',
    playing:  'Playing 游戏中',
    finished: 'Finished 已结束',
    ended:    'Finished 已结束',
  };
  return map[status.toLowerCase()] || status;
}

function showTableError(msg) {
  const tbody = document.getElementById('rooms-tbody');
  tbody.innerHTML = `<tr><td colspan="5" class="no-rooms" style="color:#e08080;">${escapeHtml(msg)}</td></tr>`;
}

function updateRefreshTime() {
  const el = document.getElementById('refresh-time');
  if (el) el.textContent = 'Updated: ' + new Date().toLocaleTimeString();
}

/* ---------- Create room ---------- */
async function createRoom() {
  const name = prompt('Room name (optional):', '');
  if (name === null) return; // user cancelled

  const rulesetChoice = prompt(
    'Rules / 规则:\n  1 = 港式麻将 (Hong Kong)\n  2 = 大连穷胡 (Dalian Qionghu)\nEnter 1 or 2:',
    '1'
  );
  if (rulesetChoice === null) return; // user cancelled
  const ruleset = rulesetChoice.trim() === '2' ? 'dalian' : 'hk';

  try {
    // Create room
    const createRes = await fetch(`${API_BASE}/api/rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() || undefined, player_id: playerId, ruleset })
    });

    if (!createRes.ok) {
      const err = await createRes.json().catch(() => ({}));
      alert('Failed to create room: ' + (err.detail || createRes.status));
      return;
    }

    const room = await createRes.json();
    const roomId = room.id || room.room_id;

    // Join the newly created room
    await joinRoom(roomId, true);
  } catch (err) {
    console.error('createRoom error:', err);
    alert('Error creating room: ' + err.message);
  }
}

/* ---------- Join room ---------- */
async function joinRoom(roomId, skipAlert) {
  try {
    const res = await fetch(`${API_BASE}/api/rooms/${roomId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: playerId })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert('Failed to join room: ' + (err.detail || res.status));
      return;
    }

    const data = await res.json();

    // Handle redirect – server may move player to a different room
    const actualRoomId = data.room_id || roomId;
    if (!skipAlert && data.was_redirected) {
      alert(`You were moved to room: ${actualRoomId}`);
    }

    clearInterval(refreshTimer);
    window.location.href = `game.html?room=${encodeURIComponent(actualRoomId)}&player=${encodeURIComponent(playerId)}`;
  } catch (err) {
    console.error('joinRoom error:', err);
    alert('Error joining room: ' + err.message);
  }
}

/* ---------- Helpers ---------- */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  return String(str).replace(/'/g, "\\'");
}

/* ---------- Boot ---------- */
document.addEventListener('DOMContentLoaded', init);

// Allow unit testing in Node/Vitest
if (typeof globalThis !== 'undefined' && typeof window === 'undefined') {
  globalThis._lobbyTestExports = { getStatusClass, formatStatus, escapeHtml, escapeAttr };
}
