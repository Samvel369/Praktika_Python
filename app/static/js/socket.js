document.addEventListener("DOMContentLoaded", () => {
  const socket = io();              // ← одна инициализация
  window.socket = socket;           // ← делаем глобально доступным

  socket.emit("join", { room: `user_${window.CURRENT_USER_ID}` });

  socket.on("friend_accepted", function(data) {
    console.log("Новый друг:", data);

    const requestEl = document.querySelector(`[data-request-id="${data.request_id}"]`);
    if (requestEl) requestEl.remove();

    const friendsList = document.getElementById("friends-list");
    if (friendsList) {
      const div = document.createElement("div");
      div.style.marginBottom = "20px";
      div.innerHTML = `
        <img src="${data.friend_avatar}" width="60" style="border-radius: 50%; margin-right: 15px;">
        <strong><a href="/profile/${data.friend_id}">${data.friend_username}</a></strong>
      `;
      friendsList.appendChild(div);
    }
  });

  // Пример: можно добавлять другие socket.on(...) сюда
  socket.on("new_request", data => {
    console.log("Новая заявка в друзья:", data);
  });
});