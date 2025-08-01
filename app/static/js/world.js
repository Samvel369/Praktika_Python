function markAction(actionId) {
    fetch('/mark_action/' + actionId, {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateCounters();
            } else if (data.error === 'wait') {
                showCooldown(actionId, data.remaining);
            }
        });
}

function showCooldown(actionId, seconds) {
    const span = document.querySelector(`#cooldown-${actionId}`);
    if (!span) return;
    span.style.display = 'inline';
    let remaining = seconds;

    const interval = setInterval(() => {
        span.innerText = `Подождите ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;
        remaining--;
        if (remaining <= 0) {
            clearInterval(interval);
            span.innerText = '';
            span.style.display = 'none';
        }
    }, 1000);
}

function updateCounters() {
    fetch('/get_mark_counts')
        .then(res => res.json())
        .then(counts => {
            for (const [actionId, count] of Object.entries(counts)) {
                const el = document.getElementById('counter-' + actionId);
                if (el) el.innerText = count;
            }
        });
}

updateCounters();
setInterval(updateCounters, 1000);

function publishAction(actionId, text) {
    const duration = document.getElementById(`duration-${actionId}`).value;

    fetch(`/publish_action/${actionId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({duration: duration})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
            return;
        }

        if (data.success) {
            // Добавляем в список опубликованных с ССЫЛКОЙ
            const publishedList = document.getElementById('published-actions');
            const li = document.createElement('li');
            li.setAttribute('data-id', data.id);
            li.innerHTML = `
                <a href="/action/${data.id}" target="_blank">${data.text}</a> —
                <span id="counter-${data.id}">0</span> чел.
                <button onclick="markAction(${data.id})">Отметиться</button>
            `;
            publishedList.prepend(li);

            // Удаляем опубликованный черновик
            const publishBtn = document.querySelector(`button[onclick="publishAction(${actionId}, '${text}')"]`);
            if (publishBtn) {
                const draftBlock = publishBtn.closest('.draft-action');
                if (draftBlock) {
                    draftBlock.remove();
                }
            }
        }
    });
}

function fetchPublishedActions() {
    fetch('/get_published_actions')
        .then(res => res.json())
        .then(actions => {
            const container = document.getElementById('published-actions');
            const existingItems = Array.from(container.children);
            const existingIds = new Set(existingItems.map(li => li.getAttribute('data-id')));
            const incomingIds = new Set(actions.map(action => String(action.id)));

            // Удаляем действия, которые больше не актуальны (истёк срок)
            existingItems.forEach(li => {
                const id = li.getAttribute('data-id');
                if (!incomingIds.has(id)) {
                    li.remove();
                }
            });

            // Добавляем новые действия
            actions.forEach(action => {
                if (!existingIds.has(String(action.id))) {
                    const li = document.createElement('li');
                    li.setAttribute('data-id', action.id);
                    li.innerHTML = `${action.text} — <span id="counter-${action.id}">0</span> чел. <button onclick="markAction(${action.id})">Отметиться</button>`;
                    container.prepend(li);
                }
            });
        });
}

// Обновляем список каждую секунду
setInterval(fetchPublishedActions, 1000);