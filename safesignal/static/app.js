setInterval(async () => {
  const live = document.querySelector('#live');
  if (!live || live.querySelector('details[open]') || document.activeElement?.closest('#live')) return;
  try {
    const response = await fetch('/', {cache: 'no-store'});
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const updated = html.querySelector('#live');
    if (updated) live.replaceChildren(...updated.childNodes);
  } catch { /* Retain last observed state during a web connection failure. */ }
}, 3000);
