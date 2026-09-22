/* Presentation and controls for the fixed, responsive media workspace. */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
let state = null, requestPending = false, lastRows = '', lastResults = '', closing = false;
let toastTimer;

function notify(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 5000);
}

function render(next) {
  state = next;
  document.body.classList.toggle('busy', next.busy);
  const file = next.path.split(/[\\/]/).pop();
  $('#filename').textContent = file || 'Choose a media file';
  $('#filename').title = next.path;
  $('#filedetail').textContent = file ? 'Selected and ready on this device' : 'Browse files on your device';
  $('#depth-value').textContent = next.lsb;
  for (const button of $$('[data-control]')) button.disabled = requestPending || next.controls[button.dataset.control] === 'disabled';
  for (const button of $$('[data-depth]')) {
    button.disabled = requestPending || next.busy;
    button.setAttribute('aria-pressed', String(button.dataset.depth === next.lsb));
  }
  $('#output').textContent = next.output;
  $('#verdict').textContent = next.verdict === 'Not verified' ? 'Not verified yet.' : next.verdict;
  $('#activity').replaceChildren(Object.assign(document.createElement('span'), {className: 'live-dot'}),
    document.createTextNode(next.busy ? 'PROCESSING' : next.verdict === 'Not verified' ? 'STANDING BY' : 'COMPLETE'));
  $('#save-hint').textContent = next.protected ? 'Your protected media is ready to save.' : 'Protect your media to create a shareable stego file.';
  // The session holds a passphrase the page never receives; say so after a refresh.
  const manual = next.start_mode === 'manual';
  for (const button of $$('[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === next.start_mode));
  $('#manual-start').hidden = !manual;
  if (document.activeElement !== $('#manual-start')) $('#manual-start').value = next.manual_start;
  $('#mode-hint').textContent = manual
    ? 'Manual uses the position you type. It is not protected by the passphrase — anyone who guesses the number can read the payload.'
    : 'Automatic derives the position from your passphrase — different for every file.';
  $('#passphrase-hint').textContent = next.passphrase_set && !$('#passphrase').value
    ? 'This session already holds a passphrase. Re-enter it to protect or verify.'
    : 'Decides where the payload hides. Party B needs this same passphrase — it is never stored in the file.';
  $('#test-summary').textContent = next.test_summary;
  $('#test-output').textContent = next.test_output;
  const rows = JSON.stringify(next.statuses);
  if (rows !== lastRows) {
    lastRows = rows;
    $('#statuses').replaceChildren();
    if (!next.statuses.length) {
      const row = document.createElement('div'); row.className = 'stage-placeholder';
      row.textContent = 'Verification stages will appear here'; $('#statuses').append(row);
    }
    for (const row of next.statuses) {
      const line = document.createElement('div'); line.className = 'stage-row';
      for (const value of row.values) { const text = document.createElement('span'); text.textContent = value; line.append(text); }
      $('#statuses').append(line);
    }
  }
  const results = JSON.stringify(next.results);
  if (results !== lastResults) {
    lastResults = results;
    $('#results').replaceChildren();
    $('#report-empty').hidden = next.results.length > 0;
    for (const row of next.results) {
      const tr = document.createElement('tr'); tr.className = row.tags.includes('pass') ? 'pass' : 'fail';
      for (const value of row.values) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
      $('#results').append(tr);
    }
  }
}

async function action(name, value) {
  if (requestPending || closing) return;
  requestPending = true;
  if (state) render(state);
  try {
    const response = await fetch('action', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: name, value})});
    const next = await response.json();
    if (!response.ok) throw new Error(next.error || 'This action could not be completed.');
    render(next);
  } catch (error) { notify(error.message); }
  finally { requestPending = false; if (state) render(state); }
}

async function poll() {
  if (closing) return;
  try {
    const response = await fetch('state');
    if (!response.ok) throw new Error('Disconnected');
    const next = await response.json();
    if (!requestPending) render(next);
    $('#connection').textContent = 'Local session';
  } catch { $('#connection').textContent = 'Session disconnected'; }
  setTimeout(poll, 400);
}

// Protect and verify both need the passphrase the user typed. Send it first so
// the value never has to be polled back into the page.
const NEEDS_PASSPHRASE = new Set(['protect', 'verify']);
$$('[data-action]').forEach(button => button.addEventListener('click', async () => {
  const name = button.dataset.action;
  if (NEEDS_PASSPHRASE.has(name)) {
    await action('passphrase', $('#passphrase').value);
    await action('manual_start', $('#manual-start').value);
  }
  await action(name);
}));
$$('[data-depth]').forEach(button => button.addEventListener('click', () => action('depth', button.dataset.depth)));
$$('[data-mode]').forEach(button => button.addEventListener('click', () => action('start_mode', button.dataset.mode)));

function setView(view) {
  for (const name of ['workspace', 'testing']) $('#' + name).hidden = name !== view;
  $$('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
    button.setAttribute('aria-pressed', String(button.dataset.view === view));
  });
}
$$('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
$('.brand').addEventListener('click', event => { event.preventDefault(); setView('workspace'); });

$('#close').addEventListener('click', async () => {
  if (state?.busy) { notify('Your file is still processing. Close when it finishes.'); return; }
  await action('close'); closing = true;
  $('#connection').textContent = 'Session closed';
  $$('[data-action], [data-depth]').forEach(button => { button.disabled = true; });
  window.close();
});
window.addEventListener('pagehide', () => {
  if (!closing) navigator.sendBeacon('action', new Blob([JSON.stringify({action: 'detach'})], {type: 'application/json'}));
});
poll();
