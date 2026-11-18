setInterval(async () => {
  const live = document.querySelector('#live');
  if (!live || live.querySelector('details[open]') || document.activeElement?.closest('#live')) return;
  try {
    const response = await fetch(location.pathname + location.search, {cache: 'no-store'});
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const updated = html.querySelector('#live');
    if (updated) live.replaceChildren(...updated.childNodes);
  } catch { /* Retain last observed state during a web connection failure. */ }
}, 3000);

document.querySelector('#export-chart')?.addEventListener('click', () => {
  const image = document.querySelector('#comparison-chart');
  if (!image?.complete || !image.naturalWidth) return;
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.getContext('2d').drawImage(image, 0, 0);
  canvas.toBlob(blob => {
    if (!blob) return;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'safesignal-comparison.png';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }, 'image/png');
});
