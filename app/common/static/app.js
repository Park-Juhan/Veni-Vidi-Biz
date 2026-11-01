// Preserve user control over whether entries are fictional or user supplied.
// Native form validation and server validation both remain active.
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.textContent = '계산 중…'; button.disabled = true; }
  });
});
