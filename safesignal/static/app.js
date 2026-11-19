function updateCharts() {
  document.querySelectorAll('[data-width]').forEach(el => {
    const percent = Number(el.dataset.width);
    el.style.width = `${Number.isFinite(percent) ? Math.min(100, Math.max(0,percent)) : 0}%`;
  });
}
updateCharts();
document.addEventListener('input', event => {
  const form = event.target.closest('[data-poll-region] form');
  if (form) form.dataset.dirty = 'true';
});
document.addEventListener('click', event => {
  const quick = event.target.closest('[data-quick-reply]');
  if (quick) {
    const field = quick.closest('form').querySelector('textarea[name="body"]');
    field.value = quick.dataset.quickReply;
    field.dispatchEvent(new Event('input', {bubbles:true}));
    field.focus();
  }
  const toggle = event.target.closest('[data-toggle-password]');
  if (toggle) {
    const input = toggle.closest('form').querySelector('input[name="password"]');
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    toggle.textContent = visible ? 'Hide password' : 'Show password';
    toggle.setAttribute('aria-pressed', String(visible));
  }
  if (event.target.closest('[data-open-report]')) document.querySelector('#report-dialog')?.showModal();
  if (event.target.closest('[data-close-dialog]')) document.querySelector('#report-dialog')?.close();
});
document.addEventListener('submit', event => {
  if (event.target.method.toLowerCase() !== 'post') return;
  const feedback = document.querySelector('#action-feedback');
  if (feedback) feedback.textContent = navigator.onLine ? 'Sending — waiting for server confirmation…' : 'Offline — reconnect before submitting. Delivery is not confirmed.';
});
document.addEventListener('submit', async event => {
  const form=event.target;
  if (!form.matches('[data-room-send]')) return;
  event.preventDefault();
  if (form.dataset.sending) return;
  const status=form.querySelector('[data-message-status]');
  if (!navigator.onLine) { status.textContent='Not sent — reconnect to submit. Draft retained.'; return; }
  form.dataset.sending='true';
  status.textContent='Pending — waiting for a server receipt…';
  const button=form.querySelector('[type="submit"]');
  button.disabled=true;
  try {
    const response=await fetch(form.action,{method:'POST',headers:{Accept:'application/json'},body:new URLSearchParams(new FormData(form))});
    const result=await response.json();
    if (!response.ok || result.status!=='OK') throw new Error('unconfirmed');
    form.querySelector('textarea[name="body"]').value='';
    form.querySelector('[name="client_uuid"]').value=result.next_key;
    delete form.dataset.dirty;
    status.textContent='Saved on server. This is not a human read receipt.';
    const globalStatus=document.querySelector('#action-feedback');
    if (globalStatus) globalStatus.textContent='Message saved on server.';
  } catch {
    status.textContent='Not confirmed. Draft retained — retry sends the same message ID.';
    const globalStatus=document.querySelector('#action-feedback');
    if (globalStatus) globalStatus.textContent='Message not confirmed. Draft retained.';
  }
  finally { delete form.dataset.sending; button.disabled=false; }
});
let polling = false;
setInterval(async () => {
  const regions = [...document.querySelectorAll('[data-poll-region]')].filter(region =>
    !region.contains(document.activeElement) && !region.querySelector('details[open], form[data-dirty],form[data-sending]'));
  if (polling || document.hidden || !regions.length) return;
  polling = true;
  try {
    const response = await fetch(location.pathname + location.search, {cache:'no-store'});
    if (response.redirected) { location.assign(response.url); return; }
    if (!response.ok) return;
    const html = new DOMParser().parseFromString(await response.text(),'text/html');
    regions.forEach(region => {
      const updated = html.getElementById(region.id);
      if (updated) region.replaceChildren(...updated.childNodes);
    });
    updateCharts();
  } catch { /* Retain last observed state during a connection failure. */ }
  finally { polling = false; }
},5000);
document.querySelector('#export-chart')?.addEventListener('click', () => {
  const image = document.querySelector('#comparison-chart');
  if (!image?.complete || !image.naturalWidth) return;
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
  canvas.getContext('2d').drawImage(image,0,0);
  canvas.toBlob(blob => {
    if (!blob) return;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob); link.download = 'safesignal-comparison.png'; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href),1000);
  },'image/png');
});
