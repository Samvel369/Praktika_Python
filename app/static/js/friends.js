// === friends.js — единые перерисовки секций без F5 ===
console.log('friends.js loaded');

function ok(m){ if (window.showNotification) showNotification(m || 'Готово', 'success'); }
function err(m){ if (window.showNotification) showNotification(m || 'Ошибка', 'error'); }

// Ждём, пока socket из socket.js инициализируется
function whenSocketReady(cb, tries = 0) {
  const s = window.socket;
  if (s && (s.connected || s.io)) return cb(s);
  if (tries < 40) return setTimeout(() => whenSocketReady(cb, tries + 1), 300);
  console.warn('socket не инициализировался');
}

// Подтяжка HTML для секции и замена DOM
function reloadSection(section) {
  const map = window.FRIENDS_PARTIALS || {};
  const url = map[section];
  const elId = {
    // id контейнеров на странице friends.html
    possible_friends: 'possible-friends-list',
    incoming: 'requests-list',
    outgoing: 'outgoing-requests',
    friends: 'friends-list',
    subscribers: 'subscribers-list',
    subscriptions: 'subscriptions-list',
  }[section];

  if (!url || !elId) return;
  fetch(url)
    .then(r => r.text())
    .then(html => {
      const box = document.getElementById(elId);
      if (box) box.innerHTML = html;
    })
    .catch(console.error);
}

// ===== SOCKET =====
if (location.pathname.includes('/friends')) {
  whenSocketReady((s) => {
    console.log('friends.js: socket ready (subscribe all)');

    // Снимаем прошлые подписки, чтобы не плодить обработчики
    s.off && s.off('update_possible_friends');
    s.off && s.off('friend_request_sent');
    s.off && s.off('friend_accepted');
    s.off && s.off('friend_request_cancelled');
    s.off && s.off('friend_removed');
    s.off && s.off('new_subscriber');
    s.off && s.off('subscribed_to');

    // Возможные друзья — приходят при отметках
    s.on('update_possible_friends', () => {
      reloadSection('possible_friends');
    });

    // Поступила заявка (получателю)
    s.on('friend_request_sent', () => {
      reloadSection('incoming');
    });

    // Заявка принята — у отправителя улетает из outgoing, появляется в friends
    s.on('friend_accepted', () => {
      reloadSection('friends');
      reloadSection('outgoing');
    });

    // Заявка отменена/отклонена
    s.on('friend_request_cancelled', () => {
      reloadSection('incoming');
      reloadSection('outgoing');
    });

    // Удалили из друзей
    s.on('friend_removed', () => {
      reloadSection('friends');
    });

    // На тебя подписались
    s.on('new_subscriber', () => {
      reloadSection('subscribers');
    });

    // Ты на кого-то подписался
    s.on('subscribed_to', () => {
      reloadSection('subscriptions');
    });

    // подписочные связи изменились (удалили/очистили/синхронизировали)
    s.off && s.off('subscribers_refresh');
    s.on('subscribers_refresh', () => {
      reloadSection('subscribers');
      reloadSection('subscriptions');
    });
  });
}

// ===== ПЕРЕХВАТ ЛОКАЛЬНЫХ ФОРМ (без «белых страниц») =====
document.addEventListener('submit', async (e) => {
  const form = e.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (!location.pathname.includes('/friends')) return;
  if ((form.method || '').toUpperCase() !== 'POST') return;

  e.preventDefault();

  // защита от дабл-кликов
  const submitBtn = form.querySelector('[type="submit"]');
  if (form.dataset.busy === '1') return;
  form.dataset.busy = '1';
  if (submitBtn) submitBtn.disabled = true;

  try {
    const fd = new FormData(form);
    const action = form.getAttribute('action') || location.pathname;
    const res = await fetch(action, { method: 'POST', body: fd });
    if (!res.ok) throw new Error('Ошибка запроса');
    ok('Готово');

    // локально догружаем вероятные секции, не ожидая сокета
    if (action.includes('/send_friend_request')) {
      reloadSection('outgoing');   // у отправителя появляется исходящая
      reloadSection('possible_friends'); // и снимается из возможных
    } else if (action.includes('/accept_friend_request')) {
      reloadSection('incoming');   // исчезает входящая
      reloadSection('friends');    // появляется друг
      reloadSection('possible_friends');
      reloadSection('subscribers');
      reloadSection('subscriptions');
    } else if (action.includes('/cancel_friend_request')) {
      reloadSection('incoming');
      reloadSection('outgoing');
      reloadSection('possible_friends');

      // если это «оставить в подписчиках», обновим локально «Подписан на»
      if ([...fd.entries()].some(([k, v]) => k === 'subscribe' && String(v) === 'true')) {
        reloadSection('subscriptions');  // у отправителя — «Подписан на»
        reloadSection('subscribers');  // у получателя — «Подписчики»
      }
    } else if (action.includes('/remove_friend')) {
      reloadSection('friends');
      reloadSection('possible_friends');
    } else if (action.includes('/subscribe')) {
      reloadSection('subscriptions'); // у подписчика
      // у владельца придёт сокет new_subscriber → обновит subscribers
      reloadSection('possible_friends');
    }
  } catch (e2) {
    console.error(e2);
    err('Ошибка');
  } finally {
    form.dataset.busy = '0';
    if (submitBtn) submitBtn.disabled = false;
  }
}, true);
