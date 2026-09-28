/* Presentation and controls for the fixed, responsive media workspace. */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
let state = null, requestPending = false, lastRows = '', lastResults = '', closing = false;
let toastTimer, lastPreview = '', manualDirty = false, payloadDirty = false;

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
  $('#decoded-payload').textContent = next.decoded_payload || 'No decoded payload yet.';
  $('#verdict').textContent = next.verdict === 'Not verified' ? 'Not verified yet.' : next.verdict;
  $('#activity').replaceChildren(Object.assign(document.createElement('span'), {className: 'live-dot'}),
    document.createTextNode(next.busy ? 'PROCESSING' : next.verdict === 'Not verified' ? 'STANDING BY' : 'COMPLETE'));
  $('#save-row').hidden = $('[data-action=save]').hidden = !next.save_ready;
  $('#save-hint').textContent = next.save_ready ? 'Saved copies can be verified here as Party B.'
    : next.protected ? 'Protected copy ready. Verify it to check the result before saving.'
    : 'Verify checks the protected copy, or the file you selected.';
  // The session holds a passphrase the page never receives; say so after a refresh.
  const manual = next.start_mode === 'manual';
  for (const button of $$('[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === next.start_mode));
  $('#manual-start').hidden = !manual;
  // Never overwrite a position the user has typed but not yet sent: a click on
  // Protect blurs the box, and the next render would otherwise erase it.
  if (!manualDirty && document.activeElement !== $('#manual-start')) $('#manual-start').value = next.manual_start;
  $('#mode-hint').textContent = manual
    ? 'Manual uses the position you type. It is not protected by the passphrase, so anyone who guesses the number can read the payload.'
    : 'Automatic derives the position from your passphrase, so it differs for every file.';
  $('#passphrase-hint').textContent = next.passphrase_set && !$('#passphrase').value
    ? 'This session already holds a passphrase. Re-enter it to protect or verify.'
    : 'Decides where the payload hides. Party B needs this same passphrase. It is never stored in the file.';
  if (!payloadDirty && document.activeElement !== $('#payload')) $('#payload').value = next.payload || '';
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
      const line = document.createElement('div'); line.className = 'stage-row ' + (row.tags || []).join(' ');
      const mark = document.createElement('span'); mark.className = 'stage-mark'; line.append(mark);
      for (const value of row.values) { const text = document.createElement('span'); text.textContent = value; line.append(text); }
      $('#statuses').append(line);
    }
  }
  const preview = [next.media_kind, next.preview_version, next.protected, next.path].join('|');
  if (preview !== lastPreview) { lastPreview = preview; updatePreview(next); }
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

// Preview panes load media through the session's own endpoints; the page
// never receives file bytes through the polled state.
function showPane(pane, kind, src, emptyText) {
  const img = pane.querySelector('img'), audio = pane.querySelector('audio'), empty = pane.querySelector('.pane-empty');
  const label = empty.querySelector('span');
  if (emptyText) label.textContent = emptyText;
  img.hidden = true; if (audio) audio.hidden = true; empty.hidden = false;
  img.removeAttribute('src'); if (audio) { audio.removeAttribute('src'); audio.load(); }
  if (!src) return;
  if (kind === 'image') {
    img.onerror = () => { img.hidden = true; empty.hidden = false; label.textContent = 'Preview unavailable for this file'; };
    img.onload = () => { img.hidden = false; empty.hidden = true; };
    img.src = src;
  } else if (kind === 'audio' && audio) {
    audio.src = src; audio.hidden = false; empty.hidden = true;
  }
}

async function updatePreview(next) {
  const kind = next.media_kind, v = next.preview_version;
  showPane($('#pane-original'), kind, next.path && kind ? `preview/original?v=${v}` : null, 'Source media preview');
  showPane($('#pane-protected'), kind, next.protected && kind ? `preview/protected?v=${v}` : null, 'Stego media preview');
  const diff = $('#pane-difference');
  diff.classList.toggle('comparing', Boolean(next.protected && kind));
  showPane(diff, null, null, next.protected ? `Comparing every ${kind === 'audio' ? 'sample' : 'pixel'} of the original with the protected copy…` : 'Protect a file to see what changed');
  const unit = kind === 'audio' ? 'sample' : 'pixel';
  $('#preview-note').textContent = !next.path ? 'Choose a file to preview it. Protect it to compare the original with the stego output.'
    : !next.protected ? 'The selected file is shown on the left. Protect it to compare it with the stego output.'
    : `The protected copy looks identical by design. The third pane marks every ${unit} whose low bits now carry payload.`;
  if (!next.protected || !kind) return;
  const started = performance.now();
  try {
    const response = await fetch(`preview/difference?v=${v}`);
    if (!response.ok) throw new Error('No difference available');
    if (lastPreview !== [next.media_kind, next.preview_version, next.protected, next.path].join('|')) return; // superseded
    const type = response.headers.get('Content-Type') || '';
    if (type.startsWith('image/')) {
      const blob = await response.blob();
      const img = diff.querySelector('img');
      const changed = Number(response.headers.get('X-Changed')), total = Number(response.headers.get('X-Total'));
      const box = (response.headers.get('X-Box') || '').split(',').map(Number), scale = Number(response.headers.get('X-Scale'));
      const seconds = ((performance.now() - started) / 1000).toFixed(1);
      img.onload = () => {
        URL.revokeObjectURL(img.src); img.hidden = false; diff.querySelector('.pane-empty').hidden = true; diff.classList.remove('comparing');
        const where = box.length === 4 ? ` The third pane zooms ${scale >= 1 ? scale.toFixed(1) + 'x into' : 'to'} rows ${box[1].toLocaleString()} to ${box[3].toLocaleString()}, columns ${box[0].toLocaleString()} to ${box[2].toLocaleString()}, where the payload sits.` : '';
        $('#preview-note').textContent = `The protected copy looks identical by design. ${changed.toLocaleString()} of ${total.toLocaleString()} pixels changed (compared in ${seconds}s).${where}`;
      };
      img.onerror = () => { diff.classList.remove('comparing'); $('#difference-text').textContent = 'The browser could not display the comparison image.'; };
      img.src = URL.createObjectURL(blob);
    } else {
      const counts = await response.json();
      diff.classList.remove('comparing');
      $('#difference-text').textContent = `${counts.changed.toLocaleString()} of ${counts.total.toLocaleString()} samples changed. Play both to hear that they match.`;
    }
  } catch (error) {
    diff.classList.remove('comparing');
    $('#difference-text').textContent = `Comparison unavailable: ${error.message}. The original and protected copies may differ in size or be unreadable.`;
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
const NEEDS_PAYLOAD = new Set(['protect']);
$('#manual-start').addEventListener('input', () => { manualDirty = true; });
$('#payload').addEventListener('input', () => { payloadDirty = true; });
$$('[data-action]').forEach(button => button.addEventListener('click', async () => {
  const name = button.dataset.action;
  if (NEEDS_PASSPHRASE.has(name)) {
    // Read both boxes before any request re-renders the page.
    const passphrase = $('#passphrase').value, manualStart = $('#manual-start').value;
    await action('passphrase', passphrase);
    await action('manual_start', manualStart);
    manualDirty = false;
  }
  if (NEEDS_PAYLOAD.has(name)) await action('payload', $('#payload').value);
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
