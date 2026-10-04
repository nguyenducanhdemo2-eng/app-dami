const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const state = {results: [], query: '', queue: [], status: null, polling: null};

async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = {...(options.headers || {})};
  if (options.body && typeof options.body !== 'string') {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  if (!['GET', 'HEAD'].includes(method.toUpperCase())) headers['X-CSRF-Token'] = csrfToken;
  const response = await fetch(path, {...options, method, headers});
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (response.status === 401) {
    throw new Error(data.detail || 'Yêu cầu không được cấp quyền.');
  }
  if (!response.ok) throw new Error(data.detail || `Yêu cầu thất bại (HTTP ${response.status}).`);
  return data;
}

function showAlert(message, type = 'danger') {
  const box = document.querySelector('#global-alert');
  box.textContent = message;
  box.className = `alert ${type}`;
  window.scrollTo({top: 0, behavior: 'smooth'});
  clearTimeout(showAlert.timer);
  showAlert.timer = setTimeout(() => box.classList.add('hidden'), 6500);
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString('vi-VN');
}

function truncate(value, max = 180) {
  const text = value || '';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function statusLabel(status) {
  return ({draft: 'Bản nháp', approved: 'Đã duyệt', sending: 'Đang gửi', sent: 'Đã gửi', failed: 'Lỗi', skipped: 'Đã bỏ qua'})[status] || status;
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === `tab-${name}`));
  if (name === 'queue') loadQueue();
  if (name === 'history') loadHistory();
}

document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));

async function loadStatus() {
  try {
    const data = await api('/api/status');
    state.status = data;
    const account = data.account;
    const pill = document.querySelector('#connection-pill');
    pill.textContent = account ? `@${account.username}` : 'Chưa kết nối Threads';
    pill.className = `pill ${account ? 'success' : 'danger'}`;
    document.querySelector('#metric-account').textContent = account ? `@${account.username}` : 'Chưa kết nối';
    document.querySelector('#metric-daily').textContent = `${data.sent_today} / ${data.max_daily_replies}`;
    document.querySelector('#config-callback').textContent = data.redirect_uri || 'Chưa có APP_BASE_URL';
    document.querySelector('#config-delay').textContent = `${data.send_delay_seconds} giây`;
    document.querySelector('#account-details').innerHTML = '';
    if (account) {
      const strong = document.createElement('strong');
      strong.textContent = `@${account.username}`;
      const info = document.createElement('div');
      info.className = 'muted small-text';
      info.textContent = `User ID: ${account.threads_user_id} · Token hết hạn: ${formatDate(account.expires_at)}`;
      document.querySelector('#account-details').append(strong, info);
    } else {
      document.querySelector('#account-details').textContent = 'Chưa kết nối tài khoản Threads thật.';
    }
    document.querySelector('#refresh-token-btn').disabled = !account;
    document.querySelector('#disconnect-btn').disabled = !account;
    document.querySelector('#oauth-connect').classList.toggle('disabled', !data.configured);
    const warnings = document.querySelector('#config-warnings');
    warnings.innerHTML = '';
    data.warnings.forEach(message => {
      const div = document.createElement('div');
      div.className = 'alert warning';
      div.textContent = message;
      warnings.appendChild(div);
    });
    updateJob(data.job);
  } catch (error) {
    showAlert(error.message);
  }
}

document.querySelector('#search-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = 'Đang lấy dữ liệu thật…';
  try {
    const payload = {
      q: document.querySelector('#search-query').value.trim(),
      search_type: document.querySelector('#search-type').value,
      search_mode: document.querySelector('#search-mode').value,
      limit: Number(document.querySelector('#search-limit').value)
    };
    const data = await api('/api/search', {method: 'POST', body: payload});
    state.results = data.data;
    state.query = data.query;
    renderResults();
    showAlert(`Đã nhận ${data.data.length} kết quả trực tiếp từ Threads.`, 'success');
  } catch (error) {
    showAlert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Tìm trên Threads';
  }
});

function renderResults() {
  const list = document.querySelector('#search-results');
  const empty = document.querySelector('#search-empty');
  const template = document.querySelector('#result-template');
  list.innerHTML = '';
  empty.classList.toggle('hidden', state.results.length > 0);
  document.querySelector('#results-title').textContent = state.results.length ? `${state.results.length} bài cho “${state.query}”` : 'Không có kết quả';
  state.results.forEach((item, index) => {
    const node = template.content.cloneNode(true);
    const article = node.querySelector('.result-item');
    article.dataset.index = index;
    const checkbox = node.querySelector('.result-check');
    checkbox.disabled = Boolean(item.queue_status);
    checkbox.addEventListener('change', () => {
      article.classList.toggle('selected', checkbox.checked);
      syncResultActions();
    });
    node.querySelector('.result-user').textContent = item.username ? `@${item.username}` : 'Không rõ tài khoản';
    node.querySelector('.result-time').textContent = formatDate(item.timestamp);
    node.querySelector('.score').textContent = `Tiềm năng ${item.lead_score}/100`;
    node.querySelector('.result-text').textContent = item.text || '(Bài không có văn bản)';
    const link = node.querySelector('.result-link');
    link.href = item.permalink || '#';
    link.classList.toggle('hidden', !item.permalink);
    const status = node.querySelector('.result-status');
    status.textContent = item.queue_status ? statusLabel(item.queue_status) : 'Mới';
    status.className = `result-status ${item.queue_status ? `status-${item.queue_status}` : ''}`;
    list.appendChild(node);
  });
  document.querySelector('#select-all-btn').disabled = state.results.length === 0;
  syncResultActions();
}

function selectedResults() {
  return [...document.querySelectorAll('.result-item .result-check:checked')].map(input => state.results[Number(input.closest('.result-item').dataset.index)]);
}

function syncResultActions() {
  const selected = selectedResults();
  document.querySelector('#add-queue-btn').disabled = selected.length === 0;
  document.querySelector('#add-queue-btn').textContent = selected.length ? `Thêm ${selected.length} bài vào hàng chờ` : 'Thêm vào hàng chờ';
}

document.querySelector('#select-all-btn').addEventListener('click', () => {
  const checks = [...document.querySelectorAll('.result-check:not(:disabled)')];
  const shouldSelect = !checks.some(check => check.checked);
  checks.forEach((check, index) => {
    check.checked = shouldSelect && index < window.DAMI_CONFIG.maxBatch;
    check.closest('.result-item').classList.toggle('selected', check.checked);
  });
  syncResultActions();
});

document.querySelector('#add-queue-btn').addEventListener('click', async () => {
  const selected = selectedResults().slice(0, window.DAMI_CONFIG.maxBatch);
  if (!selected.length) return;
  try {
    await api('/api/queue', {
      method: 'POST',
      body: {
        items: selected.map(item => ({id: item.id, username: item.username, text: item.text, permalink: item.permalink})),
        template: document.querySelector('#reply-template').value,
        keyword: state.query
      }
    });
    state.results.forEach(item => {
      if (selected.some(chosen => chosen.id === item.id)) item.queue_status = 'draft';
    });
    renderResults();
    await loadQueue();
    showAlert(`Đã tạo ${selected.length} bản nháp. Hãy kiểm tra và duyệt trước khi gửi.`, 'success');
    switchTab('queue');
  } catch (error) { showAlert(error.message); }
});

async function loadQueue() {
  try {
    const data = await api('/api/queue');
    state.queue = data.data;
    renderQueue();
  } catch (error) { showAlert(error.message); }
}

function renderQueue() {
  const list = document.querySelector('#queue-list');
  const empty = document.querySelector('#queue-empty');
  list.innerHTML = '';
  empty.classList.toggle('hidden', state.queue.length > 0);
  document.querySelector('#queue-count').textContent = state.queue.length;
  state.queue.forEach(item => {
    const article = document.createElement('article');
    article.className = 'queue-item';
    article.dataset.id = item.id;

    const head = document.createElement('div');
    head.className = 'queue-head';
    const source = document.createElement('div');
    const user = document.createElement('strong');
    user.textContent = item.target_username ? `@${item.target_username}` : 'Không rõ tài khoản';
    const text = document.createElement('p');
    text.className = 'queue-source';
    text.textContent = truncate(item.target_text, 240);
    source.append(user, text);
    const badge = document.createElement('span');
    badge.className = `status-badge status-${item.status}`;
    badge.textContent = statusLabel(item.status);
    head.append(source, badge);

    const label = document.createElement('label');
    label.textContent = 'Bình luận sẽ gửi';
    const textarea = document.createElement('textarea');
    textarea.value = item.reply_text;
    textarea.maxLength = 500;
    textarea.rows = 4;
    textarea.disabled = ['sending', 'sent'].includes(item.status);
    label.appendChild(textarea);

    const actions = document.createElement('div');
    actions.className = 'queue-actions';
    if (!['sending', 'sent'].includes(item.status)) {
      actions.append(
        actionButton('Lưu bản nháp', 'ghost', () => saveQueueItem(item.id, textarea.value)),
        actionButton(item.status === 'approved' ? 'Đã duyệt ✓' : 'Duyệt bình luận', 'secondary', async () => {
          await saveQueueItem(item.id, textarea.value, false);
          await api(`/api/queue/${item.id}/approve`, {method: 'POST'});
          await loadQueue();
          showAlert('Đã duyệt bình luận.', 'success');
        }),
        actionButton('Xóa', 'danger', async () => {
          await api(`/api/queue/${item.id}`, {method: 'DELETE'});
          await loadQueue();
        })
      );
    }
    if (item.permalink) {
      const link = document.createElement('a');
      link.className = 'button ghost small-button';
      link.href = item.permalink;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'Xem bài gốc ↗';
      actions.appendChild(link);
    }
    article.append(head, label);
    if (item.error) {
      const error = document.createElement('div');
      error.className = 'queue-error';
      error.textContent = item.error;
      article.appendChild(error);
    }
    article.appendChild(actions);
    list.appendChild(article);
  });
}

function actionButton(text, kind, handler) {
  const button = document.createElement('button');
  button.className = `button ${kind} small-button`;
  button.textContent = text;
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await handler(); } catch (error) { showAlert(error.message); }
    finally { button.disabled = false; }
  });
  return button;
}

async function saveQueueItem(id, replyText, notify = true) {
  await api(`/api/queue/${id}/edit`, {method: 'POST', body: {reply_text: replyText}});
  await loadQueue();
  if (notify) showAlert('Đã lưu bản nháp.', 'success');
}

document.querySelector('#refresh-queue-btn').addEventListener('click', loadQueue);
document.querySelector('#send-approved-btn').addEventListener('click', async () => {
  const ids = state.queue.filter(item => item.status === 'approved').map(item => item.id);
  if (!ids.length) return showAlert('Hãy duyệt ít nhất một bình luận trước khi gửi.', 'warning');
  try {
    await api('/api/queue/send', {method: 'POST', body: {ids}});
    showAlert(`Đã bắt đầu gửi ${ids.length} bình luận qua Threads API.`, 'success');
    beginJobPolling();
  } catch (error) { showAlert(error.message); }
});

document.querySelector('#stop-send-btn').addEventListener('click', async () => {
  try { await api('/api/queue/stop', {method: 'POST'}); } catch (error) { showAlert(error.message); }
});

function updateJob(job) {
  const box = document.querySelector('#job-box');
  const isVisible = job.running || job.completed > 0;
  box.classList.toggle('hidden', !isVisible);
  const percent = job.total ? Math.round((job.completed / job.total) * 100) : 0;
  document.querySelector('#job-progress').style.width = `${percent}%`;
  document.querySelector('#job-message').textContent = job.message;
  document.querySelector('#job-counts').textContent = `${job.completed}/${job.total} · Thành công ${job.sent} · Lỗi ${job.failed}`;
  document.querySelector('#stop-send-btn').classList.toggle('hidden', !job.running);
  document.querySelector('#send-approved-btn').disabled = job.running;
}

function beginJobPolling() {
  clearInterval(state.polling);
  state.polling = setInterval(async () => {
    try {
      const data = await api('/api/job');
      updateJob(data.job);
      await loadQueue();
      if (!data.job.running) {
        clearInterval(state.polling);
        state.polling = null;
        await Promise.all([loadStatus(), loadHistory()]);
        showAlert(data.job.message, data.job.failed ? 'warning' : 'success');
      }
    } catch (error) {
      clearInterval(state.polling);
      showAlert(error.message);
    }
  }, 2000);
}

async function loadHistory() {
  try {
    const data = await api('/api/history');
    const body = document.querySelector('#history-body');
    body.innerHTML = '';
    document.querySelector('#history-empty').classList.toggle('hidden', data.data.length > 0);
    data.data.forEach(item => {
      const row = document.createElement('tr');
      const statusCell = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = `status-badge status-${item.status}`;
      badge.textContent = statusLabel(item.status);
      statusCell.appendChild(badge);
      const user = document.createElement('td'); user.textContent = item.target_username ? `@${item.target_username}` : '—';
      const copy = document.createElement('td');
      const copyInner = document.createElement('div'); copyInner.className = 'clip'; copyInner.textContent = item.reply_text; copy.appendChild(copyInner);
      const date = document.createElement('td'); date.textContent = formatDate(item.sent_at || item.updated_at);
      const linkCell = document.createElement('td');
      if (item.permalink) {
        const link = document.createElement('a'); link.href = item.permalink; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Mở ↗'; linkCell.appendChild(link);
      } else linkCell.textContent = '—';
      row.append(statusCell, user, copy, date, linkCell);
      body.appendChild(row);
    });
  } catch (error) { showAlert(error.message); }
}

document.querySelector('#refresh-history-btn').addEventListener('click', loadHistory);
document.querySelector('#token-form').addEventListener('submit', async event => {
  event.preventDefault();
  const token = document.querySelector('#manual-token').value.trim();
  try {
    await api('/api/threads/connect-token', {method: 'POST', body: {access_token: token, expires_in: 5184000}});
    event.currentTarget.reset();
    await loadStatus();
    showAlert('Đã xác minh và kết nối tài khoản Threads thật.', 'success');
  } catch (error) { showAlert(error.message); }
});

document.querySelector('#refresh-token-btn').addEventListener('click', async () => {
  try { await api('/api/threads/refresh', {method: 'POST'}); await loadStatus(); showAlert('Đã làm mới token.', 'success'); }
  catch (error) { showAlert(error.message); }
});

document.querySelector('#disconnect-btn').addEventListener('click', async () => {
  if (!confirm('Ngắt kết nối tài khoản Threads khỏi web này?')) return;
  try { await api('/api/threads/disconnect', {method: 'POST'}); await loadStatus(); showAlert('Đã ngắt kết nối.', 'success'); }
  catch (error) { showAlert(error.message); }
});

const logoutBtn = document.querySelector('#logout-btn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    try { await api('/api/session/logout', {method: 'POST'}); location.reload(); }
    catch (error) { showAlert(error.message); }
  });
}

const searchParams = new URLSearchParams(location.search);
const oauthState = searchParams.get('oauth');
const oauthMsg = searchParams.get('msg');
if (oauthState === 'connected') showAlert('Đã kết nối Threads qua OAuth thành công!', 'success');
if (oauthState === 'error') showAlert(`Lỗi kết nối Threads: ${oauthMsg || 'Meta từ chối hoặc hủy yêu cầu kết nối.'}`, 'danger');
if (oauthState === 'state_invalid') showAlert('OAuth state không hợp lệ hoặc phiên làm việc đã hết hạn. Hãy thử lại.', 'danger');

Promise.all([loadStatus(), loadQueue(), loadHistory()]).then(() => {
  if (state.status?.job?.running) beginJobPolling();
});

