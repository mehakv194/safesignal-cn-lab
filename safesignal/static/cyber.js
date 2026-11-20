const report = document.querySelector('[data-cyber-report]');
if (report) {
  const category = report.elements.category;
  function showCategory() {
    for (const group of report.querySelectorAll('[data-category]')) {
      group.hidden = group.disabled = group.dataset.category !== category.value;
    }
  }
  category.addEventListener('change', showCategory);
  showCategory();
  report.addEventListener('submit', (event) => {
    const file = report.elements.file;
    if (file?.files[0]?.size > Number(file.dataset.maxBytes)) {
      if (!window.confirm('This attachment exceeds the size limit. Save the report without it?')) {
        event.preventDefault();
      } else {
        file.value = '';
      }
    }
  });
}
const messages = document.querySelector('[data-cyber-messages]');
async function refreshConversation() {
  if (!messages?.dataset.cyberMessages || document.hidden) return;
  try {
    const response = await fetch(messages.dataset.cyberMessages);
    if (response.ok && !response.redirected) messages.innerHTML = await response.text();
  } catch { /* Keep the last confirmed view when offline. */ }
}
if (messages) window.setInterval(refreshConversation, 5000);
const messageForm = document.querySelector('[data-cyber-message]');
messageForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = messageForm.querySelector('[data-message-status]');
  const button = messageForm.querySelector('button');
  const draft = messageForm.elements.body.value;
  button.disabled = true;
  try {
    const response = await fetch(messageForm.action, {method:'POST',body:new FormData(messageForm),headers:{Accept:'application/json'}});
    if (!response.ok || response.redirected) throw new Error();
    messageForm.elements.client_uuid.value = (await response.json()).next_key;
    if (messageForm.elements.body.value === draft) messageForm.elements.body.value = '';
    status.textContent = 'Message stored. This is not a read receipt.';
    await refreshConversation();
  } catch { status.textContent = 'Message not confirmed. Your draft is still here.'; }
  finally { button.disabled = false; }
});
for (const toggle of document.querySelectorAll('[data-toggle-password]')) {
  toggle.addEventListener('click', () => {
    const field = toggle.previousElementSibling.querySelector('input');
    const show = field.type === 'password';
    field.type = show ? 'text' : 'password';
    toggle.setAttribute('aria-pressed', String(show));
    toggle.textContent = show ? 'Hide password' : 'Show password';
  });
}
