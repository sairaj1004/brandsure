/* BrandSure pages 1-5 and 7-9 plus the router. Page 6 (review report) is in report.js. */

const NAV = [
  ['Dashboard', '/dashboard', null],
  ['Knowledge Base', '/knowledge', null],
  ['New Review', '/review/new', ['creator', 'manager', 'admin']],
  ['Approvals', '/approvals', ['reviewer', 'manager', 'admin']],
  ['Insights', '/insights', ['manager', 'admin']],
  ['Settings', '/settings', null],
];

function shell(active, ...content) {
  const links = NAV.filter(([, , roles]) => !roles || roles.includes(S.user.role))
    .map(([label, path]) => h('a', { href: '#' + path, 'aria-current': active === path ? 'page' : false }, label));
  return h('div', { class: 'shell' },
    h('aside', { class: 'side' },
      h('a', { class: 'logo', href: '#/dashboard' }, h('i', null, 'B'), 'BrandSure'),
      h('nav', { 'aria-label': 'Main' }, links)),
    h('div', { class: 'main' },
      h('header', { class: 'topbar' },
        h('span', { class: 'muted' }, 'Signed in as ', h('b', null, S.user.name), ' ', h('span', { class: 'badge' }, S.user.role)),
        h('button', { class: 'btn ghost sm', onclick: () => { setSession('', null); location.hash = '#/'; } }, 'Logout')),
      h('main', { class: 'content', id: 'main', tabindex: '-1' }, content)));
}

function denied() { return h('div', { class: 'card' }, h('h2', null, 'No access'), h('p', { class: 'muted' }, 'Your role does not have access to this page.')); }

/* ============================================================ 1. Landing */
function pageLanding() {
  const card = (n, t, d) => h('div', { class: 'feature' }, h('div', { class: 'n' }, n), h('h3', null, t), h('p', { class: 'muted' }, d));
  return h('div', null,
    h('header', { class: 'land-top' },
      h('a', { class: 'logo', href: '#/' }, h('i', null, 'B'), 'BrandSure'),
      h('a', { class: 'btn', href: '#/login' }, 'Login')),
    h('section', { class: 'hero' },
      h('h1', null, 'Catch brand mistakes ', h('span', { class: 'grad' }, 'before you publish')),
      h('p', null, 'Add your approved guidelines and facts. Submit a draft. Get clear, source-cited findings and suggested fixes. A human always decides.'),
      h('div', { class: 'row', style: 'justify-content:center' },
        h('a', { class: 'btn', href: '#/login?tab=register' }, 'Get Started'),
        h('button', { class: 'btn ghost', onclick: () => document.getElementById('how').scrollIntoView({ behavior: 'smooth' }) }, 'See how it works'))),
    h('section', { class: 'sec', id: 'how' },
      h('h2', { style: 'text-align:center' }, 'How it works'),
      h('div', { class: 'cards3' },
        card('1', 'Add your rules', 'Import guidelines, glossary, approved facts and claims, and brand colours. Publish a version.'),
        card('2', 'Check a draft', 'Paste text or upload an image. Findings appear in seconds with the exact rule or fact behind each one.'),
        card('3', 'Approve with confidence', 'Accept, edit, dismiss or escalate. Managers approve. Every step is saved in the history.'))),
    h('section', { class: 'sec', style: 'background:#fff' },
      h('h2', { style: 'text-align:center' }, 'Why you can trust it'),
      h('div', { class: 'cards3' },
        card('✔', 'Every finding is explained', 'You see the flagged words, the source, the reason, a confidence level and whether it was rule-based or AI.'),
        card('?', 'No guessing', 'If no approved source supports a claim, it is marked Unverified, never silently approved or rejected.'),
        card('🔒', 'Confidential stays private', 'Confidential drafts never go to an external AI service, and the AI and data panel shows exactly what is used.'))),
    h('footer', { class: 'foot' }, h('span', null, '© 2026 BrandSure'),
      h('span', null, h('a', { href: '#/privacy' }, 'Privacy'), ' · ', h('a', { href: '#/terms' }, 'Terms'))));
}

function pageText(title, paras) {
  return h('div', { class: 'auth-wrap' }, h('div', { class: 'auth-card' }, h('h1', null, title), paras.map((p) => h('p', { class: 'muted' }, p)), h('a', { href: '#/' }, 'Back to home')));
}

/* ============================================================ 2. Login / Register */
function pageLogin(_m, q) {
  let tab = q.tab === 'register' ? 'register' : 'login';
  const wrap = h('div', { class: 'auth-wrap' });
  const err = h('div', { class: 'err', role: 'alert' });
  const email = h('input', { type: 'email', id: 'li-email', autocomplete: 'username' });
  const pw = h('input', { type: 'password', id: 'li-pw', autocomplete: 'current-password' });
  const ws = h('input', { type: 'text', id: 'rg-ws' }), nm = h('input', { type: 'text', id: 'rg-name' });
  const em2 = h('input', { type: 'email', id: 'rg-email' }), pw2 = h('input', { type: 'password', id: 'rg-pw', autocomplete: 'new-password' });

  async function submit(path, body, btn) {
    err.textContent = ''; btn.disabled = true;
    try {
      const r = await api(path, { method: 'POST', body });
      setSession(r.token, r.user);
      location.hash = '#/dashboard';
    } catch (e) { err.textContent = e.message; } finally { btn.disabled = false; }
  }
  function draw() {
    const loginBtn = h('button', { class: 'btn', type: 'submit' }, 'Login');
    const regBtn = h('button', { class: 'btn', type: 'submit' }, 'Create workspace');
    const tabs = h('div', { class: 'tabs', role: 'tablist' },
      ['login', 'register'].map((t) => h('button', { class: 'tab', role: 'tab', type: 'button', 'aria-selected': tab === t ? 'true' : 'false',
        onclick: () => { tab = t; err.textContent = ''; draw(); } }, t === 'login' ? 'Login' : 'Register')));
    const form = tab === 'login'
      ? h('form', { onsubmit: (e) => { e.preventDefault(); submit('/auth/login', { email: email.value, password: pw.value }, loginBtn); } },
        field('Email', email), field('Password', pw), err, h('div', { class: 'row mt' }, loginBtn,
          h('button', { class: 'link', type: 'button', onclick: () => { email.value = 'manager@nova.test'; pw.value = 'demo1234'; loginBtn.focus(); } }, 'Use demo account')))
      : h('form', { onsubmit: (e) => { e.preventDefault(); submit('/auth/register', { workspace_name: ws.value, name: nm.value, email: em2.value, password: pw2.value }, regBtn); } },
        field('Workspace name', ws), field('Your name', nm), field('Email', em2), field('Password (at least 8 characters)', pw2), err,
        h('div', { class: 'row mt' }, regBtn));
    wrap.replaceChildren(h('div', { class: 'auth-card' }, h('a', { class: 'logo mb', href: '#/' }, h('i', null, 'B'), 'BrandSure'), tabs, form,
      h('p', { class: 'small mt' }, h('a', { href: '#/' }, 'Back to home'))));
  }
  draw();
  return wrap;
}

/* ============================================================ 3. Dashboard */
async function pageDashboard() {
  const d = await api('/dashboard');
  let filter = '';
  const recentBox = h('div');
  const cards = [['drafts', 'Drafts', ['draft', 'checked']], ['in_review', 'In review', ['in_review']], ['changes_requested', 'Changes requested', ['changes_requested']], ['approved', 'Approved', ['approved']]];
  const statNodes = [];
  function drawRecent() {
    const list = filter ? d.recent.filter((r) => filter.includes(r.status)) : d.recent;
    recentBox.replaceChildren(list.length ? reviewTable(list) : h('div', { class: 'empty' }, 'No reviews here yet.'));
    statNodes.forEach(([n, st]) => n.setAttribute('aria-pressed', filter === st ? 'true' : 'false'));
  }
  const stats = h('div', { class: 'stats' }, cards.map(([key, label, st]) => {
    const n = h('button', { class: 'stat', type: 'button', onclick: () => { filter = filter === st ? '' : st; drawRecent(); } }, h('b', null, d.counts[key] || 0), label);
    statNodes.push([n, st]); return n;
  }));
  drawRecent();
  return shell('/dashboard',
    h('div', { class: 'row between mb' }, h('h1', null, 'Dashboard'),
      can('creator', 'manager', 'admin') ? h('a', { class: 'btn', href: '#/review/new' }, '+ New Review') : null),
    stats,
    h('h2', null, 'Needs your action'),
    d.action.length ? reviewTable(d.action) : h('div', { class: 'card empty' }, 'Nothing needs your action right now.'),
    can('reviewer', 'manager', 'admin') ? h('p', null, h('a', { href: '#/approvals' }, 'View all approvals')) : null,
    h('h2', { class: 'mt' }, 'Recent reviews'), recentBox);
}

function reviewTable(list) {
  return h('div', { class: 'tablewrap' }, h('table', null,
    h('thead', null, h('tr', null, ['Title', 'Channel', 'Status', 'Open findings', 'Updated'].map((x) => h('th', null, x)))),
    h('tbody', null, list.map((r) => h('tr', { class: 'click', tabindex: 0, onclick: () => (location.hash = '#/review/' + r.id),
      onkeydown: (e) => { if (e.key === 'Enter') location.hash = '#/review/' + r.id; } },
    h('td', null, h('b', null, r.title), h('div', { class: 'small muted' }, 'by ' + r.creator_name)),
    h('td', null, r.channel), h('td', null, statusBadge(r.status)),
    h('td', null, r.open_findings, r.high ? h('span', { class: 'badge High', style: 'margin-left:6px' }, r.high + ' High') : null),
    h('td', null, fmtDate(r.updated_at)))))));
}

/* ============================================================ 4. Knowledge Base */
const KN_TABS = [['guideline', 'Guidelines'], ['glossary', 'Glossary'], ['fact', 'Approved facts'], ['claim', 'Approved claims'], ['colour', 'Brand colours and logo']];
const RULE_KEYS = [['', 'None (used by AI tone check only)'], ['max_exclaim', 'Max exclamation marks (value = limit)'], ['no_caps', 'No ALL CAPS words'],
  ['max_sentence', 'Max words per sentence (value = limit)'], ['min_readability', 'Min reading-ease score (value = target)'],
  ['alt_required', 'Images need alt text'], ['min_contrast', 'Min contrast ratio (value = ratio)']];

function knFields(kind) {
  const sev = ['select', ['High', 'Medium', 'Low']];
  const map = {
    guideline: [['title', 'Title', 'text'], ['body', 'Rule text', 'textarea'], ['severity', 'Severity', ...sev],
      ['category', 'Category', 'select', ['Tone', 'Terminology', 'Messaging', 'Visual', 'Accessibility']],
      ['extra', 'Automatic check (optional)', 'select', RULE_KEYS], ['value', 'Limit or target (number, optional)', 'text']],
    glossary: [['title', 'Preferred term', 'text'], ['body', 'Variants to replace (comma separated)', 'textarea'], ['source', 'Note', 'text']],
    fact: [['title', 'Fact text', 'textarea'], ['value', 'Approved value (a number is checked automatically)', 'text'],
      ['category', 'Topic keywords (comma separated, e.g. languages,language)', 'text'], ['source', 'Source name', 'text'],
      ['extra', 'Last verified (YYYY-MM-DD)', 'text'], ['severity', 'Severity', ...sev]],
    claim: [['title', 'Claim wording (e.g. fastest)', 'text'], ['extra', 'Status', 'select', ['Allowed', 'Needs proof', 'Forbidden']],
      ['value', 'Safer wording to suggest', 'text'], ['source', 'Proof link or name', 'text'], ['severity', 'Severity', ...sev]],
    colour: [['title', 'Name', 'text'], ['value', 'Hex colour (#RRGGBB) or pixel width', 'text'],
      ['extra', 'Type', 'select', [['', 'Palette colour'], ['min_logo', 'Minimum logo width (px)']]], ['body', 'Note', 'text']],
  };
  return map[kind];
}

function knDetails(it) {
  switch (it.kind) {
    case 'guideline': return [h('span', { class: 'chip' }, it.category), h('span', { class: 'chip' }, it.severity), it.extra ? h('span', { class: 'chip' }, 'auto: ' + it.extra + (it.value ? '=' + it.value : '')) : null, h('div', null, it.body)];
    case 'glossary': return ['Replace: ' + it.body];
    case 'fact': return ['Value ' + it.value + ' · topics: ' + (it.category || '-') + ' · source: ' + (it.source || '-') + (it.extra ? ' · verified ' + it.extra : '')];
    case 'claim': return [h('span', { class: 'chip' }, it.extra || 'Needs proof'), ' safer: ' + (it.value || '-') + (it.source ? ' · proof: ' + it.source : '')];
    default: return [it.extra === 'min_logo' ? 'Minimum logo width ' + it.value + ' px' : h('span', null, h('span', { style: 'display:inline-block;width:14px;height:14px;border-radius:4px;vertical-align:middle;margin-right:6px;background:' + (/^#[0-9a-f]{3,6}$/i.test(it.value) ? it.value : '#ccc') }), it.value)];
  }
}

async function pageKnowledge(_m, q) {
  let kind = KN_TABS.some(([k]) => k === q.kind) ? q.kind : 'guideline';
  let data = await api('/knowledge');
  const editable = can('manager', 'admin');
  const area = h('div');
  const side = h('div');
  let preview = null;

  async function reload() { data = await api('/knowledge'); draw(); }

  function openForm(item) {
    const defs = knFields(kind);
    const inputs = {};
    const nodes = defs.map(([name, label, type, opts]) => {
      let el;
      if (type === 'textarea') el = h('textarea', { value: item ? item[name] : '' });
      else if (type === 'select') el = h('select', null, opts.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v, selected: (item ? item[name] : (name === 'severity' ? 'Medium' : opts[0] && (Array.isArray(opts[0]) ? opts[0][0] : opts[0]))) === v }, l); }));
      else el = h('input', { type: 'text', value: item ? item[name] : '' });
      el.id = 'kf-' + name; inputs[name] = el;
      return h('div', null, h('label', { class: 'f', for: 'kf-' + name }, label), el);
    });
    const status = h('select', { id: 'kf-status' }, [['active', 'Active (used in checks)'], ['draft', 'Draft (not used yet)']].map(([v, l]) => h('option', { value: v, selected: (item ? item.status : 'active') === v }, l)));
    const conf = h('input', { type: 'checkbox', id: 'kf-conf', checked: item ? !!item.confidential : false });
    const err = h('div', { class: 'err', role: 'alert' });
    const save = h('button', { class: 'btn', type: 'button', onclick: async () => {
      err.textContent = '';
      const body = { kind, status: status.value, confidential: conf.checked };
      for (const [n, el] of Object.entries(inputs)) body[n] = el.value;
      try {
        await api(item ? '/knowledge/' + item.id : '/knowledge', { method: item ? 'PUT' : 'POST', body });
        side.replaceChildren(); toast('Saved'); await reload();
      } catch (e) { err.textContent = e.message; }
    } }, 'Save');
    side.replaceChildren(h('div', { class: 'drawer', role: 'dialog', 'aria-label': 'Item form' },
      h('h2', null, (item ? 'Edit ' + item.code : 'Add item')), nodes,
      h('div', null, h('label', { class: 'f', for: 'kf-status' }, 'Status'), status),
      h('label', { class: 'f' }, conf, ' Confidential (never sent to external AI)'),
      err, h('div', { class: 'actions mt' }, save, h('button', { class: 'btn ghost', type: 'button', onclick: () => side.replaceChildren() }, 'Cancel'))));
  }

  async function onImport(file) {
    const b64 = await fileToB64(file);
    const r = await api('/knowledge/import', { method: 'POST', body: { filename: file.name, data_b64: b64 } });
    preview = r.rules; draw();
  }

  function draw() {
    const items = data.items.filter((i) => i.kind === kind);
    const tabs = h('div', { class: 'tabs', role: 'tablist' }, KN_TABS.map(([k, l]) => h('button', { class: 'tab', role: 'tab', type: 'button', 'aria-selected': kind === k ? 'true' : 'false',
      onclick: () => { kind = k; preview = null; draw(); } }, l)));
    const fileInput = h('input', { type: 'file', accept: '.docx,.pdf,.md,.txt', style: 'display:none', id: 'kn-file',
      onchange: (e) => { const f = e.target.files[0]; if (f) guard(() => onImport(f)); e.target.value = ''; } });
    const toolbar = editable ? h('div', { class: 'row mb' },
      kind === 'guideline' ? h('button', { class: 'btn ghost', type: 'button', onclick: () => fileInput.click() }, 'Import guideline file') : null,
      h('button', { class: 'btn', type: 'button', onclick: () => openForm(null) }, '+ Add item'), fileInput,
      h('span', { class: 'grow' }),
      h('span', { class: 'muted small' }, data.version ? 'Published version: ' + data.version : 'Not published yet'),
      h('button', { class: 'btn good', type: 'button', onclick: () => guard(async () => { const r = await api('/knowledge/publish', { method: 'POST' }); toast('Version ' + r.version + ' published'); await reload(); }) }, 'Publish version'))
      : h('p', { class: 'muted' }, 'You can read the Knowledge Base. Managers and admins edit it.');
    const prev = preview ? h('div', { class: 'card mb' }, h('h3', null, 'Preview: ' + preview.length + ' rules found'),
      h('ol', null, preview.slice(0, 40).map((r) => h('li', null, r.body))), preview.length > 40 ? h('p', { class: 'small muted' }, '…and ' + (preview.length - 40) + ' more') : null,
      h('div', { class: 'actions' },
        h('button', { class: 'btn', type: 'button', onclick: () => guard(async () => { await api('/knowledge/bulk', { method: 'POST', body: { kind: 'guideline', items: preview } }); preview = null; toast('Rules saved as Draft. Activate them with Edit.'); await reload(); }) }, 'Save all rules'),
        h('button', { class: 'btn ghost', type: 'button', onclick: () => { preview = null; draw(); } }, 'Discard'))) : null;
    const table = items.length ? h('div', { class: 'tablewrap' }, h('table', null,
      h('thead', null, h('tr', null, ['Code', 'Title', 'Details', 'Status', 'Confidential', editable ? 'Actions' : ''].map((x) => h('th', null, x)))),
      h('tbody', null, items.map((it) => h('tr', null,
        h('td', null, h('b', null, it.code)), h('td', null, it.kind === 'fact' ? it.title : it.title), h('td', null, knDetails(it)),
        h('td', null, h('span', { class: 'badge' }, it.status)),
        h('td', null, editable ? h('input', { type: 'checkbox', checked: !!it.confidential, 'aria-label': 'Confidential ' + it.code,
          onchange: (e) => guard(async () => { await api('/knowledge/' + it.id, { method: 'PUT', body: { confidential: e.target.checked } }); toast('Updated'); await reload(); }) }) : (it.confidential ? 'Yes' : 'No')),
        editable ? h('td', null, h('div', { class: 'actions' },
          h('button', { class: 'btn ghost sm', type: 'button', onclick: () => openForm(it) }, 'Edit'),
          h('button', { class: 'btn danger sm', type: 'button', onclick: () => modal({ title: 'Archive ' + it.code + '?', body: h('p', null, 'It will stop being used in checks. History is kept.'),
            buttons: [{ label: 'Archive', cls: 'danger', onclick: async () => { await api('/knowledge/' + it.id + '/archive', { method: 'POST' }); toast('Archived'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] }) }, 'Archive'))) : null))))) : h('div', { class: 'card empty' }, 'Nothing here yet.');
    area.replaceChildren(...[tabs, toolbar, prev, table].filter(Boolean));
  }
  draw();
  if (q.edit && editable) {
    const it = data.items.find((i) => i.code === q.edit);
    if (it) { kind = it.kind; draw(); openForm(it); }
  }
  return shell('/knowledge', h('h1', null, 'Knowledge Base'), area, side);
}

/* ============================================================ 5. New Review */
async function pageNewReview() {
  if (!can('creator', 'manager', 'admin')) return shell('/review/new', denied());
  const title = h('input', { type: 'text', id: 'nr-title', maxlength: 200 });
  const channel = h('select', { id: 'nr-channel' }, ['Social post', 'Email', 'Web page', 'Press release'].map((x) => h('option', { value: x }, x)));
  const audience = h('select', { id: 'nr-aud' }, ['Customers', 'Students', 'Investors', 'Internal'].map((x) => h('option', { value: x }, x)));
  let ctype = 'text'; let imageFile = null;
  const text = h('textarea', { id: 'nr-text', style: 'min-height:200px' });
  const textBox = h('div'), imgBox = h('div');
  const conf = h('input', { type: 'checkbox', id: 'nr-conf' });
  const confNote = h('div', { class: 'notice', style: 'display:none' }, 'AI model checks are off for this item. Only rule-based checks will run.');
  conf.addEventListener('change', () => { confNote.style.display = conf.checked ? '' : 'none'; });
  const docFile = h('input', { type: 'file', accept: '.docx,.pdf,.md,.txt', style: 'display:none', onchange: (e) => {
    const f = e.target.files[0]; if (!f) return;
    guard(async () => { const r = await api('/extract', { method: 'POST', body: { filename: f.name, data_b64: await fileToB64(f) } }); text.value = r.text; toast('Text extracted. Check it, then run the check.'); });
    e.target.value = '';
  } });
  const imgInput = h('input', { type: 'file', accept: '.png,.jpg,.jpeg,.gif,.webp', id: 'nr-img', onchange: (e) => { imageFile = e.target.files[0] || null; } });
  const alt = h('input', { type: 'text', id: 'nr-alt' }), cap = h('textarea', { id: 'nr-cap' });
  const tcol = h('input', { type: 'text', id: 'nr-tc', placeholder: '#222222' }), bcol = h('input', { type: 'text', id: 'nr-bc', placeholder: '#FFFFFF' });
  const logo = h('input', { type: 'number', id: 'nr-logo', min: 0, placeholder: 'e.g. 140' });
  const progress = h('div', { style: 'display:none' });
  const err = h('div', { class: 'err', role: 'alert' });

  function drawType() {
    textBox.replaceChildren(ctype === 'text' ? h('div', null, field('Your text', text),
      h('button', { class: 'link small', type: 'button', onclick: () => docFile.click() }, 'Upload DOCX / PDF instead'), docFile) : '');
    imgBox.replaceChildren(ctype === 'image' ? h('div', null, field('Image file', imgInput), field('Alt text', alt), field('Caption (also checked as text)', cap),
      h('div', { class: 'row' }, h('div', { class: 'grow' }, field('Text colour on the image (hex)', tcol)), h('div', { class: 'grow' }, field('Background colour (hex)', bcol)), h('div', { class: 'grow' }, field('Logo width (px)', logo)))) : '');
  }
  const radios = h('div', { class: 'row' }, [['text', 'Text'], ['image', 'Image']].map(([v, l]) => h('label', null, h('input', { type: 'radio', name: 'ctype', value: v, checked: v === 'text', onchange: () => { ctype = v; drawType(); } }), ' ' + l)));
  drawType();

  function payload(draft) {
    const d = { title: title.value, channel: channel.value, audience: audience.value, content_type: ctype, confidential: conf.checked, draft };
    if (ctype === 'text') d.content_text = text.value;
    else Object.assign(d, { alt_text: alt.value, caption: cap.value, text_color: tcol.value, bg_color: bcol.value, logo_width: Number(logo.value || 0) });
    return d;
  }
  async function submit(draft, btn) {
    err.textContent = '';
    if (!title.value.trim()) { err.textContent = 'Enter a title.'; title.focus(); return; }
    btn.disabled = true;
    const steps = ['Rules', 'Claims', 'Tone', 'Accessibility'];
    let timer;
    try {
      const d = payload(draft);
      if (ctype === 'image' && imageFile) { d.image_b64 = await fileToB64(imageFile); d.image_name = imageFile.name; }
      if (!draft) {
        const bar = h('i'); let n = 0;
        const list = h('ul', { class: 'plain steps' }, steps.map((s) => h('li', null, s)));
        progress.style.display = ''; progress.replaceChildren(h('div', { class: 'progress' }, bar), list);
        const tick = () => { n = Math.min(n + 1, steps.length); bar.style.width = (n / (steps.length + 1) * 100) + '%'; [...list.children].forEach((li, i) => li.className = i < n ? 'on' : ''); };
        tick(); timer = setInterval(tick, 450);
      }
      const r = await api('/reviews', { method: 'POST', body: d });
      location.hash = draft ? '#/dashboard' : '#/review/' + r.id;
    } catch (e) { err.textContent = e.message; progress.style.display = 'none'; }
    finally { clearInterval(timer); btn.disabled = false; }
  }
  const run = h('button', { class: 'btn', type: 'button', onclick: (e) => submit(false, e.currentTarget) }, 'Run check');
  const draftBtn = h('button', { class: 'btn ghost', type: 'button', onclick: (e) => submit(true, e.currentTarget) }, 'Save as draft');
  const cancel = h('button', { class: 'btn ghost', type: 'button', onclick: () => modal({ title: 'Discard this draft?', body: h('p', null, 'Nothing has been saved.'),
    buttons: [{ label: 'Discard', cls: 'danger', onclick: () => { location.hash = '#/dashboard'; } }, { label: 'Keep editing', cls: 'ghost' }] }) }, 'Cancel');
  return shell('/review/new', h('h1', null, 'New Review'),
    h('div', { class: 'card', style: 'max-width:820px' },
      field('Title', title),
      h('div', { class: 'row' }, h('div', { class: 'grow' }, field('Channel', channel)), h('div', { class: 'grow' }, field('Audience', audience))),
      h('label', { class: 'f' }, 'Content type'), radios, textBox, imgBox,
      h('label', { class: 'f' }, conf, ' This content is confidential'), confNote, progress, err,
      h('div', { class: 'actions mt' }, run, draftBtn, cancel)));
}

/* ============================================================ 7. Approvals */
async function pageApprovals(_m, q) {
  if (!can('reviewer', 'manager', 'admin')) return shell('/approvals', denied());
  let tab = q.tab || 'waiting';
  const box = h('div');
  const chan = h('select', { 'aria-label': 'Channel' }, [['', 'All channels'], 'Social post', 'Email', 'Web page', 'Press release'].map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v }, l); }));
  const sev = h('select', { 'aria-label': 'Severity' }, [['', 'Any severity'], ['high', 'Has High findings']].map(([v, l]) => h('option', { value: v }, l)));
  let rows = [];
  function drawRows() {
    let list = rows.filter((r) => (!chan.value || r.channel === chan.value) && (!sev.value || r.high > 0));
    box.replaceChildren(list.length ? h('div', { class: 'tablewrap' }, h('table', null,
      h('thead', null, h('tr', null, ['Title', 'Creator', 'Channel', 'High findings', 'Submitted'].map((x) => h('th', null, x)))),
      h('tbody', null, list.map((r) => h('tr', { class: 'click', tabindex: 0, onclick: () => (location.hash = '#/review/' + r.id), onkeydown: (e) => { if (e.key === 'Enter') location.hash = '#/review/' + r.id; } },
        h('td', null, h('b', null, r.title)), h('td', null, r.creator_name), h('td', null, r.channel), h('td', null, r.high), h('td', null, fmtDate(r.submitted_at || r.updated_at))))))) : h('div', { class: 'card empty' }, 'Nothing here.'));
    return list;
  }
  async function load() { rows = (await api('/approvals?tab=' + tab)).rows; drawRows(); }
  const tabs = h('div');
  function drawTabs() {
    tabs.replaceChildren(h('div', { class: 'tabs', role: 'tablist' }, [['waiting', 'Waiting for me'], ['changes', 'Changes requested'], ['approved', 'Recently approved']].map(([k, l]) =>
      h('button', { class: 'tab', role: 'tab', type: 'button', 'aria-selected': tab === k ? 'true' : 'false', onclick: () => guard(async () => { tab = k; drawTabs(); await load(); }) }, l))));
  }
  drawTabs(); chan.addEventListener('change', drawRows); sev.addEventListener('change', drawRows);
  await load();
  const next = h('button', { class: 'btn', type: 'button', onclick: () => {
    const list = rows.slice().sort((a, b) => String(a.submitted_at || a.updated_at).localeCompare(String(b.submitted_at || b.updated_at)));
    if (!list.length) return toast('Nothing is waiting.');
    location.hash = '#/review/' + list[0].id;
  } }, 'Open next');
  return shell('/approvals', h('div', { class: 'row between mb' }, h('h1', null, 'Approvals'), next), tabs, h('div', { class: 'row mb' }, chan, sev), box);
}

/* ============================================================ 8. Insights */
async function pageInsights() {
  if (!can('manager', 'admin')) return shell('/insights', denied());
  const range = h('select', { 'aria-label': 'Date range' }, [['7', 'Last 7 days'], ['30', 'Last 30 days'], ['', 'All time']].map(([v, l]) => h('option', { value: v, selected: v === '' }, l)));
  const out = h('div');
  async function load() {
    const d = await api('/insights' + (range.value ? '?days=' + range.value : ''));
    const max = Math.max(1, ...d.top.map((t) => t.total));
    const bars = d.top.length ? h('div', { class: 'bars' }, d.top.map((t) => h('div', { class: 'bar' }, h('button', { type: 'button', title: 'Show reviews', onclick: () => guard(async () => {
      const rs = await api('/insights/code/' + encodeURIComponent(t.code));
      modal({ title: 'Reviews where ' + t.code + ' was flagged', body: rs.length ? h('ul', null, rs.map((r) => h('li', null, h('a', { href: '#/review/' + r.id, onclick: () => (document.getElementById('modal-root').replaceChildren()) }, r.title), ' ', statusBadge(r.status)))) : h('p', null, 'None.') });
    }) }, h('span', { class: 'l' }, h('b', null, t.code), ' ' + t.title), h('i', { style: 'width:' + Math.max(4, t.total / max * 100) + '%' }), h('b', null, t.total))))) : h('div', { class: 'empty' }, 'No findings in this period.');
    const dis = d.dismissed.length ? h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Rule', 'Dismissed', 'Rate'].map((x) => h('th', null, x)))),
      h('tbody', null, d.dismissed.map((p) => h('tr', null, h('td', null, h('b', null, p.code), ' ' + p.title), h('td', null, p.dismissed + ' of ' + p.total), h('td', null, p.rate + '%')))))) : h('div', { class: 'empty' }, 'No dismissals yet.');
    const unc = d.unclear.length ? h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Rule', 'Marked unclear', ''].map((x) => h('th', null, x)))),
      h('tbody', null, d.unclear.map((p) => h('tr', null, h('td', null, h('b', null, p.code), ' ' + p.title), h('td', null, p.unclear + ' times'),
        h('td', null, h('a', { class: 'btn sm', href: '#/knowledge?kind=guideline&edit=' + encodeURIComponent(p.code) }, 'Improve this rule'))))))) : h('div', { class: 'empty' }, 'No unclear rules detected.');
    out.replaceChildren(
      h('div', { class: 'stats' },
        h('div', { class: 'card' }, h('b', { style: 'font-size:1.8rem' }, d.avg_hours == null ? '-' : d.avg_hours + ' h'), h('div', { class: 'muted' }, 'Average time from submit to approval')),
        h('div', { class: 'card' }, h('b', { style: 'font-size:1.8rem' }, d.avg_rounds == null ? '-' : d.avg_rounds), h('div', { class: 'muted' }, 'Average versions (review rounds) per item')),
        h('div', { class: 'card' }, h('b', { style: 'font-size:1.8rem' }, d.reviews), h('div', { class: 'muted' }, 'Reviews in this period'))),
      h('div', { class: 'card mb' }, h('div', { class: 'row between' }, h('h2', null, 'Top repeated issues'),
        h('button', { class: 'btn ghost sm', type: 'button', onclick: () => downloadCSV('top-issues.csv', [['Rule', 'Title', 'Flagged', 'Dismissed', 'Dismiss rate %', 'Marked unclear']].concat(d.top.map((t) => [t.code, t.title, t.total, t.dismissed, t.rate, t.unclear]))) }, 'Export CSV')), bars),
      h('h2', null, 'Most dismissed rules'), dis,
      h('h2', { class: 'mt' }, 'Unclear guideline alerts'), unc,
      h('p', { class: 'small muted mt' }, 'Insights show counts only. They never show draft content to people who cannot open that review.'));
  }
  range.addEventListener('change', () => guard(load));
  await load();
  return shell('/insights', h('div', { class: 'row between mb' }, h('h1', null, 'Insights'), range), out);
}

/* ============================================================ 9. Settings */
async function pageSettings(_m, q) {
  let tab = q.tab || 'team';
  const body = h('div');
  const tabs = h('div');
  async function drawTeam() {
    const users = await api('/settings/users');
    const admin = can('admin');
    const name = h('input', { type: 'text', 'aria-label': 'Name' }), mail = h('input', { type: 'email', 'aria-label': 'Email' });
    const role = h('select', { 'aria-label': 'Role' }, ['creator', 'reviewer', 'manager', 'admin'].map((r) => h('option', { value: r }, r)));
    body.replaceChildren(
      admin ? h('div', { class: 'card mb' }, h('h3', null, 'Invite user'), h('div', { class: 'row' }, h('div', { class: 'grow' }, name), h('div', { class: 'grow' }, mail), role,
        h('button', { class: 'btn', type: 'button', onclick: () => guard(async () => {
          const r = await api('/settings/users', { method: 'POST', body: { name: name.value, email: mail.value, role: role.value } });
          modal({ title: 'Invite created', body: h('p', null, 'Give this temporary password to ', h('b', null, mail.value), ': ', h('code', null, r.temp_password), '. It is shown only once.') });
          await drawTeam();
        }) }, 'Send invite'))) : h('p', { class: 'muted' }, 'Only admins can change the team.'),
      h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Name', 'Email', 'Role', admin ? 'Actions' : ''].map((x) => h('th', null, x)))),
        h('tbody', null, users.map((u) => h('tr', null, h('td', null, u.name), h('td', null, u.email),
          h('td', null, admin ? h('select', { 'aria-label': 'Role for ' + u.name, onchange: (e) => guard(async () => { await api('/settings/users/' + u.id, { method: 'PUT', body: { role: e.target.value } }); toast('Role changed'); await drawTeam(); }) },
            ['creator', 'reviewer', 'manager', 'admin'].map((r) => h('option', { value: r, selected: r === u.role }, r))) : u.role),
          admin ? h('td', null, h('button', { class: 'btn danger sm', type: 'button', disabled: u.id === S.user.id, onclick: () => modal({ title: 'Remove ' + u.name + '?', body: h('p', null, 'They will no longer be able to sign in.'),
            buttons: [{ label: 'Remove', cls: 'danger', onclick: async () => { await api('/settings/users/' + u.id, { method: 'DELETE' }); toast('Removed'); await drawTeam(); } }, { label: 'Cancel', cls: 'ghost' }] }) }, 'Remove')) : null))))));
  }
  async function drawAI() {
    const a = await api('/settings/ai');
    const sw = h('input', { type: 'checkbox', id: 'ai-sw', checked: a.allow_ai, disabled: !can('admin') });
    body.replaceChildren(
      h('div', { class: 'tablewrap mb' }, h('table', null, h('thead', null, h('tr', null, ['Model or service', 'Purpose', 'Data sent', 'Confidential items', 'Status'].map((x) => h('th', null, x)))),
        h('tbody', null, a.services.map((s) => h('tr', null, h('td', null, h('b', null, s.name)), h('td', null, s.purpose), h('td', null, s.data_sent), h('td', null, s.confidential), h('td', null, h('span', { class: 'badge ' + (s.active ? 'approved' : '') }, s.note || (s.active ? 'Active' : 'Off')))))))),
      h('div', { class: 'card' }, h('label', null, sw, ' Allow external AI for non-confidential items'),
        h('p', { class: 'small muted' }, 'When this is off, every check is rule-based only. Confidential items never use external AI either way.'),
        can('admin') ? h('button', { class: 'btn', type: 'button', onclick: () => guard(async () => { await api('/settings/ai', { method: 'PUT', body: { allow_ai: sw.checked } }); toast('Settings saved'); await drawAI(); }) }, 'Save settings') : h('p', { class: 'small muted' }, 'Only admins can change this.')));
  }
  async function drawAudit() {
    if (!can('admin', 'manager')) { body.replaceChildren(h('div', { class: 'card empty' }, 'Only admins and managers can see the audit log.')); return; }
    const users = await api('/settings/users');
    const sel = h('select', { 'aria-label': 'Filter by user' }, [h('option', { value: '' }, 'All users')].concat(users.map((u) => h('option', { value: u.id }, u.name))));
    const tbl = h('div');
    let rows = [];
    async function load() { rows = (await api('/audit' + (sel.value ? '?user=' + sel.value : ''))).rows;
      tbl.replaceChildren(rows.length ? h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Time', 'User', 'Action', 'Item', 'Detail'].map((x) => h('th', null, x)))),
        h('tbody', null, rows.map((r) => h('tr', null, h('td', null, fmtDate(r.created_at)), h('td', null, r.user_name || '-'), h('td', null, r.action), h('td', null, r.target_type ? r.target_type + ' #' + (r.target_id ?? '') : ''), h('td', null, r.detail)))))) : h('div', { class: 'empty' }, 'No entries.')); }
    sel.addEventListener('change', () => guard(load));
    body.replaceChildren(h('div', { class: 'row mb' }, sel, h('button', { class: 'btn ghost', type: 'button', onclick: () => downloadCSV('audit-log.csv', [['Time', 'User', 'Action', 'Item', 'Detail']].concat(rows.map((r) => [r.created_at, r.user_name, r.action, r.target_type + ' ' + (r.target_id ?? ''), r.detail]))) }, 'Export CSV')), tbl);
    await load();
  }
  const draw = { team: drawTeam, ai: drawAI, audit: drawAudit };
  function drawTabs() {
    tabs.replaceChildren(h('div', { class: 'tabs', role: 'tablist' }, [['team', 'Team'], ['ai', 'AI and data'], ['audit', 'Audit log']].map(([k, l]) =>
      h('button', { class: 'tab', role: 'tab', type: 'button', 'aria-selected': tab === k ? 'true' : 'false', onclick: () => guard(async () => { tab = k; drawTabs(); await draw[k](); }) }, l))));
  }
  drawTabs(); await draw[tab]();
  return shell('/settings', h('h1', null, 'Settings'), tabs, body);
}

/* ============================================================ router */
const ROUTES = [
  [/^\/$/, pageLanding, false], [/^\/login$/, pageLogin, false],
  [/^\/privacy$/, () => pageText('Privacy', ['BrandSure stores your workspace data on the server you run it on. Confidential items are never sent to external AI services.', 'This is a demo project text. Replace it with your real policy.']), false],
  [/^\/terms$/, () => pageText('Terms', ['This is a demo project text. Replace it with your real terms.']), false],
  [/^\/dashboard$/, pageDashboard, true], [/^\/knowledge$/, pageKnowledge, true], [/^\/review\/new$/, pageNewReview, true],
  [/^\/review\/(\d+)$/, (m, q) => pageReport(Number(m[1]), q), true],
  [/^\/approvals$/, pageApprovals, true], [/^\/insights$/, pageInsights, true], [/^\/settings$/, pageSettings, true],
];

let renderToken = 0;
async function render() {
  const my = ++renderToken;
  const { path, q } = parseHash();
  const app = document.getElementById('app');
  document.getElementById('modal-root').replaceChildren();
  for (const [re, fn, needAuth] of ROUTES) {
    const m = path.match(re);
    if (!m) continue;
    if (needAuth && !S.token) { location.hash = '#/login'; return; }
    try {
      const node = await fn(m, q);
      if (my !== renderToken) return;
      app.replaceChildren(node);
      window.scrollTo(0, 0);
      document.title = 'BrandSure';
    } catch (e) {
      if (my !== renderToken) return;
      app.replaceChildren(S.token && S.user ? shell('', h('div', { class: 'card' }, h('h2', null, 'Something went wrong'), h('p', null, e.message), h('button', { class: 'btn', onclick: render }, 'Try again')))
        : h('div', { class: 'auth-wrap' }, h('div', { class: 'auth-card' }, h('p', null, e.message))));
    }
    return;
  }
  location.hash = '#/';
}
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
