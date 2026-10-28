/* Page 6: Review Report. Left = content with highlights, right = findings, bottom = comments, history, approval. */

const STATE_LABEL = { open: '', fixed: 'Fixed', dismissed: 'Dismissed', escalated: 'Waiting for reviewer', cleared: 'Cleared by reviewer', overridden: 'Overridden by manager' };

async function pageReport(rid, q) {
  let data = await api('/reviews/' + rid + (q.version ? '?version=' + encodeURIComponent(q.version) : ''));
  let selected = null;
  let editing = false;
  const root = h('div');

  async function reload(version) {
    data = await api('/reviews/' + rid + (version ? '?version=' + version : ''));
    editing = false; draw();
  }
  const select = (fid) => { selected = fid; paintSelection(); const card = root.querySelector('.fcard[data-fid="' + fid + '"]'); if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
  function paintSelection() {
    root.querySelectorAll('.fcard').forEach((c) => c.classList.toggle('sel', Number(c.dataset.fid) === selected));
    root.querySelectorAll('mark.hl').forEach((m) => m.classList.toggle('sel', Number(m.dataset.fid) === selected));
  }
  const isOpen = (f) => f.state === 'open' || f.state === 'escalated';

  // ---------- content with highlights (positions are in Unicode code points)
  function contentNode() {
    const v = data.version, r = data.review;
    const text = v.content_text || '';
    const chars = Array.from(text);
    const spans = data.findings.filter((f) => f.start_pos >= 0 && f.end_pos > f.start_pos).sort((a, b) => a.start_pos - b.start_pos);
    const nodes = []; let pos = 0;
    for (const f of spans) {
      if (f.start_pos < pos) continue;
      nodes.push(chars.slice(pos, f.start_pos).join(''));
      const cls = (f.verdict === 'unverified' ? 'unverified' : f.severity) + (isOpen(f) ? '' : ' done');
      nodes.push(h('mark', { class: 'hl ' + cls, 'data-fid': f.id, tabindex: 0, title: f.severity + ': ' + f.why, onclick: () => select(f.id), onkeydown: (e) => { if (e.key === 'Enter') select(f.id); } }, chars.slice(f.start_pos, f.end_pos).join('')));
      pos = f.end_pos;
    }
    nodes.push(chars.slice(pos).join(''));
    if (r.content_type === 'image') {
      return h('div', null,
        v.image_path ? h('img', { class: 'imgprev', alt: v.alt_text || 'Uploaded image (no alt text provided)', src: '/api/uploads/' + encodeURIComponent(v.image_path) + '?t=' + encodeURIComponent(S.token) }) : null,
        h('p', { class: 'small muted mt' }, 'Alt text: ', v.alt_text || '(none)', ' · Text colour: ', v.text_color || '-', ' · Background: ', v.bg_color || '-', ' · Logo width: ', v.logo_width ? v.logo_width + ' px' : '-'),
        h('h3', null, 'Caption'), h('div', { class: 'doc' }, nodes));
    }
    return h('div', { class: 'doc' }, nodes);
  }

  function editorNode() {
    const r = data.review, v = data.version;
    const ta = h('textarea', { style: 'min-height:220px', value: v.content_text, 'aria-label': r.content_type === 'image' ? 'Caption' : 'Content text' });
    const extra = {};
    let imgFile = null;
    const imgFields = r.content_type === 'image' ? h('div', null,
      field('Replace image (optional)', h('input', { type: 'file', accept: '.png,.jpg,.jpeg,.gif,.webp', onchange: (e) => { imgFile = e.target.files[0] || null; } })),
      field('Alt text', (extra.alt_text = h('input', { type: 'text', value: v.alt_text }))),
      h('div', { class: 'row' }, h('div', { class: 'grow' }, field('Text colour', (extra.text_color = h('input', { type: 'text', value: v.text_color })))),
        h('div', { class: 'grow' }, field('Background colour', (extra.bg_color = h('input', { type: 'text', value: v.bg_color })))),
        h('div', { class: 'grow' }, field('Logo width (px)', (extra.logo_width = h('input', { type: 'number', value: v.logo_width }))))) ) : null;
    return h('div', null, ta, imgFields, h('div', { class: 'actions mt' },
      h('button', { class: 'btn', type: 'button', onclick: () => guard(async () => {
        const body = r.content_type === 'image' ? { caption: ta.value } : { content_text: ta.value };
        for (const [k, el] of Object.entries(extra)) body[k] = k === 'logo_width' ? Number(el.value || 0) : el.value;
        if (imgFile) { body.image_b64 = await fileToB64(imgFile); body.image_name = imgFile.name; }
        const res = await api('/reviews/' + rid + '/versions', { method: 'POST', body });
        toast('Saved as version ' + res.version + '. Checks re-run.');
        await reload();
      }) }, 'Save new version'),
      h('button', { class: 'btn ghost', type: 'button', onclick: () => { editing = false; draw(); } }, 'Cancel')));
  }

  // ---------- modals
  function sourceDrawer(f) {
    const s = f.source;
    modal({ title: f.source_code === 'NONE' ? 'No approved source' : 'Source ' + s.code,
      body: s ? h('div', null, h('p', null, h('span', { class: 'chip' }, s.kind), ' ', h('b', null, s.title)), s.body ? h('p', null, s.body) : null,
        s.value ? h('p', null, 'Value: ', h('b', null, s.value)) : null, s.source ? h('p', { class: 'small muted' }, 'Source: ' + s.source) : null, s.extra ? h('p', { class: 'small muted' }, 'Setting: ' + s.extra) : null)
        : h('p', null, 'No approved guideline, fact or claim supports this text. Add proof to the Knowledge Base, rephrase, or ask a reviewer.') });
  }
  function editFix(f) {
    const inp = h('input', { type: 'text', value: f.suggestion || '' });
    modal({ title: 'Edit fix', body: h('div', null, h('p', null, h('del', null, f.quote), ' → your wording:'), inp),
      buttons: [{ label: 'Apply', onclick: async () => { const r = await api('/findings/' + f.id + '/edit', { method: 'POST', body: { text: inp.value } }); toast('Fixed. Now version ' + r.version + '.'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] });
  }
  function dismiss(f) {
    const reason = h('select', null, [['', 'Choose a reason...'], 'Not applicable', 'Rule is unclear', 'Approved exception', 'Other'].map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v }, l); }));
    const note = h('textarea', { placeholder: 'Optional note' });
    modal({ title: 'Dismiss this finding', body: h('div', null, field('Reason (required)', reason), field('Note', note)),
      buttons: [{ label: 'Confirm', cls: 'danger', onclick: async () => { await api('/findings/' + f.id + '/dismiss', { method: 'POST', body: { reason: reason.value, note: note.value } }); toast('Dismissed'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] });
  }
  async function escalate(f) {
    const revs = await api('/reviewers');
    const who = h('select', null, revs.map((r) => h('option', { value: r.id }, r.name + ' (' + r.role + ')')));
    const note = h('textarea', { placeholder: 'What should the reviewer check?' });
    modal({ title: 'Escalate to a reviewer', body: h('div', null, field('Reviewer', who), field('Note', note)),
      buttons: [{ label: 'Send', onclick: async () => { await api('/findings/' + f.id + '/escalate', { method: 'POST', body: { reviewer_id: Number(who.value), note: note.value } }); toast('Sent to reviewer'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] });
  }
  function noteModal(title, label, path, f, okLabel, cls) {
    const t = h('textarea');
    modal({ title, body: field(label, t), buttons: [{ label: okLabel, cls, onclick: async () => { await api(path, { method: 'POST', body: { note: t.value, justification: t.value } }); toast('Saved'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] });
  }
  function checksModal() {
    modal({ title: 'What was checked (version ' + data.version.number + ')', wide: true,
      body: h('div', null, h('p', { class: 'small muted' }, data.ai_used ? 'An AI model was used for part of this report. Its citations were re-checked in code.' : 'No AI model was used for this report. All findings are rule-based.'),
        h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Check', 'Type', 'Result', 'Details'].map((x) => h('th', null, x)))),
          h('tbody', null, data.checks.map((c) => h('tr', null, h('td', null, c.check_name), h('td', null, h('span', { class: 'badge ' + c.check_type }, c.check_type === 'ai' ? 'AI' : 'Rule-based')),
            h('td', null, h('span', { class: 'badge ' + (c.status === 'ok' ? 'approved' : c.status === 'failed' ? 'High' : '') }, c.status === 'ok' ? 'Ran' : c.status === 'failed' ? 'Could not run' : 'Skipped')), h('td', null, c.message)))))),
        h('p', { class: 'small muted' }, 'Knowledge version used: ' + (data.review.knowledge_version || 'unpublished set'))) });
  }
  function compareModal() {
    const vs = data.versions;
    const a = h('select', null, vs.map((n) => h('option', { value: n, selected: n === Math.max(1, vs[vs.length - 1] - 1) }, 'v' + n)));
    const b = h('select', null, vs.map((n) => h('option', { value: n, selected: n === vs[vs.length - 1] }, 'v' + n)));
    const out = h('div', { class: 'diffbox doc', style: 'min-height:80px' }, 'Choose two versions and click Compare.');
    async function run() { const d = await api('/reviews/' + rid + '/diff?a=' + a.value + '&b=' + b.value);
      out.replaceChildren(...d.ops.map((o) => o.t === 'eq' ? document.createTextNode(o.s) : h(o.t === 'del' ? 'del' : 'ins', null, o.s))); }
    modal({ title: 'Compare versions', wide: true, body: h('div', null, h('div', { class: 'row mb' }, 'From', a, 'to', b, h('button', { class: 'btn sm', type: 'button', onclick: () => guard(run) }, 'Compare')), out),
      buttons: [{ label: 'Close', cls: 'ghost' }] });
    guard(run);
  }
  function approve() {
    const high = data.unresolved_high;
    if (high && can('reviewer')) { toast('High findings are still open. Only a manager can approve with an override.', true); return; }
    const t = h('textarea', { placeholder: 'Reason for approving with open High findings' });
    const note = h('textarea', { placeholder: 'Optional note' });
    modal({ title: 'Approve version ' + data.version.number, body: h('div', null, high ? h('div', { class: 'notice' }, high + ' High finding(s) are still open. An override reason is required and will be saved in the audit log.') : h('p', null, 'This locks the version.'),
      high ? field('Override reason (required)', t) : null, field('Note', note)),
      buttons: [{ label: 'Approve', cls: 'good', onclick: async () => { await api('/reviews/' + rid + '/approve', { method: 'POST', body: { override_reason: t.value, note: note.value } }); toast('Approved and locked'); await reload(); } }, { label: 'Cancel', cls: 'ghost' }] });
  }

  // ---------- finding card
  function findingCard(f) {
    const r = data.review, latest = data.is_latest;
    const open = isOpen(f);
    const commentsFor = data.comments.filter((c) => c.finding_id === f.id);
    const thread = h('div', { style: 'display:none' });
    function drawThread() {
      const box = h('textarea', { placeholder: 'Write a comment', 'aria-label': 'Comment on finding' });
      thread.replaceChildren(h('ul', { class: 'plain thread' }, commentsFor.map((c) => h('li', null, h('b', null, c.author), ' ', h('span', { class: 'muted small' }, fmtDate(c.created_at)), h('div', null, c.body)))), box,
        h('button', { class: 'btn sm', type: 'button', onclick: () => guard(async () => { await api('/comments', { method: 'POST', body: { review_id: rid, finding_id: f.id, body: box.value } }); toast('Posted'); await reload(data.version.number); }) }, 'Post'));
    }
    drawThread();
    const acts = [];
    if (latest && data.can_work && f.state === 'open') {
      if (f.suggestion && f.start_pos >= 0) acts.push(h('button', { class: 'btn sm good', type: 'button', onclick: () => guard(async () => { const res = await api('/findings/' + f.id + '/accept', { method: 'POST' }); toast('Fixed. Now version ' + res.version + '.'); await reload(); }) }, 'Accept fix'));
      if (f.start_pos >= 0) acts.push(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editFix(f) }, 'Edit fix'));
      acts.push(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => dismiss(f) }, 'Dismiss'));
      acts.push(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => guard(() => escalate(f)) }, 'Escalate'));
    }
    if (latest && f.state === 'escalated' && can('reviewer', 'manager', 'admin')) acts.push(h('button', { class: 'btn sm good', type: 'button', onclick: () => noteModal('Mark this finding OK', 'Your note (required)', '/findings/' + f.id + '/clear', f, 'Mark OK', 'good') }, 'Mark OK'));
    if (latest && open && f.severity === 'High' && can('manager', 'admin') && r.status !== 'approved') acts.push(h('button', { class: 'btn sm danger', type: 'button', onclick: () => noteModal('Override this finding', 'Written justification (required)', '/findings/' + f.id + '/override', f, 'Override', 'danger') }, 'Override finding'));
    acts.push(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { thread.style.display = thread.style.display === 'none' ? '' : 'none'; } }, 'Comment' + (commentsFor.length ? ' (' + commentsFor.length + ')' : '')));
    return h('div', { class: 'fcard ' + f.severity + (open ? '' : ' done'), 'data-fid': f.id, onclick: (e) => { if (!e.target.closest('button,a,textarea')) select(f.id); } },
      h('div', { class: 'row' }, h('span', { class: 'badge ' + f.severity }, f.severity), h('span', { class: 'badge' }, f.type),
        (f.verdict === 'unverified' || f.verdict === 'contradicted') ? h('span', { class: 'badge ' + (f.verdict === 'unverified' ? 'unverified' : 'High') }, f.verdict === 'unverified' ? 'Unverified' : 'Contradicted') : null,
        f.state !== 'open' ? h('span', { class: 'badge approved' }, STATE_LABEL[f.state] || f.state) : null,
        f.needs_reviewer ? h('span', { class: 'badge in_review' }, 'Reviewer should confirm') : null),
      f.quote ? h('p', null, h('span', { class: 'quote' }, f.quote)) : null,
      h('p', null, h('b', null, 'Why: '), f.why),
      h('p', { class: 'small' }, h('b', null, 'Source: '), f.source_code === 'NONE' ? h('span', { class: 'muted' }, 'No approved source found')
        : h('button', { class: 'link', type: 'button', onclick: () => sourceDrawer(f) }, f.source_code + (f.source ? ' ' + f.source.title : ''))),
      h('p', { class: 'small' }, h('b', null, 'Confidence: '), f.confidence, ' · ', h('span', { class: 'badge ' + f.check_type }, f.check_type === 'ai' ? 'AI check' : 'Rule-based')),
      f.suggestion ? h('div', { class: 'diffbox' }, f.start_pos >= 0 ? [h('del', null, f.quote), ' → ', h('ins', null, f.suggestion)] : ['Suggestion: ', h('ins', null, f.suggestion)]) : h('div', { class: 'small muted' }, 'No automatic fix. Edit the content or escalate.'),
      f.state === 'dismissed' || f.state === 'cleared' || f.state === 'overridden' ? h('p', { class: 'small muted' }, (f.dismiss_reason || '') + (f.dismiss_note ? ': ' + f.dismiss_note : '')) : null,
      f.state === 'escalated' ? h('p', { class: 'small muted' }, 'Sent to ' + (f.escalated_name || 'a reviewer') + (f.escalate_note ? ': ' + f.escalate_note : '')) : null,
      h('div', { class: 'actions' }, acts), thread);
  }

  // ---------- page
  function draw() {
    const r = data.review, v = data.version;
    const vsel = h('select', { 'aria-label': 'Version', onchange: (e) => guard(() => reload(e.target.value)) }, data.versions.map((n) => h('option', { value: n, selected: n === v.number }, 'v' + n + (n === data.versions[data.versions.length - 1] ? ' (latest)' : ''))));
    const canSubmit = data.is_latest && data.can_work && ['checked', 'changes_requested'].includes(r.status);
    const strip = h('div', { class: 'strip' },
      h('h1', { style: 'margin:0' }, r.title), statusBadge(r.status),
      r.confidential ? h('span', { class: 'badge High' }, 'Confidential') : null,
      h('span', { class: 'muted small' }, r.channel + ' · ' + r.audience + ' · by ' + r.creator_name), h('span', { class: 'grow' }),
      vsel,
      data.versions.length > 1 ? h('button', { class: 'btn ghost sm', type: 'button', onclick: compareModal }, 'Compare versions') : null,
      h('button', { class: 'link', type: 'button', onclick: checksModal }, 'What was checked'),
      data.is_latest && data.can_work && !editing ? h('button', { class: 'btn ghost sm', type: 'button', onclick: () => { editing = true; draw(); } }, 'Edit content') : null,
      canSubmit ? h('button', { class: 'btn sm', type: 'button', disabled: r.status === 'draft', onclick: () => guard(async () => { await api('/reviews/' + rid + '/submit', { method: 'POST' }); toast('Submitted for approval'); location.hash = '#/dashboard'; }) }, 'Submit for approval') : null);
    const banners = [];
    if (!data.is_latest) banners.push(h('div', { class: 'notice' }, 'You are viewing version ' + v.number + ', which is read-only. ', h('button', { class: 'link', type: 'button', onclick: () => guard(() => reload()) }, 'Go to latest version')));
    if (r.status === 'approved') banners.push(h('div', { class: 'notice', style: 'background:#e9f8f0;border-color:#9bd6b8' }, 'Approved and locked. Create a new review to change this content.'));
    if (r.confidential) banners.push(h('div', { class: 'notice' }, 'Confidential item: no external AI service is used for this review.'));
    if (r.status === 'draft') banners.push(h('div', { class: 'notice' }, 'This is a draft with no checks yet. Use Edit content and Save new version to run the check.'));
    if (data.unresolved_high > 0 && data.is_latest) banners.push(h('div', { class: 'notice' }, data.unresolved_high + ' High finding(s) must be fixed, dismissed with a reason, or overridden by a manager before this can be submitted.'));

    const findings = data.findings.length ? data.findings.map(findingCard) : [h('div', { class: 'card empty' }, 'No findings. This version passed all checks that ran.')];
    const gen = data.comments.filter((c) => !c.finding_id);
    const cbox = h('textarea', { placeholder: 'Write a comment', 'aria-label': 'General comment' });
    const approvalPanel = (r.status === 'in_review' && can('reviewer', 'manager', 'admin')) ? h('div', { class: 'card mb' }, h('h3', null, 'Decision'),
      h('div', { class: 'actions' }, h('button', { class: 'btn good', type: 'button', onclick: approve }, 'Approve'),
        h('button', { class: 'btn danger', type: 'button', onclick: () => noteModal('Request changes', 'What should change? (required)', '/reviews/' + rid + '/request-changes', null, 'Request changes', 'danger') }, 'Request changes'))) : null;
    const record = r.status === 'approved' ? h('a', { class: 'btn ghost sm', href: '/api/reviews/' + rid + '/approval-record.pdf?t=' + encodeURIComponent(S.token) }, 'Export approval record') : null;

    // Approve/Request changes modals post to /reviews/.. paths; noteModal posts to '/reviews/..' via api()
    root.replaceChildren(strip, ...banners,
      h('div', { class: 'report' },
        h('div', { class: 'card' }, h('h3', null, 'Content'), editing ? editorNode() : contentNode()),
        h('div', null, h('h3', null, 'Findings (' + data.findings.length + ')'), findings)),
      h('div', { class: 'report mt' },
        h('div', null, approvalPanel,
          h('div', { class: 'card' }, h('h3', null, 'Comments'),
            h('ul', { class: 'plain thread' }, gen.length ? gen.map((c) => h('li', null, h('b', null, c.author), ' ', h('span', { class: 'muted small' }, fmtDate(c.created_at)), h('div', null, c.body))) : h('li', { class: 'muted' }, 'No comments yet.')),
            cbox, h('button', { class: 'btn sm', type: 'button', onclick: () => guard(async () => { await api('/comments', { method: 'POST', body: { review_id: rid, body: cbox.value } }); toast('Posted'); await reload(v.number); }) }, 'Post'))),
        h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h3', null, 'History'), record),
          h('ul', { class: 'plain history' }, data.history.map((x) => h('li', null, h('b', null, x.author || 'System'), ' ', x.action.replace(/_/g, ' '), ' ', h('span', { class: 'muted small' }, fmtDate(x.created_at)), x.detail ? h('div', { class: 'small muted' }, x.detail) : null))))));
    paintSelection();
  }
  draw();
  return shell('/dashboard', root);
}
