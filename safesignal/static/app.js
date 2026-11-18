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
  if (event.target.closest('[data-open-report]')) document.querySelector('#report-dialog')?.showModal();
  if (event.target.closest('[data-close-dialog]')) document.querySelector('#report-dialog')?.close();
});
let polling = false;
setInterval(async () => {
  const regions = [...document.querySelectorAll('[data-poll-region]')];
  if (polling || document.hidden || !regions.length || regions.some(region =>
    region.contains(document.activeElement) || region.querySelector('details[open], form[data-dirty]'))) return;
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
