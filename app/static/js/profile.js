// Небольшой ajax-хелпер для кнопок на страницах профиля/превью
document.addEventListener('submit', async (e) => {
  const form = e.target;
  if (!(form instanceof HTMLFormElement)) return;

  // обрабатываем только формы с атрибутом data-ajax
  if (!form.hasAttribute('data-ajax')) return;

  e.preventDefault();

  const btn = form.querySelector('[type="submit"]');
  if (form.dataset.busy === '1') return;
  form.dataset.busy = '1';
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(form.action || location.href, { method: 'POST', body: new FormData(form) });
    const data = await res.json().catch(() => ({}));
    if (window.showNotification) showNotification(data.message || 'Готово', data.ok ? 'success' : 'error');

    if (data.ok && btn) {
      btn.textContent = 'Заявка отправлена';
      btn.disabled = true;
    }
  } catch (err) {
    console.error(err);
    if (window.showNotification) showNotification('Ошибка', 'error');
  } finally {
    form.dataset.busy = '0';
    if (btn && !btn.disabled) btn.disabled = false;
  }
});
