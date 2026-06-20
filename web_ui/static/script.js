// ===================================================================
//  JARVIS WEB UI — script.js
// ===================================================================

// -------------------------------------------------------------------
// State
// -------------------------------------------------------------------
const state = {
    mode: 'jarvis',
    sessionId: 'jarvis_main',
    images: [],
    isStreaming: false,
    modeMessages: { jarvis: null, coding: null },
    cmdIndex: -1,
};

// -------------------------------------------------------------------
// DOM refs
// -------------------------------------------------------------------
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const messagesEl = $('#messages');
const inputEl = $('#message-input');
const sendBtn = $('#send-btn');
const uploadBtn = $('#upload-btn');
const micBtn = $('#mic-btn');
const uploadPreview = $('#upload-preview');
const dragOverlay = $('#drag-overlay');
const modeIndicator = $('#mode-indicator');
const modelBadge = $('#model-badge');
const newChatBtn = $('#new-chat-btn');
const typingIndicator = $('#typing-indicator');
const cmdSuggestions = $('#cmd-suggestions');

// -------------------------------------------------------------------
// Particle Canvas Background
// -------------------------------------------------------------------
function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    const COUNT = 80;
    for (let i = 0; i < COUNT; i++) {
        particles.push({
            x: Math.random() * w,
            y: Math.random() * h,
            vx: (Math.random() - 0.5) * 0.3,
            vy: (Math.random() - 0.5) * 0.3,
            r: Math.random() * 2 + 0.5,
            a: Math.random() * 0.4 + 0.1,
        });
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        for (const p of particles) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0) p.x = w;
            if (p.x > w) p.x = 0;
            if (p.y < 0) p.y = h;
            if (p.y > h) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(201, 168, 76, ${p.a})`;
            ctx.fill();
        }
        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(201, 168, 76, ${0.06 * (1 - dist / 120)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(draw);
    }
    draw();
}

// -------------------------------------------------------------------
// Markdown + highlight
// -------------------------------------------------------------------
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true, gfm: true,
        highlight: (code, lang) => {
            if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang))
                try { return hljs.highlight(code, { language: lang }).value; } catch (_) {}
            return code;
        },
    });
}

// -------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------
async function apiGet(url) { const r = await fetch(url); if (r.status === 401) { window.location.href = '/login'; throw new Error('unauthorized'); } return r.json(); }
async function apiPost(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.status === 401) { window.location.href = '/login'; throw new Error('unauthorized'); }
    return r;
}
async function apiDelete(url) { const r = await fetch(url, { method: 'DELETE' }); if (r.status === 401) { window.location.href = '/login'; } }
async function uploadFile(file) {
    const fd = new FormData(); fd.append('file', file); fd.append('session_id', state.sessionId || 'default');
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    if (r.status === 401) { window.location.href = '/login'; throw new Error('unauthorized'); }
    return r.json();
}

// -------------------------------------------------------------------
// Auto-scroll
// -------------------------------------------------------------------
let autoScrollUserDisabled = false;
function scrollToBottom() {
    if (autoScrollUserDisabled) return;
    const c = document.getElementById('chat-container');
    c.scrollTop = c.scrollHeight;
}
function toggleAutoScroll() {
    if (autoScrollUserDisabled) { lockScroll(); scrollToBottom(); }
    else { unlockScroll(); }
}
function lockScroll() {
    autoScrollUserDisabled = false;
    const btn = document.getElementById('st-btn');
    if (btn) { btn.dataset.locked = 'true'; btn.textContent = '🔒'; }
}
function unlockScroll() {
    autoScrollUserDisabled = true;
    const btn = document.getElementById('st-btn');
    if (btn) { btn.dataset.locked = 'false'; btn.textContent = '🔓'; }
}
(function() {
    const container = document.getElementById('chat-container');
    if (container) {
        container.addEventListener('scroll', function() {
            if (autoScrollUserDisabled) return;
        });
    }
    const toggleBtn = document.getElementById('st-btn');
    if (toggleBtn) toggleBtn.addEventListener('click', toggleAutoScroll);
})();

// -------------------------------------------------------------------
// DOM ordering fix
// -------------------------------------------------------------------
function fixElementOrder() {
    const lastMsg = messagesEl.querySelector('.message.assistant:last-of-type');
    if (!lastMsg) return;
    let el = lastMsg.nextElementSibling;
    const stray = [];
    while (el) { stray.push(el); el = el.nextElementSibling; }
    stray.forEach(function(e) {
        if (e.classList.contains('reasoning-block') || e.classList.contains('completion-log')) {
            lastMsg.parentNode.insertBefore(e, lastMsg);
        }
    });
}

// -------------------------------------------------------------------
// Bottom status bar
// -------------------------------------------------------------------
function setBottomStatus(icon, text, tokens, elapsed) {
    const bar = document.getElementById('bottom-status');
    const iconEl = document.getElementById('bs-icon');
    const textEl = document.getElementById('bs-text');
    const tokensEl = document.getElementById('bs-tokens');
    const timeEl = document.getElementById('bs-time');
    if (!bar) return;
    bar.classList.remove('hidden');
    if (iconEl) iconEl.textContent = icon || '';
    if (textEl) textEl.textContent = text || '';
    if (tokensEl) tokensEl.textContent = tokens ? '↓ ' + tokens + 't' : '';
    if (timeEl) timeEl.textContent = elapsed ? elapsed + 's' : '';
}
function clearBottomStatus() {
    const bar = document.getElementById('bottom-status');
    if (bar) bar.classList.add('hidden');
}
let _statusTimer = null;
function startStatusTimer(startTime) {
    stopStatusTimer();
    _statusTimer = setInterval(function() {
        const elapsed = Math.round((Date.now() - startTime) / 100) / 10;
        const timeEl = document.getElementById('bs-time');
        if (timeEl) timeEl.textContent = elapsed + 's';
    }, 200);
}
function stopStatusTimer() {
    if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null; }
}

// -------------------------------------------------------------------
// Status dot
// -------------------------------------------------------------------
function setStatusDot(state) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (!dot) return;
    dot.className = 'status-dot ' + state;
    if (label) label.textContent = state === 'online' ? 'Online' : state === 'busy' ? 'Pracujem' : 'Offline';
}

// -------------------------------------------------------------------
// Command suggestions on /
// -------------------------------------------------------------------
const COMMANDS = [
    { cmd: '/help', desc: 'Zoznam všetkých príkazov' },
    { cmd: '/clear', desc: 'Vymazať aktuálny chat' },
    { cmd: '/new', desc: 'Nový chat' },
    { cmd: '/save <názov>', desc: 'Uložiť session' },
    { cmd: '/load <názov>', desc: 'Načítať session' },
    { cmd: '/list', desc: 'Zoznam uložených session' },
    { cmd: '/delete <názov>', desc: 'Vymazať session' },
    { cmd: '/compact', desc: 'Zhustiť konverzáciu' },
    { cmd: '/stats', desc: 'Štatistiky session' },
];

let _cmdFilter = '';

function showCmdSuggestions(filter) {
    _cmdFilter = filter.toLowerCase();
    if (!_cmdFilter.startsWith('/') || _cmdFilter === '/') {
        hideCmdSuggestions();
        return;
    }
    const term = _cmdFilter.slice(1);
    const matches = COMMANDS.filter(c => c.cmd.includes(term));
    if (matches.length === 0) { hideCmdSuggestions(); return; }

    cmdSuggestions.classList.remove('hidden');
    cmdSuggestions.innerHTML = '<div class="cmd-suggestion-header">💡 Príkazy</div>' +
        matches.map((c, i) =>
            `<div class="cmd-suggestion-item" data-index="${i}">
                <span class="cmd-key">${escHtml(c.cmd)}</span>
                <span class="cmd-desc">${escHtml(c.desc)}</span>
                <span class="cmd-arrow">↲</span>
            </div>`
        ).join('');

    state.cmdIndex = -1;

    // Click handler
    cmdSuggestions.querySelectorAll('.cmd-suggestion-item').forEach(item => {
        item.addEventListener('click', function() {
            const key = this.querySelector('.cmd-key').textContent;
            inputEl.value = key + ' ';
            inputEl.focus();
            hideCmdSuggestions();
        });
    });
}

function hideCmdSuggestions() {
    cmdSuggestions.classList.add('hidden');
    state.cmdIndex = -1;
}

function navigateCmdSuggestions(dir) {
    const items = cmdSuggestions.querySelectorAll('.cmd-suggestion-item');
    if (!items.length) return;

    // Remove existing highlight
    items.forEach(i => i.classList.remove('highlighted'));

    state.cmdIndex = (state.cmdIndex + dir + items.length) % items.length;
    items[state.cmdIndex].classList.add('highlighted');
    items[state.cmdIndex].scrollIntoView({ block: 'nearest' });
}

function acceptCmdSuggestion() {
    const items = cmdSuggestions.querySelectorAll('.cmd-suggestion-item');
    if (state.cmdIndex >= 0 && state.cmdIndex < items.length) {
        const key = items[state.cmdIndex].querySelector('.cmd-key').textContent;
        inputEl.value = key + ' ';
        inputEl.focus();
        hideCmdSuggestions();
        return true;
    }
    return false;
}

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') return marked.parse(text);
    return text.replace(/\n/g, '<br>');
}

function renderSafeHTML(text) {
    const raw = renderMarkdown(text);
    if (typeof DOMPurify !== 'undefined') return DOMPurify.sanitize(raw);
    return raw;  // fallback ak CDN nezbehol
}

// -------------------------------------------------------------------
// Context usage bar
// -------------------------------------------------------------------
function updateContextBar(pct, estimated, max) {
    const bar = document.getElementById('context-bar');
    const fill = document.getElementById('ctx-fill');
    const label = document.getElementById('ctx-pct');
    bar.classList.remove('hidden');
    fill.style.width = Math.min(pct, 100) + '%';
    label.textContent = pct + '%';
    fill.style.background = pct > 80 ? '#e74a4a' : pct > 60 ? '#e8c56d' : pct > 40 ? '#c9a84c' : '#6b2a3e';
    fill.title = `${estimated.toLocaleString()} / ${(max/1000).toFixed(0)}K tokens`;
}

// -------------------------------------------------------------------
// Model badge — show exact model name
// -------------------------------------------------------------------
function updateModelBadge() {
    const badge = document.getElementById('model-badge');
    if (!badge) return;
    if (state.mode === 'jarvis') {
        var m = config.jarvis_model || 'DeepSeek';
        badge.textContent = '🤖 ' + m;
    } else {
        var m = config.coding_model || 'DeepSeek';
        badge.textContent = '🧠 ' + m;
    }
}

// -------------------------------------------------------------------
// Config
// -------------------------------------------------------------------
let config = {};
apiGet('/api/config').then(c => { config = c; updateModelBadge(); });

// -------------------------------------------------------------------
// Command handler
// -------------------------------------------------------------------
async function handleCommand(text) {
    const cmd = text.trim();
    const r = await apiPost('/api/command', { command: cmd.slice(1), session_id: state.sessionId });
    const data = await r.json();
    addMessage('user', cmd);
    const bodyEl = addMessage('assistant', data.message || 'Ok.');
    bodyEl.classList.add('command-response');
    bodyEl.previousElementSibling.textContent = 'System';
    state.modeMessages[state.mode] = { html: messagesEl.innerHTML, sessionId: state.sessionId };
    return true;
}

// -------------------------------------------------------------------
// Mode switching
// -------------------------------------------------------------------
$$('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (state.isStreaming) return;
        const mode = btn.dataset.mode;
        if (mode === state.mode) return;

        state.modeMessages[state.mode] = { html: messagesEl.innerHTML, sessionId: state.sessionId };

        $$('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.mode = mode;
        state.sessionId = mode + '_main';
        state.images = [];
        updatePreview();

        const saved = state.modeMessages[mode];
        if (saved && saved.html) {
            messagesEl.innerHTML = saved.html;
            state.sessionId = saved.sessionId;
        } else {
            messagesEl.innerHTML = '';
            showWelcome();
        }
        modeIndicator.textContent = mode === 'jarvis' ? '🤖 Jarvis mód' : '💻 Coding mód';
        inputEl.placeholder = mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...';
        updateModelBadge();
        scrollToBottom();
        refreshFileList();
    });
});

// -------------------------------------------------------------------
// Message rendering
// -------------------------------------------------------------------
function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const hdr = document.createElement('div');
    hdr.className = 'message-header';
    const name = role === 'user' ? 'Fogy' : (state.mode === 'coding' ? 'DeepSeek' : 'Jarvis');
    hdr.textContent = name;
    const body = document.createElement('div');
    body.className = 'message-content';
    body.innerHTML = renderSafeHTML(content);
    div.appendChild(hdr);
    div.appendChild(body);
    messagesEl.appendChild(div);
    scrollToBottom();
    return body;
}

// -------------------------------------------------------------------
// Thinking & Reasoning
// -------------------------------------------------------------------
function addThinking() {
    // Use the dedicated typing indicator
    typingIndicator.classList.remove('hidden');
    return typingIndicator;
}

function removeThinking(el) {
    typingIndicator.classList.add('hidden');
}

const reasoningQueue = {
    _queue: [], _displaying: false, _gen: 0, _block: null,

    add(text) {
        this._queue.push(text);
        if (!this._displaying) this._process();
    },

    flush() {
        if (this._queue.length === 0 && !this._displaying) return;
        this._gen++;
        const remaining = this._queue.join('');
        this._queue = [];
        if (remaining) {
            const block = this._getBlock();
            const el = block && block.querySelector('.reasoning-content');
            if (el) el.textContent += remaining;
        }
        this._displaying = false;
    },

    _getBlock() {
        if (this._block && document.contains(this._block)) return this._block;
        const block = document.createElement('div');
        block.className = 'reasoning-block';
        block.innerHTML = `<div class="reasoning-header" onclick="
            var c = this.nextElementSibling;
            c.classList.toggle('collapsed');
            this.querySelector('.reasoning-toggle').textContent = c.classList.contains('collapsed') ? '▶' : '▼';
        ">
            <span class="reasoning-icon">🤔</span>
            <span class="reasoning-label">Rozmýšľanie</span>
            <span class="reasoning-toggle">▶</span></div>
            <div class="reasoning-content collapsed"></div>`;
        const lastMsg = messagesEl.querySelector('.message.assistant:last-of-type');
        if (lastMsg) messagesEl.insertBefore(block, lastMsg);
        else messagesEl.appendChild(block);
        this._block = block;
        return block;
    },

    reset() { this.flush(); this._block = null; },

    async _process() {
        const myGen = ++this._gen;
        this._displaying = true;
        while (this._queue.length > 0) {
            if (this._gen !== myGen) break;
            const text = this._queue.shift();
            await this._typewrite(text);
            if (this._gen !== myGen) break;
            if (this._queue.length > 0) await new Promise(r => setTimeout(r, 25));
        }
        if (this._gen === myGen) this._displaying = false;
    },

    async _typewrite(text) {
        const block = this._getBlock();
        const content = block.querySelector('.reasoning-content');
        if (!content) return;
        content.textContent += text;
    }
};

function addReasoning(text) { reasoningQueue.add(text); }

// -------------------------------------------------------------------
// Task panel
// -------------------------------------------------------------------
const taskItems = {};
function resetTaskPanel() {
    const list = document.getElementById('sidebar-task-list');
    if (list) list.innerHTML = '';
    const section = document.getElementById('sidebar-tasks');
    if (section) section.classList.add('hidden');
    window._currentCompletionLog = null;
    for (const k in taskItems) delete taskItems[k];
    const statsEl = document.getElementById('sidebar-stats');
    if (statsEl) statsEl.classList.add('hidden');
}
function addTaskStart(name, args) {
    const section = document.getElementById('sidebar-tasks');
    const list = document.getElementById('sidebar-task-list');
    if (!section || !list) return;
    section.classList.remove('hidden');
    const stepNum = list.children.length + 1;
    const displayName = args || name;
    const id = name + '_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
    taskItems[id] = { name, displayName, stepNum, status: 'running', elapsed: null };
    const row = document.createElement('div');
    row.className = 's-task-item running';
    row.id = 's-task-' + id;
    row.innerHTML = '<span class="s-task-icon">⟳</span>' +
        '<span class="s-task-name">' + stepNum + '. ' + escHtml(displayName) + '</span>' +
        '<span class="s-task-time">…</span>';
    list.appendChild(row);
    while (list.children.length > 8) list.removeChild(list.firstChild);
}
function addTaskEnd(name, elapsed) {
    const ids = Object.keys(taskItems).filter(function(id) { return taskItems[id].name === name && taskItems[id].status === 'running'; });
    if (ids.length === 0) return;
    const id = ids[ids.length - 1];
    const item = taskItems[id];
    item.status = 'done';
    item.elapsed = elapsed;
    const row = document.getElementById('s-task-' + id);
    if (!row) return;
    row.className = 's-task-item done';
    row.innerHTML = '<span class="s-task-icon">✓</span>' +
        '<span class="s-task-name">' + item.stepNum + '. ' + escHtml(item.displayName) + '</span>' +
        '<span class="s-task-time">' + elapsed + 's</span>';
    // Completion log in chat
    let log = window._currentCompletionLog;
    if (!log) {
        const lastMsg = messagesEl.querySelector('.message.assistant:last-of-type');
        if (lastMsg) {
            log = document.createElement('div');
            log.className = 'completion-log';
            const body = lastMsg.querySelector('.message-content');
            if (body) lastMsg.insertBefore(log, body.nextSibling);
            else lastMsg.appendChild(log);
            window._currentCompletionLog = log;
        }
    }
    if (log) {
        const line = document.createElement('div');
        line.className = 'completion-line';
        line.textContent = '✅ ' + item.stepNum + '. ' + item.displayName + ' (' + elapsed + 's)';
        log.appendChild(line);
    }
}
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function getFileIcon(filename) {
    var ext = filename.split('.').pop().toLowerCase();
    var icons = {
        pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
        py: '🐍', js: '📜', ts: '📘', html: '🌐', css: '🎨',
        json: '📋', xml: '📋', md: '📝', txt: '📄',
        zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
        mp4: '🎬', avi: '🎬', mkv: '🎬', mov: '🎬',
        mp3: '🎵', wav: '🎵', flac: '🎵',
        png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️',
        exe: '⚙️', dll: '🔧', bat: '📦', ps1: '📦',
    };
    return icons[ext] || '📎';
}
function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    return (bytes / 1048576).toFixed(1) + 'MB';
}

// -------------------------------------------------------------------
// Sidebar file list — categorized
// -------------------------------------------------------------------
var CATEGORY_ICONS = {
    images: '🖼️', screenshots: '📸', documents: '📄', spreadsheets: '📊',
    videos: '🎬', audio: '🎵', archives: '📦', code: '💻', other: '📎',
};
var CATEGORY_LABELS = {
    images: 'Obrázky', screenshots: 'Screenshoty', documents: 'Dokumenty', spreadsheets: 'Tabuľky',
    videos: 'Videá', audio: 'Audio', archives: 'Archívy', code: 'Kód', other: 'Ostatné',
};

async function refreshFileList() {
    var el = document.getElementById('sidebar-file-list');
    var section = document.getElementById('sidebar-files');
    if (!el || !section) return;
    try {
        var r = await fetch('/api/uploads/' + encodeURIComponent(state.sessionId));
        var data = await r.json();
        var categories = data.categories || {};
        section.classList.remove('hidden');
        var html = '';
        var catOrder = ['images', 'screenshots', 'documents', 'spreadsheets', 'videos', 'audio', 'archives', 'code', 'other'];
        for (var ci = 0; ci < catOrder.length; ci++) {
            var cat = catOrder[ci];
            var files = categories[cat] || [];
            var icon = CATEGORY_ICONS[cat] || '📎';
            var label = CATEGORY_LABELS[cat] || cat;
            if (files.length === 0) {
                html += '<div class="s-file-category empty"><span class="s-cat-icon">' + icon + '</span> ' + label + ' <span class="s-cat-empty">(prázdne)</span></div>';
                continue;
            }
            html += '<div class="s-file-category" data-cat="' + cat + '"><span class="s-cat-icon">' + icon + '</span> ' + label + ' <span class="s-toggle">▼</span></div>';
            html += '<div class="s-category-items" data-cat="' + cat + '">';
            for (var fi = 0; fi < files.length; fi++) {
                var f = files[fi];
                var fic = getFileIcon(f.filename);
                var fileUrl = '/api/uploads/' + encodeURIComponent(state.sessionId) + '/' + encodeURIComponent(f.filename);
                html += '<div class="s-file-item"><span class="s-file-icon">' + fic + '</span><a href="' + fileUrl + '" target="_blank" class="s-file-link" title="' + escHtml(f.filename) + '">' + escHtml(truncName(f.filename, 18)) + '</a><span class="s-file-size">' + formatSize(f.size) + '</span></div>';
            }
            html += '</div>';
        }
        el.innerHTML = html;

        // Click na kategorie — toggle collapse
        el.querySelectorAll('.s-file-category[data-cat]').forEach(function(header) {
            header.addEventListener('click', function() {
                var cat = this.dataset.cat;
                var items = el.querySelector('.s-category-items[data-cat="' + cat + '"]');
                if (!items) return;
                items.classList.toggle('collapsed');
                var toggle = this.querySelector('.s-toggle');
                if (toggle) toggle.textContent = items.classList.contains('collapsed') ? '▶' : '▼';
            });
        });
    } catch (_) {
        section.classList.add('hidden');
    }
}
function truncName(name, max) {
    if (name.length <= max) return name;
    var ext = name.split('.').pop();
    var base = name.slice(0, max - ext.length - 3);
    return base + '...' + ext;
}

function getFileIcon(filename) {
    var ext = filename.split('.').pop().toLowerCase();
    var icons = {
        pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
        py: '🐍', js: '📜', ts: '📘', html: '🌐', css: '🎨',
        json: '📋', xml: '📋', md: '📝', txt: '📄',
        zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
        mp4: '🎬', avi: '🎬', mkv: '🎬', mov: '🎬',
        mp3: '🎵', wav: '🎵', flac: '🎵',
        png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️',
        exe: '⚙️', dll: '🔧', bat: '📦', ps1: '📦',
    };
    return icons[ext] || '📎';
}
function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    return (bytes / 1048576).toFixed(1) + 'MB';
}

// -------------------------------------------------------------------
// Sidebar stats
// -------------------------------------------------------------------
function updateSidebarStats(promptTokens, completionTokens, elapsedSec, loopCalls) {
    const el = document.getElementById('sidebar-stats');
    const tokensEl = document.getElementById('ss-tokens');
    const timeEl = document.getElementById('ss-time');
    if (!el) return;
    el.classList.remove('hidden');
    if (tokensEl) tokensEl.textContent = `${promptTokens}↑ ${completionTokens}↓`;
    if (timeEl) timeEl.textContent = `${elapsedSec}s`;
}

function showStatus(text) {
    // No-op: old status bar not used
}
function hideStatus() {}

function removeWelcome() {
    const w = messagesEl.querySelector('.welcome-message');
    if (w) w.remove();
}

// -------------------------------------------------------------------
// sendMessage
// -------------------------------------------------------------------
async function sendMessage(text) {
    const msgText = text || inputEl.value.trim();
    if (!msgText && state.images.length === 0) return;
    if (state.isStreaming) return;

    hideCmdSuggestions();
    closeFileBrowser();

    // Handle commands
    if (msgText.startsWith('/')) {
        inputEl.value = '';
        await handleCommand(msgText);
        return;
    }

    resetTaskPanel();
    removeWelcome();
    var fileRefs = [];
    for (const img of state.images) {
        var isImage = img.media_type && img.media_type.startsWith('image/');
        if (isImage) {
            addMessage('user', '<div class="uploaded-file image"><img src="data:' + img.media_type + ';base64,' + img.data + '" alt="' + escHtml(img.filename) + '"><div class="file-label">' + escHtml(img.filename) + '</div></div>');
        } else {
            var icon = getFileIcon(img.filename);
            var fileUrl = '/api/uploads/' + encodeURIComponent(state.sessionId) + '/' + encodeURIComponent(img.filename);
            addMessage('user', '<div class="uploaded-file generic"><span class="file-icon">' + icon + '</span><a href="' + fileUrl + '" target="_blank" class="file-link">' + escHtml(img.filename) + '</a><span class="file-size">' + formatSize(img.size) + '</span></div>');
        }
        if (img.saved_path) {
            fileRefs.push(img.saved_path);
        }
    }

    // Split images vs non-image files for the API
    var apiImages = [], fileRefText = [];
    for (const f of state.images) {
        var isImage = f.media_type && f.media_type.startsWith('image/');
        if (isImage) {
            apiImages.push(f);
        }
        // Always add file path reference so AI knows where the file is on disk
        var fpath = f.relative_path || f.saved_path || ('uploads/' + state.sessionId + '/' + (f.category || 'other') + '/' + f.filename);
        fileRefText.push('[File: ' + f.filename + ' (path: ' + fpath + ')]');
    }
    var fileRefStr = fileRefText.length > 0 ? '\n' + fileRefText.join('\n') : '';
    var finalMessage = msgText + fileRefStr;

    const payload = {
        mode: state.mode,
        message: finalMessage,
        images: apiImages,
        session_id: state.sessionId,
    };

    inputEl.value = '';
    state.images = [];
    updatePreview();
    inputEl.style.height = 'auto';

    const thinkingEl = addThinking();
    reasoningQueue.reset();
    state.isStreaming = true;
    sendBtn.disabled = true;
    setStatusDot('busy');
    const msgStartTime = Date.now();
    setBottomStatus('💭', 'Rozmýšľam…', '', 0);
    startStatusTimer(msgStartTime);

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant';
    const hdr = document.createElement('div');
    hdr.className = 'message-header';
    hdr.textContent = state.mode === 'coding' ? 'DeepSeek' : 'Jarvis';
    const body = document.createElement('div');
    body.className = 'message-content stream-cursor';
    msgDiv.appendChild(hdr);
    msgDiv.appendChild(body);
    window._currentCompletionLog = null;

    try {
        const resp = await apiPost('/api/chat', payload);
        removeThinking();
        messagesEl.appendChild(msgDiv);
        scrollToBottom();

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const d = line.slice(6).trim();
                if (!d) continue;
                try {
                    const ev = JSON.parse(d);
                    if (ev.type === 'token') {
                        if (!window._streamingStarted) {
                            window._streamingStarted = true;
                            reasoningQueue.flush();
                            setBottomStatus('📝', 'Odpovedám…', '', 0);
                        }
                        streamText += ev.text;
                        body.textContent = streamText;
                        scrollToBottom();
                    } else if (ev.type === 'reasoning') {
                        addReasoning(ev.text);
                        setBottomStatus('🤔', 'Rozmýšľanie…', '', 0);
                    } else if (ev.type === 'context') {
                        updateContextBar(ev.pct, ev.estimated, ev.max);
                    } else if (ev.type === 'task_start') {
                        addTaskStart(ev.name, ev.args);
                        setBottomStatus('⚙️', ev.args || ev.name, '', 0);
                    } else if (ev.type === 'task_end') {
                        addTaskEnd(ev.name, ev.elapsed);
                    } else if (ev.type === 'stats') {
                        updateSidebarStats(ev.prompt_tokens || 0, ev.completion_tokens || 0, ev.elapsed_sec || 0, ev.loop_calls);
                    } else if (ev.type === 'status') {
                        // ignore
                    } else if (ev.type === 'error') {
                        body.textContent = streamText;
                        body.innerHTML += `<div class="error">${ev.text}</div>`;
                        body.classList.remove('stream-cursor');
                    } else if (ev.type === 'done') {
                        if (streamText) body.innerHTML = renderSafeHTML(streamText);
                        body.classList.remove('stream-cursor');
                        fixElementOrder();
                        scrollToBottom();
                        window._streamingStarted = false;
                        reasoningQueue.flush();
                        stopStatusTimer();
                        clearBottomStatus();
                    }
                } catch (_) {}
            }
        }
    } catch (err) {
        removeThinking();
        const ediv = document.createElement('div');
        ediv.className = 'message assistant';
        ediv.innerHTML = `<div class="message-header">System</div><div class="message-content"><div class="error">${escHtml(err.message)}</div></div>`;
        messagesEl.appendChild(ediv);
        window._streamingStarted = false;
        reasoningQueue.flush();
        stopStatusTimer();
        clearBottomStatus();
        resetTaskPanel();
    } finally {
        state.isStreaming = false;
        sendBtn.disabled = false;
        hideStatus();
        fixElementOrder();
        scrollToBottom();
        setStatusDot('online');
        state.modeMessages[state.mode] = { html: messagesEl.innerHTML, sessionId: state.sessionId };
        window._streamingStarted = false;
        stopStatusTimer();
        clearBottomStatus();
        // Refresh file list after message (AI may have created/modified files)
        refreshFileList();
        // Also refresh file browser if it's open
        if (fileBrowser && !fileBrowser.classList.contains('hidden') && !window._fbPollTimer) {
            refreshFileBrowser();
        }
    }
}

// -------------------------------------------------------------------
// File upload (images, music, videos, docs — all types)
// -------------------------------------------------------------------
function updatePreview() {
    if (state.images.length === 0) {
        uploadPreview.classList.add('hidden');
        uploadPreview.innerHTML = '';
        return;
    }
    uploadPreview.classList.remove('hidden');
    uploadPreview.innerHTML = state.images.map((img, i) => {
        var isImage = img.media_type && img.media_type.startsWith('image/');
        if (isImage && img.data) {
            // Uploaded image with base64 data
            return '<div class="preview-item"><img src="data:' + img.media_type + ';base64,' + img.data + '"><button class="remove-btn" data-index="' + i + '">×</button></div>';
        } else if (isImage && img.filename) {
            // Already on disk — use file URL
            var fileUrl2 = '/api/uploads/' + encodeURIComponent(state.sessionId) + '/' + encodeURIComponent(img.filename);
            return '<div class="preview-item"><img src="' + escHtml(fileUrl2) + '"><button class="remove-btn" data-index="' + i + '">×</button></div>';
        } else {
            return '<div class="preview-item file">' +
                '<span class="pfi-icon">' + getFileIcon(img.filename) + '</span>' +
                '<span class="pfi-name">' + escHtml(img.filename) + '</span>' +
                '<button class="remove-btn" data-index="' + i + '">×</button></div>';
        }
    }).join('');
    uploadPreview.querySelectorAll('.remove-btn').forEach(b => {
        b.addEventListener('click', () => { state.images.splice(parseInt(b.dataset.index), 1); updatePreview(); });
    });
}

uploadBtn.addEventListener('click', () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '*/*';  // all file types — images, music, videos, docs, code, archives
    inp.multiple = true;
    inp.addEventListener('change', async () => {
        for (const f of inp.files) {
            if (state.images.length >= 50) break;
            try {
                var uploadResult = await uploadFile(f);
                // Ensure relative_path is set on the result
                if (!uploadResult.relative_path) {
                    var ext = f.name.split('.').pop().toLowerCase();
                    // Map to server-side category
                    var cat = 'other';
                    if (['jpg','jpeg','png','gif','webp','bmp','svg','heic','heif'].includes(ext)) cat = 'images';
                    else if (['mp4','avi','mkv','mov','wmv','flv','webm'].includes(ext)) cat = 'videos';
                    else if (['mp3','wav','ogg','flac','aac','m4a','wma'].includes(ext)) cat = 'audio';
                    else if (['zip','rar','7z','tar','gz','bz2','xz'].includes(ext)) cat = 'archives';
                    else if (['pdf','txt','md','doc','docx','rtf'].includes(ext)) cat = 'documents';
                    else if (['py','js','ts','html','css','json','xml'].includes(ext)) cat = 'code';
                    uploadResult.relative_path = 'uploads/' + cat + '/' + f.name;
                }
                state.images.push(uploadResult);
            } catch (_) {}
        }
        updatePreview();
        refreshFileList();
    });
    inp.click();
});

// Drag & drop
let dragCounter = 0;
document.addEventListener('dragenter', (e) => { e.preventDefault(); dragCounter++; dragOverlay.classList.remove('hidden'); });
document.addEventListener('dragleave', (e) => { e.preventDefault(); dragCounter--; if (dragCounter <= 0) { dragCounter = 0; dragOverlay.classList.add('hidden'); } });
document.addEventListener('dragover', (e) => { e.preventDefault(); });
document.addEventListener('drop', async (e) => {
    e.preventDefault(); dragCounter = 0; dragOverlay.classList.add('hidden');
    if (state.isStreaming) return;
    for (const f of e.dataTransfer.files) {
        if (state.images.length >= 50) break;
        try { state.images.push(await uploadFile(f)); } catch (_) {}
    }
    updatePreview();
});

// -------------------------------------------------------------------
// File browser — select from previously uploaded files
// -------------------------------------------------------------------
const filesBtn = document.getElementById('files-btn');

// Hamburger menu toggle (mobile)
(function() {
    var menuToggle = document.getElementById('menu-toggle');
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    var sidebarClose = document.getElementById('sidebar-close');
    if (menuToggle && sidebar) {
        function openMenu() { sidebar.classList.add('open'); }
        function closeMenu() { sidebar.classList.remove('open'); }
        menuToggle.addEventListener('click', function(e) { e.stopPropagation(); openMenu(); });
        if (sidebarClose) sidebarClose.addEventListener('click', closeMenu);
        // Close sidebar when clicking outside (on the main area)
        document.addEventListener('click', function(e) {
            if (!sidebar.classList.contains('open')) return;
            if (!sidebar.contains(e.target) && e.target !== menuToggle && !menuToggle.contains(e.target)) {
                closeMenu();
            }
        });
    }
})();


// Camera button — MediaDevices API: otvorí kameru priamo v prehliadači
(function() {
    var camBtn = document.getElementById('camera-btn');
    var overlay = document.getElementById('camera-overlay');
    var video = document.getElementById('camera-preview');
    var canvas = document.getElementById('camera-canvas');
    var shutter = document.getElementById('camera-shutter');
    var closeBtn = document.getElementById('camera-close-btn');
    var switchBtn = document.getElementById('camera-switch');
    var flash = document.getElementById('camera-flash');
    var stream = null;
    var facingMode = 'environment';

    if (!camBtn || !overlay) return;

    function stopStream() {
        if (stream) {
            stream.getTracks().forEach(function(t) { t.stop(); });
            stream = null;
        }
        video.srcObject = null;
    }

    async function startCamera(facing) {
        stopStream();
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: facing, width: { ideal: 1920 }, height: { ideal: 1080 } },
                audio: false,
            });
            video.srcObject = stream;
            overlay.classList.remove('hidden');
            return true;
        } catch (err) {
            // Fallback: skús bez facingMode (niektoré zariadenia)
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                video.srcObject = stream;
                overlay.classList.remove('hidden');
                switchBtn.classList.add('hidden'); // nevieme prepínať
                return true;
            } catch (err2) {
                // Úplný fallback: klasický input[type=file][capture]
                var inp = document.createElement('input');
                inp.type = 'file';
                inp.accept = 'image/*';
                inp.capture = 'environment';
                inp.onchange = async function() {
                    if (inp.files.length > 0 && state.images.length < 50) {
                        try {
                            var r = await uploadFile(inp.files[0]);
                            state.images.push(r);
                            updatePreview();
                            refreshFileList();
                        } catch (_) {}
                    }
                };
                inp.click();
                return false;
            }
        }
    }

    function capturePhoto() {
        if (!stream) return;
        // Flash efekt
        flash.classList.remove('hidden');
        flash.classList.add('active');
        setTimeout(function() { flash.classList.remove('active'); flash.classList.add('hidden'); }, 150);

        var w = video.videoWidth || 1280;
        var h = video.videoHeight || 720;
        canvas.width = w;
        canvas.height = h;
        var ctx = canvas.getContext('2d');
        // Flip if front camera
        if (facingMode === 'user') {
            ctx.translate(w, 0);
            ctx.scale(-1, 1);
        }
        ctx.drawImage(video, 0, 0);
        canvas.toBlob(async function(blob) {
            if (!blob) return;
            var filename = 'camera_' + Date.now() + '.jpg';
            var file = new File([blob], filename, { type: 'image/jpeg' });
            if (state.images.length < 50) {
                try {
                    var uploadResult = await uploadFile(file);
                    state.images.push(uploadResult);
                    updatePreview();
                    refreshFileList();
                } catch (_) {}
            }
        }, 'image/jpeg', 0.92);
    }

    function stopCamera() {
        stopStream();
        overlay.classList.add('hidden');
    }

    // Event listeners
    camBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        startCamera(facingMode);
    });

    shutter.addEventListener('click', capturePhoto);
    closeBtn.addEventListener('click', stopCamera);

    // Prepínanie predná/zadná kamera
    switchBtn.addEventListener('click', function() {
        facingMode = (facingMode === 'environment') ? 'user' : 'environment';
        startCamera(facingMode);
    });

    // Keyboard: Enter/space = fotka, Escape = zavrieť
    document.addEventListener('keydown', function(e) {
        if (overlay.classList.contains('hidden')) return;
        if (e.key === 'Escape') { stopCamera(); e.preventDefault(); }
        else if (e.key === 'Enter' || (e.key === ' ' && e.target === document.body)) {
            capturePhoto();
            e.preventDefault();
        }
    });
})();


// 



const fileBrowser = document.getElementById('file-browser');
const fbList = document.getElementById('fb-list');
const fbClose = document.getElementById('fb-close');

async function openFileBrowser() {
    if (!fileBrowser || !fbList) return;
    // Show immediately so refreshFileBrowser knows it's open
    fileBrowser.classList.remove('hidden');
    await refreshFileBrowser();
    // Start polling every 5 seconds
    if (window._fbPollTimer) { clearInterval(window._fbPollTimer); }
    window._fbPollTimer = setInterval(refreshFileBrowser, 5000);
}
function closeFileBrowser() {
    if (fileBrowser) fileBrowser.classList.add('hidden');
    // Stop polling
    if (window._fbPollTimer) { clearInterval(window._fbPollTimer); window._fbPollTimer = null; }
}

async function refreshFileBrowser() {
    if (!fileBrowser || fileBrowser.classList.contains('hidden')) return;
    var previewEl = document.getElementById('fb-preview');
    try {
        // Save expanded state before rebuilding HTML
        var expandedCats = {};
        fbList.querySelectorAll('.fb-category-items[data-cat]').forEach(function(el) {
            expandedCats[el.dataset.cat] = !el.classList.contains('collapsed');
        });

        var r = await fetch('/api/uploads/' + encodeURIComponent(state.sessionId));
        var data = await r.json();
        var categories = data.categories || {};

        var html = '';
        var catOrder = ['images', 'screenshots', 'documents', 'spreadsheets', 'videos', 'audio', 'archives', 'code', 'other'];
        for (var ci = 0; ci < catOrder.length; ci++) {
            var cat = catOrder[ci];
            var files = categories[cat] || [];
            var catIcon = CATEGORY_ICONS[cat] || '📎';
            var catLabel = CATEGORY_LABELS[cat] || cat;

            if (files.length === 0) {
                html += '<div class="fb-category-header empty">' + catIcon + ' ' + catLabel + ' <span class="fb-cat-empty">(prázdne)</span></div>';
                continue;
            }

            // Restore expanded state if previously open
            var wasExpanded = expandedCats[cat];
            var collapsedClass = wasExpanded ? '' : ' collapsed';
            var toggleArrow = wasExpanded ? '▼' : '▶';

            html += '<div class="fb-category-header" data-cat="' + cat + '">' + catIcon + ' ' + catLabel + ' <span class="fb-toggle">' + toggleArrow + '</span></div>';
            html += '<div class="fb-category-items' + collapsedClass + '" data-cat="' + cat + '">';
            for (var fi = 0; fi < files.length; fi++) {
                var f = files[fi];
                var icon = getFileIcon(f.filename);
                var isImg = f.filename.match(/\.(png|jpg|jpeg|gif|svg|webp)$/i);
                var fileUrl = '/api/uploads/' + encodeURIComponent(state.sessionId) + '/' + encodeURIComponent(f.filename);
                var relPath = f.relative_path || (cat + '/' + f.filename);
                html += '<div class="fb-item' + (isImg ? ' fb-img-item' : '') + '" data-filename="' + escHtml(f.filename) + '" data-isimg="' + (isImg ? '1' : '0') + '" data-fileurl="' + escHtml(fileUrl) + '" data-category="' + cat + '" data-relpath="' + escHtml(relPath) + '">' +
                    (isImg ? '<img class="fb-thumb" src="' + escHtml(fileUrl) + '" loading="lazy">' : '<span class="fb-icon">' + icon + '</span>') +
                    '<span class="fb-name">' + escHtml(f.filename) + '</span>' +
                    '<span class="fb-size">' + formatSize(f.size) + '</span>' +
                    '</div>';
            }
            html += '</div>';
        }
        fbList.innerHTML = html;
        if (previewEl) previewEl.classList.add('hidden');

        // Click na kategorie — toggle collapse
        fbList.querySelectorAll('.fb-category-header[data-cat]').forEach(function(header) {
            header.addEventListener('click', function(e) {
                var cat2 = this.dataset.cat;
                var items = fbList.querySelector('.fb-category-items[data-cat="' + cat2 + '"]');
                if (!items) return;
                items.classList.toggle('collapsed');
                var toggle = this.querySelector('.fb-toggle');
                if (toggle) toggle.textContent = items.classList.contains('collapsed') ? '▶' : '▼';
            });
        });

        // Click na subor — zobraz preview alebo pripoj k sprave
        fbList.querySelectorAll('.fb-item').forEach(function(item) {
            item.addEventListener('click', function(e) {
                e.stopPropagation();
                var fname = this.dataset.filename;
                var isImg = this.dataset.isimg === '1';
                var furl = this.dataset.fileurl;
                var relPath = this.dataset.relpath || (this.dataset.category + '/' + fname);
                var cat = this.dataset.category;

                // Attach to message — add to state.images + show preview with X button above input
                var existing = state.images.find(function(img) {
                    return img.filename === fname;
                });
                if (!existing) {
                    state.images.push({
                        data: '',
                        media_type: isImg ? 'image/jpeg' : 'application/octet-stream',
                        filename: fname,
                        saved_path: 'uploads/' + relPath,
                        relative_path: relPath,
                        size: 0,
                    });
                }
                updatePreview();

                // Close file browser on mobile after selection
                if (window.innerWidth <= 768) {
                    closeFileBrowser();
                }
            });
        });
    } catch (e) { fbList.innerHTML = '<div class="fb-error">Chyba načítania</div>'; }
}

if (filesBtn) filesBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    if (fileBrowser && !fileBrowser.classList.contains('hidden')) {
        closeFileBrowser();
    } else {
        openFileBrowser();
    }
});
if (fbClose) fbClose.addEventListener('click', closeFileBrowser);
// Refresh button
var fbRefresh = document.getElementById('fb-refresh');
if (fbRefresh) {
    fbRefresh.addEventListener('click', function(e) {
        e.stopPropagation();
        this.classList.add('spinning');
        refreshFileBrowser().then(function() {
            fbRefresh.classList.remove('spinning');
        }).catch(function() {
            fbRefresh.classList.remove('spinning');
        });
    });
}
// Close file browser on click outside
document.addEventListener('click', function(e) {
    if (fileBrowser && !fileBrowser.classList.contains('hidden') &&
        !fileBrowser.contains(e.target) && e.target !== filesBtn && !filesBtn.contains(e.target)) {
        closeFileBrowser();
    }
});

// -------------------------------------------------------------------
// Voice / Mic — AudioContext capture + WAV → server transcribe
// -------------------------------------------------------------------
let _micRec = false;
let _micGen = 0;
let _micStream = null;
let _micCtx = null;
let _micNode = null;
let _micPcm = [];

/** Encode Float32 PCM samples as a 16-bit mono WAV Blob */
function _pcmToWav(samples, sampleRate) {
    var len = samples.length;
    var buf = new ArrayBuffer(44 + len * 2);
    var v = new DataView(buf);
    function w(off, str) { for (var i = 0; i < str.length; i++) v.setUint8(off + i, str.charCodeAt(i)); }
    w(0, 'RIFF');
    v.setUint32(4, 36 + len * 2, true);
    w(8, 'WAVE');
    w(12, 'fmt ');
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);          // PCM
    v.setUint16(22, 1, true);          // mono
    v.setUint32(24, sampleRate, true);
    v.setUint32(28, sampleRate * 2, true); // byte rate
    v.setUint16(32, 2, true);          // block align
    v.setUint16(34, 16, true);         // bits per sample
    w(36, 'data');
    v.setUint32(40, len * 2, true);
    for (var i = 0; i < len; i++) {
        var s = Math.max(-1, Math.min(1, samples[i]));
        v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Blob([buf], { type: 'audio/wav' });
}

micBtn.addEventListener('click', function() {
    console.log('[Mic] ⬇️ klik, _micRec:', _micRec, 'isStreaming:', state.isStreaming);
    if (state.isStreaming) return;

    // --- STOP ---
    if (_micRec) {
        console.log('[Mic] ⏹ stop recording');

        // Stop capture and null vars immediately (race-safe for quick re-start)
        if (_micNode) { _micNode.disconnect(); _micNode = null; }
        var oldCtx = _micCtx; _micCtx = null;
        var oldStream = _micStream; _micStream = null;
        var sampleRate = oldCtx ? oldCtx.sampleRate : 16000;
        if (oldCtx) oldCtx.close().catch(function(){});
        if (oldStream) oldStream.getTracks().forEach(function(t) { t.stop(); });

        _micRec = false;
        micBtn.classList.remove('listening');
        inputEl.placeholder = '🎤 Prepisujem…';

        var pcm = _micPcm;
        _micPcm = [];

        if (pcm.length < 1000) {
            console.log('[Mic] ❌ príliš krátka nahrávka');
            inputEl.placeholder = '🎤 Nahrávka je príliš krátka';
            setTimeout(function() { inputEl.placeholder = state.mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...'; }, 2000);
            return;
        }

        // Encode WAV and send to server
        console.log('[Mic] 🎵 kódujem WAV, vzorky:', pcm.length, 'sampleRate:', sampleRate);
        var wavBlob = _pcmToWav(pcm, sampleRate);
        console.log('[Mic] 🎵 WAV blob:', wavBlob.size, 'bytes');

        var fd = new FormData();
        fd.append('audio', wavBlob, 'recording.wav');
        micBtn.title = '⏳';
        var gen = _micGen;

        fetch('/api/transcribe', { method: 'POST', body: fd })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (_micGen !== gen) return;
                micBtn.title = '🎤 Hlasový vstup';
                if (data.text) {
                    console.log('[Mic] ✅ prepis:', JSON.stringify(data.text));
                    inputEl.value = data.text;
                    inputEl.dispatchEvent(new Event('input'));
                    sendMessage();
                } else if (data.error) {
                    console.log('[Mic] ❌ chyba:', data.error);
                    inputEl.placeholder = '❌ ' + data.error;
                    setTimeout(function() { inputEl.placeholder = state.mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...'; }, 3000);
                } else {
                    console.log('[Mic] ❌ prázdny prepis');
                    inputEl.placeholder = '🎤 Nič nerozpoznané, skús znova';
                    setTimeout(function() { inputEl.placeholder = state.mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...'; }, 2000);
                }
            })
            .catch(function(err) {
                if (_micGen !== gen) return;
                console.log('[Mic] ❌ fetch error:', err.message);
                micBtn.title = '🎤 Hlasový vstup';
                inputEl.placeholder = '❌ ' + err.message;
                setTimeout(function() { inputEl.placeholder = state.mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...'; }, 3000);
            });
        return;
    }

    // --- START ---
    console.log('[Mic] ▶️ start recording');
    inputEl.placeholder = '🎤 Povoľ mikrofón…';
    ++_micGen;

    navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream) {
        console.log('[Mic] ✅ stream získaný, ID:', stream.id);
        _micStream = stream;
        _micPcm = [];

        var actx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        _micCtx = actx;

        var src = actx.createMediaStreamSource(stream);
        var node = actx.createScriptProcessor(4096, 1, 1);
        _micNode = node;

        node.onaudioprocess = function(ev) {
            if (!_micRec) return; // stopped
            var ch = ev.inputBuffer.getChannelData(0);
            for (var i = 0; i < ch.length; i++) {
                _micPcm.push(ch[i]);
            }
        };

        src.connect(node);
        // Connect to a gain=0 node so onaudioprocess fires without feedback
        var dummy = actx.createGain();
        dummy.gain.value = 0;
        node.connect(dummy);
        dummy.connect(actx.destination);

        _micRec = true;
        micBtn.classList.add('listening');
        micBtn.title = '⏹ Zastaviť';
        inputEl.placeholder = '🎤 Nahrávam… hovor';

        console.log('[Mic] ✅ nahrávanie spustené, sampleRate:', actx.sampleRate);
    }).catch(function(err) {
        console.log('[Mic] ❌ getUserMedia zlyhalo:', err.name, err.message);
        inputEl.placeholder = '❌ Mikrofón: ' + err.name;
        setTimeout(function() { inputEl.placeholder = state.mode === 'jarvis' ? 'Správa pre Jarvisa...' : 'Sem píš kód alebo príkaz...'; }, 3000);
    });
});

// -------------------------------------------------------------------
// Input events
// -------------------------------------------------------------------
inputEl.addEventListener('keydown', (e) => {
    // Command suggestions navigation
    if (!cmdSuggestions.classList.contains('hidden')) {
        if (e.key === 'ArrowDown') { e.preventDefault(); navigateCmdSuggestions(1); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); navigateCmdSuggestions(-1); return; }
        if (e.key === 'Tab' || e.key === 'Enter') {
            if (state.cmdIndex >= 0) {
                e.preventDefault();
                if (acceptCmdSuggestion()) return;
            }
        }
        if (e.key === 'Escape') { hideCmdSuggestions(); return; }
    }

    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 150) + 'px';
    // Show command suggestions
    showCmdSuggestions(inputEl.value);
});

inputEl.addEventListener('blur', () => {
    // Hide suggestions on blur with delay so click can register
    setTimeout(hideCmdSuggestions, 200);
});

sendBtn.addEventListener('click', () => sendMessage());

// -------------------------------------------------------------------
// New chat
// -------------------------------------------------------------------
newChatBtn.addEventListener('click', () => {
    if (state.isStreaming) return;
    state.modeMessages[state.mode] = { html: messagesEl.innerHTML, sessionId: state.sessionId };
    messagesEl.innerHTML = '';
    state.sessionId = state.mode + '_' + Date.now();
    resetTaskPanel();
    showWelcome();
    refreshHistoryList();
    refreshFileList();
});

// -------------------------------------------------------------------
// Session history sidebar
// -------------------------------------------------------------------
async function refreshHistoryList() {
    const list = document.getElementById('history-list');
    if (!list) return;
    try {
        const resp = await apiGet('/api/sessions');
        const sessions = resp.sessions || [];
        // Filter out auto sessions without display name, keep only named ones
        const named = sessions.filter(s => !s.id.startsWith('_'));
        if (named.length === 0) {
            list.innerHTML = '<div class="history-empty">💬 Žiadne staré chaty</div>';
            return;
        }
        list.innerHTML = named.map(s => {
            const date = s.modified ? new Date(s.modified) : new Date(0);
            const timeStr = date.toLocaleDateString('sk-SK', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            const msgCount = s.messages || '?';
            return `<div class="history-item" data-id="${escHtml(s.id)}">
                <span class="history-icon">💬</span>
                <span class="history-name">${escHtml(s.name)}</span>
                <span class="history-time">${timeStr}</span>
                <span class="history-del" data-del="${escHtml(s.id)}">✕</span>
            </div>`;
        }).join('');

        // Click to load
        list.querySelectorAll('.history-item').forEach(item => {
            item.addEventListener('click', function(e) {
                if (e.target.classList.contains('history-del')) return;
                const id = this.dataset.id;
                loadSession(id);
            });
        });
        // Delete
        list.querySelectorAll('.history-del').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const id = this.dataset.del;
                await apiDelete(`/api/sessions/${encodeURIComponent(id)}`);
                refreshHistoryList();
            });
        });
    } catch (_) {
        list.innerHTML = '<div class="history-empty">⚠️ História nedostupná</div>';
    }
}

async function loadSession(id, historyData) {
    if (state.isStreaming) return;
    try {
        let history = historyData;
        if (!history) {
            const resp = await fetch(`/api/sessions/${encodeURIComponent(id)}`);
            const data = await resp.json();
            history = data.history;
        }
        if (history) {
            state.sessionId = id;
            messagesEl.innerHTML = '';
            removeWelcome();
            for (const msg of history) {
                const role = msg.role === 'user' ? 'user' : 'assistant';
                addMessage(role, msg.content || '');
            }
            state.modeMessages[state.mode] = { html: messagesEl.innerHTML, sessionId: id };
            updateModelBadge();
            scrollToBottom();
            refreshFileList();
        }
    } catch (_) {}
}

// -------------------------------------------------------------------
// Welcome
// -------------------------------------------------------------------
function showWelcome() {
    const isJ = state.mode === 'jarvis';
    const chips = isJ
        ? [
            { icon: '📊', text: 'Stav systému', prompt: 'Jarvis, aký je stav systému?' },
            { icon: '🚀', text: 'Spusti Discord', prompt: 'Jarvis, spusti Discord' },
            { icon: '📰', text: 'Novinky', prompt: 'Jarvis, prečítaj novinky' },
            { icon: '💾', text: 'Disk', prompt: 'Jarvis, aké mám voľné miesto na disku?' },
          ]
        : [
            { icon: '🐍', text: 'Python kód', prompt: 'Napíš Python kalkulačku' },
            { icon: '🔧', text: 'Vytvor súbor', prompt: 'vytvor súbor hello.py s programom a spusti ho' },
            { icon: '📁', text: 'Zoznam súborov', prompt: 'vypíš všetky súbory v D:/JARVIS' },
            { icon: '💻', text: 'Stav PC', prompt: 'aký je stav systému?' },
          ];

    messagesEl.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">⚡</div>
            <div class="welcome-title">${isJ ? 'Jarvis' : 'Coding'} je online</div>
            <div class="welcome-sub">Ako ti môžem pomôcť, Fogy? 👋</div>
            <div class="welcome-suggestions">
                ${chips.map(ch => `<button class="suggestion-chip" data-t="${escHtml(ch.prompt)}">${ch.icon} ${escHtml(ch.text)}</button>`).join('')}
            </div>
        </div>`;
    messagesEl.querySelectorAll('[data-t]').forEach(b => {
        b.addEventListener('click', () => { inputEl.value = b.dataset.t; inputEl.focus(); inputEl.dispatchEvent(new Event('input')); });
    });
}

// -------------------------------------------------------------------
// Init
// -------------------------------------------------------------------
initParticles();
updateModelBadge();
showWelcome();
refreshHistoryList();
refreshFileList();
// Try to load last session
fetch('/api/sessions/last').then(r => r.json()).then(data => {
    if (data.status === 'loaded' && data.history && data.history.length > 0) {
        loadSession(data.id, data.history);
    }
}).catch(() => {});
inputEl.focus();
setStatusDot('online');
console.log('⚡ Jarvis Web UI ready');
