/* ============================================================
   lobby.js – Mahjong Lobby
   ============================================================ */

const API_BASE = 'http://localhost:8000';
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
    tbody.innerHTML = `<tr><td colspan="4" class="no-rooms">No rooms yet. Create one to get started!</td></tr>`;
    return;
  }

  rooms.forEach(room => {
    const tr = document.createElement('tr');
    const playerCount = room.player_count ?? (room.players ? room.players.length : 0);
    const maxPlayers = room.max_players ?? 4;
    const statusClass = getStatusClass(room.status);

    tr.innerHTML = `
      <td>${escapeHtml(room.name || room.id)}</td>
      <td>${playerCount}/${maxPlayers}</td>
      <td><span class="${statusClass}">${formatStatus(room.status)}</span></td>
      <td>
        <button class="btn btn-sm btn-primary"
                onclick="joinRoom('${escapeAttr(room.id)}')"
                ${room.status === 'finished' ? 'disabled' : ''}>
          Join
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function getStatusClass(status) {
  if (!status) return '';
  const s = status.toLowerCase();
  if (s === 'waiting')  return 'status-waiting';
  if (s === 'playing')  return 'status-playing';
  if (s === 'finished') return 'status-finished';
  return '';
}

function formatStatus(status) {
  if (!status) return 'Unknown';
  const map = { waiting: 'Waiting', playing: 'Playing', finished: 'Finished' };
  return map[status.toLowerCase()] || status;
}

function showTableError(msg) {
  const tbody = document.getElementById('rooms-tbody');
  tbody.innerHTML = `<tr><td colspan="4" class="no-rooms" style="color:#e08080;">${escapeHtml(msg)}</td></tr>`;
}

function updateRefreshTime() {
  const el = document.getElementById('refresh-time');
  if (el) el.textContent = 'Updated: ' + new Date().toLocaleTimeString();
}

/* ---------- Create room ---------- */
async function createRoom() {
  const name = prompt('Room name (optional):', '') ;
  if (name === null) return; // user cancelled

  try {
    // Create room
    const createRes = await fetch(`${API_BASE}/api/rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() || undefined, player_id: playerId })
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
