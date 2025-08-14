// =====================
// Универсальный fetch-хелпер
// =====================
async function apiRequest(url, options = {}) {
    const defaultHeaders = {
        "Content-Type": "application/json",
    };

    // Если в base.html будет meta-тег с CSRF — добавляем его
    const csrfToken = getCsrfToken();
    if (csrfToken) {
        defaultHeaders["X-CSRFToken"] = csrfToken;
    }

    const config = {
        method: options.method || "GET",
        headers: { ...defaultHeaders, ...(options.headers || {}) },
    };

    if (options.data) {
        config.body = JSON.stringify(options.data);
    }

    try {
        const response = await fetch(url, config);
        const data = await response.json();
        if (!response.ok) {
            showNotification(data.message || "Ошибка запроса", "error");
            throw new Error(data.message || "Ошибка запроса");
        }
        if (data.message) {
            showNotification(data.message, "success");
        }
        return data;
    } catch (err) {
        console.error("API Error:", err);
        throw err;
    }
}

// =====================
// Получение CSRF-токена из meta
// =====================
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : null;
}

// =====================
// Уведомления (тосты)
// =====================
function showNotification(message, type = "info") {
    const container = document.getElementById("notification-container");
    if (!container) return;

    const notification = document.createElement("div");
    notification.className = `notification ${type}`;
    notification.textContent = message;

    container.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}
