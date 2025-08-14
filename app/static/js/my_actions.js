// my_actions.js — шаг 2: обновление DOM без перезагрузки

console.log('my_actions.js loaded');

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : null;
}
function ok(m){ if (window.showNotification) showNotification(m || 'Готово', 'success'); }
function err(m){ if (window.showNotification) showNotification(m || 'Ошибка', 'error'); }

async function postForm(url, formData) {
  const headers = {};
  const csrf = getCsrfToken();
  if (csrf) headers['X-CSRFToken'] = csrf;

  const res = await fetch(url, { method: 'POST', headers, body: formData });
  let data;
  try { data = await res.json(); } catch { throw new Error('Некорректный ответ сервера'); }
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || 'Ошибка запроса');
  }
  return data; // { ok, message, data: {...} }
}

// Рендер одной карточки (минимально — как в шаблоне)
function renderDraftItem(a) {
  const div = document.createElement('div');
  div.className = 'action-item';
  div.dataset.id = a.id;
  div.innerHTML = `
    <a href="/action/${a.id}">${escapeHtml(a.text)}</a>
    <form method="POST" style="display:inline;">
      <input type="hidden" name="delete_id" value="${a.id}">
      <button type="submit">Удалить</button>
    </form>

    <select name="duration" required>
      <option value="10">10 мин</option>
      <option value="30">30 мин</option>
      <option value="60">1 час</option>
    </select>
    <form method="POST" style="display:inline;">
      <input type="hidden" name="publish_id" value="${a.id}">
      <button type="submit">Опубликовать</button>
    </form>
  `;
  return div;
}

function renderPublishedItem(a) {
  const div = document.createElement('div');
  div.className = 'action-item';
  div.dataset.id = a.id;
  const expires = a.expires_at ? new Date(a.expires_at) : null;
  const fmt = expires ? fmtDate(expires) : '—';

  div.innerHTML = `
    <a href="/action/${a.id}">${escapeHtml(a.text)}</a>
    <small>Действует до: ${fmt}</small>
    <form method="POST" style="display:inline;">
      <input type="hidden" name="delete_id" value="${a.id}">
      <button type="submit">Удалить</button>
    </form>
  `;
  return div;
}

function fmtDate(d) {
  const pad = (n)=> String(n).padStart(2,'0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function escapeHtml(s){
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

const draftsList = document.getElementById('drafts-list');
const publishedList = document.getElementById('published-list');

// Перехватываем submit на всей странице /my_actions
if (location.pathname.includes('/my_actions')) {
  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;

    const isCreate = !!form.querySelector('input[name="new_action"]');
    const del = form.querySelector('input[name="delete_id"]');
    const pub = form.querySelector('input[name="publish_id"]');
    if (!isCreate && !del && !pub) return;

    e.preventDefault();

    const fd = new FormData(form);

    // Если это публикация — гарантируем наличие duration
    if (pub && !fd.has('duration')) {
        const inForm = form.querySelector('select[name="duration"]');
        const nearby = form.closest('.action-item')?.querySelector('select[name="duration"]');
        const sel = inForm || nearby;
        if (sel && sel.value) {
        fd.append('duration', sel.value);
        }
    }

    const url = form.getAttribute('action') || '/my_actions';

    try {
        const resp = await postForm(url, fd);
        if (resp.message) ok(resp.message);

        if (isCreate && resp.data?.action) {
        const item = renderDraftItem(resp.data.action);
        document.getElementById('drafts-list')?.prepend(item);
        const input = form.querySelector('input[name="new_action"]');
        if (input) input.value = '';
        return;
        }

        if (del && resp.data?.id) {
        document.querySelector(`.action-item[data-id="${resp.data.id}"]`)?.remove();
        return;
        }

        if (pub && resp.data?.action) {
        const id = resp.data.action.id;
        document.querySelector(`.action-item[data-id="${id}"]`)?.remove();
        const pubEl = renderPublishedItem(resp.data.action);
        document.getElementById('published-list')?.prepend(pubEl);
        return;
        }

    } catch (e2) {
        console.error(e2);
        err(e2.message || 'Ошибка');
    }
    }, true);
}
