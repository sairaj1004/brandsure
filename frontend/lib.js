/* BrandSure frontend helpers: DOM builder, API calls, modal, toast, session. No innerHTML anywhere (prevents XSS). */
const S = {
  token: localStorage.getItem('bs_token') || '',
  user: JSON.parse(localStorage.getItem('bs_user') || 'null'),
};

function setSession(token, user) {
  S.token = token; S.user = user;
  if (token) { localStorage.setItem('bs_token', token); localStorage.setItem('bs_user', JSON.stringify(user)); }
  else { localStorage.removeItem('bs_token'); localStorage.removeItem('bs_user'); }
}

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'value' || k === 'checked' || k === 'selected' || k === 'disabled') e[k] = v;
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return e;
}

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  let r;
  try {
    r = await fetch('/api' + path, { method: opts.method || 'GET', headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  } catch (e) { throw new Error('Cannot reach the server. Is it running?'); }
  let data = null;
  try { data = await r.json(); } catch (e) { /* not json */ }
  if (r.status === 401 && S.token) { setSession('', null); location.hash = '#/login'; throw new Error('Please sign in again.'); }
  if (!r.ok) throw new Error((data && data.detail) || ('Request failed (' + r.status + ')'));
  return data;
}

function toast(msg, bad) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), bad ? 6000 : 3500);
}

/* Run an async action; show errors as a toast. */
async function guard(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); return undefined; }
}

function modal({ title, body, buttons, wide }) {
  const root = document.getElementById('modal-root');
  const err = h('div', { class: 'err', role: 'alert' });
  const close = () => { back.remove(); document.removeEventListener('keydown', onKey); if (prev && prev.focus) prev.focus(); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  const prev = document.activeElement;
  const btns = (buttons || [{ label: 'Close', cls: 'ghost' }]).map((b) =>
    h('button', {
      class: 'btn ' + (b.cls || ''), type: 'button',
      onclick: async (ev) => {
        err.textContent = '';
        if (!b.onclick) { close(); return; }
        ev.target.disabled = true;
        try { const keep = await b.onclick(); if (keep !== false) close(); }
        catch (e) { err.textContent = e.message; }
        finally { ev.target.disabled = false; }
      },
    }, b.label));
  const box = h('div', { class: 'modal' + (wide ? ' wide' : ''), role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('h2', null, title), body, err, h('div', { class: 'actions mt' }, btns));
  const back = h('div', { class: 'modal-back', onclick: (e) => { if (e.target === back) close(); } }, box);
  root.append(back);
  document.addEventListener('keydown', onKey);
  const first = box.querySelector('input,select,textarea,button');
  if (first) first.focus();
  return close;
}

function field(label, input, help) {
  return h('div', null, h('label', { class: 'f' }, label), input, help ? h('div', { class: 'small muted' }, help) : null);
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

const STATUS = { draft: 'Draft', checked: 'Checked', in_review: 'In review', changes_requested: 'Changes requested', approved: 'Approved' };
function statusBadge(s) { return h('span', { class: 'badge ' + s }, STATUS[s] || s); }

function downloadCSV(filename, rows) {
  const esc = (v) => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
  const blob = new Blob([rows.map((r) => r.map(esc).join(',')).join('\n')], { type: 'text/csv' });
  const a = h('a', { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a); a.click(); a.remove();
}

function fileToB64(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(',')[1] || '');
    fr.onerror = () => rej(new Error('Could not read that file.'));
    fr.readAsDataURL(file);
  });
}

function parseHash() {
  const raw = location.hash.slice(1) || '/';
  const [path, qs] = raw.split('?');
  return { path, q: Object.fromEntries(new URLSearchParams(qs || '')) };
}

const can = (...roles) => S.user && roles.includes(S.user.role);
