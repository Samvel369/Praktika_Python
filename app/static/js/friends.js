document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".add-friend-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const userId = btn.dataset.userId;
      socket.emit("send_friend_request", { user_id: userId });
    });
  });

  socket.on("friend_list_update", data => {
    console.log("Обновлён список друзей");
    // updateFriendList() — если такая функция есть
  });
});

//<!-- Основной JavaScript -->

  // --- Инициализация Socket.IO ---
  socket.on('connect', () => {
    console.log('✅ Подключено к Socket.IO');
  });

  // --- Обновление возможных друзей ---
  socket.on('update_possible_friends', function(data) {
    console.log("👥 Обновление возможных друзей:", data);

    fetch("/friends_partial")
      .then(res => res.text())
      .then(html => {
        const container = document.getElementById("possible-friends-list");
        if (container) container.innerHTML = html;
      });

    // Дополнительно можно динамически вставлять нового пользователя (если нужно):
    /*
    const container = document.getElementById("possible-friends-list");
    if (container) {
      const newUser = document.createElement("div");
      newUser.classList.add("friend-box");
      newUser.innerHTML = `
          <p><a href="/user/${data.user_id}">${data.username}</a></p>
          <button onclick="addFriend(${data.user_id})">Добавить в друзья</button>
          <button onclick="subscribe(${data.user_id})">Подписаться</button>
      `;
      container.prepend(newUser);
    }
    */
  });

  // --- Другие события ---
  socket.on('friend_accepted', function (data) {
    const requestEl = document.querySelector(`[data-request-id="${data.request_id}"]`);
    if (requestEl) requestEl.remove();

    const friendsList = document.getElementById('friends-list');
    if (friendsList) {
      const div = document.createElement('div');
      div.innerHTML = `
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
          <img src="${data.friend_avatar}" style="width: 60px; height: 60px; border-radius: 50%; margin-right: 15px;">
          <div style="flex-grow: 1;">
            <strong><a href="/profile/${data.friend_id}">${data.friend_username}</a></strong><br>
            <a href="/profile/${data.friend_id}">Перейти в профиль</a>
          </div>
          <form method="post" action="/remove_friend/${data.friend_id}">
            <button type="submit">Удалить из друзей</button>
          </form>
        </div>
      `;
      friendsList.appendChild(div);

      const noMsg = document.getElementById('no-friends-msg');
      if (noMsg) noMsg.remove();
    }
  });

  socket.on('friend_removed', function(data) {
    const friendEl = document.querySelector(`#friends-list [data-user-id="${data.user_id}"]`);
    if (friendEl) friendEl.remove();

    const friendsList = document.getElementById('friends-list');
    if (friendsList && friendsList.children.length === 0) {
      const msg = document.createElement('p');
      msg.id = 'no-friends-msg';
      msg.textContent = 'Пока нет друзей.';
      friendsList.appendChild(msg);
    }
  });

  socket.on('friend_request_cancelled', function (data) {
    const requestEl = document.querySelector(`[data-request-id="${data.request_id}"]`);
    if (requestEl) requestEl.remove();
  });

  socket.on('new_subscriber', function(data) {
    const list = document.getElementById('subscribers-list');
    if (!list) return;

    const noMsg = document.getElementById('no-subscribers-msg');
    if (noMsg) noMsg.remove();

    const div = document.createElement('div');
    div.style = "display: flex; align-items: center; margin-bottom: 20px;";
    div.innerHTML = `
      <img src="${data.subscriber_avatar}" alt="avatar"
          style="width: 60px; height: 60px; object-fit: cover; border-radius: 50%; margin-right: 15px;">
      <div style="flex-grow: 1;">
        <strong>
          <a href="/profile/${data.subscriber_id}">
            ${data.subscriber_username}
          </a>
        </strong><br>
        <a href="/profile/${data.subscriber_id}">Перейти в профиль</a>
      </div>
    `;
    list.appendChild(div);
  });

  socket.on('friend_request_sent', function (data) {
    const possible = document.querySelector(`[data-user-id="${data.sender_id}"]`);
    if (possible) possible.remove();

    const requestsList = document.getElementById('requests-list');
    if (!requestsList) return;

    const noMsg = document.getElementById('no-requests-msg');
    if (noMsg) noMsg.remove();

    if (requestsList.querySelector(`[data-request-id="${data.request_id}"]`)) return;

    const div = document.createElement('div');
    div.setAttribute('data-request-id', data.request_id);
    div.innerHTML = `
      <div style="display: flex; align-items: center; margin-bottom: 20px;">
        <img src="${data.sender_avatar}" style="width: 60px; border-radius: 50%; margin-right: 15px;">
        <div style="flex-grow: 1;">
          <strong><a href="/profile/${data.sender_id}">${data.sender_username}</a></strong><br>
          <a href="/profile/${data.sender_id}">Перейти в профиль</a>
        </div>
        <form method="post" action="/accept_friend_request/${data.request_id}" style="margin-right: 5px;">
          <button type="submit">Принять</button>
        </form>
        <form method="post" action="/cancel_friend_request/${data.request_id}">
          <input type="hidden" name="subscribe" value="true">
          <button type="submit">Оставить в подписчиках</button>
        </form>
      </div>
    `;
    requestsList.appendChild(div);
  });

  socket.on('subscribed_to', function(data) {
    const list = document.getElementById('subscriptions-list');
    if (!list) return;

    if (list.querySelector(`[data-user-id="${data.user_id}"]`)) return;

    const noMsg = document.getElementById('no-subscriptions-msg');
    if (noMsg) noMsg.remove();

    const div = document.createElement('div');
    div.setAttribute('data-user-id', data.user_id);
    div.style = "display: flex; align-items: center; margin-bottom: 20px;";
    div.innerHTML = `
      <img src="${data.avatar}" alt="avatar"
          style="width: 60px; height: 60px; object-fit: cover; border-radius: 50%; margin-right: 15px;">
      <div style="flex-grow: 1;">
        <strong><a href="/profile/${data.user_id}">${data.username}</a></strong><br>
        <a href="/profile/${data.user_id}">Перейти в профиль</a>
      </div>
    `;
    list.appendChild(div);
  });

  function startCleanupDatabaseTimer() {
    const selectElement = document.getElementById("cleanup_time");
    if (!selectElement) return;

    const minutes = parseInt(selectElement.value);
    if (!minutes || minutes <= 0) return;

    // Отправляем POST-запрос на сервер для очистки базы
    fetch("/cleanup_potential_friends", {
        method: "POST",
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `minutes=${minutes}`
    });

    // Запускаем повтор через N минут
    setTimeout(startCleanupDatabaseTimer, minutes * 60 * 1000);
}

// Запускаем первый раз при загрузке
startCleanupDatabaseTimer();


document.addEventListener("DOMContentLoaded", function () {
    const select = document.getElementById("cleanup_time");

    // Сохраняем выбор в сессии
    select.addEventListener("change", function () {
        const minutes = select.value;
        sessionStorage.setItem("cleanup_time", minutes);
    });

    function cleanupPotentialFriends() {
        const minutes = sessionStorage.getItem("cleanup_time") || select.value;

        fetch("/cleanup_potential_friends", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: "cleanup_time=" + encodeURIComponent(minutes)
        }).then(response => {
            if (!response.ok) {
                console.error("Ошибка при очистке возможных друзей");
            } else {
                // 🔄 Обновляем HTML после успешной очистки
                fetch("/friends_partial")
                  .then(res => res.text())
                  .then(html => {
                      const container = document.getElementById("possible-friends-list");
                      if (container) container.innerHTML = html;
                  });
            }
        });
    }


    // Запуск сразу при загрузке
    cleanupPotentialFriends();

    // И повторять каждые 1 сек
    setInterval(cleanupPotentialFriends, 1000);
});


// ⏱️ Удаление просроченных возможных друзей
setInterval(() => {
    const now = Date.now();
    const lifespan = CLEANUP_TIME_MINUTES * 60 * 1000;

    document.querySelectorAll(".possible-friend").forEach(el => {
        const appearedAt = parseInt(el.dataset.appearedAt);
        if (!appearedAt) return;

        if ((now - appearedAt) >= lifespan) {
            el.remove(); // Удаляем с экрана
        }
    });
}, 10000); // Проверка каждые 10 сек

  const CLEANUP_TIME_MINUTES = { cleanup_time };

