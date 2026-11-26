// Step panels: show one field group at a time. Without JS every panel stays visible.
document.querySelectorAll('[data-steps]').forEach(root => {
  const form = root.closest('form');
  const tabs = [...root.querySelectorAll('[data-step-tab]')];
  const panels = [...root.querySelectorAll('[data-step-panel]')];
  if (!form || !tabs.length || tabs.length !== panels.length) return;
  const fieldsOf = panel => [...panel.querySelectorAll('input, select')];
  const panelValid = panel => fieldsOf(panel).every(field => field.checkValidity());
  let current = 0;

  function refresh(markErrors) {
    panels.forEach((panel, i) => {
      const valid = panelValid(panel);
      tabs[i].classList.toggle('is-complete', valid);
      if (markErrors || valid) tabs[i].classList.toggle('has-error', !valid);
    });
  }

  function show(index, focusTab) {
    current = Math.max(0, Math.min(index, panels.length - 1));
    panels.forEach((panel, i) => { panel.hidden = i !== current; });
    tabs.forEach((tab, i) => {
      const selected = i === current;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    if (focusTab) tabs[current].focus();
  }

  root.classList.add('is-enhanced');
  // Hidden panels cannot show native validation bubbles, so validate on submit ourselves.
  form.noValidate = true;
  tabs.forEach((tab, i) => tab.addEventListener('click', () => show(i)));
  root.querySelector('.step-tabs').addEventListener('keydown', event => {
    const moves = { ArrowRight: 1, ArrowLeft: -1, Home: -current, End: panels.length };
    if (!(event.key in moves)) return;
    event.preventDefault();
    show(current + moves[event.key], true);
  });
  root.querySelectorAll('[data-step-prev]').forEach(button => button.addEventListener('click', () => show(current - 1)));
  root.querySelectorAll('[data-step-next]').forEach(button => button.addEventListener('click', () => {
    const invalid = fieldsOf(panels[current]).find(field => !field.checkValidity());
    if (invalid) { refresh(true); invalid.reportValidity(); return; }
    show(current + 1);
    panels[current].querySelector('input, select')?.focus();
  }));
  form.addEventListener('input', () => refresh(false));
  form.addEventListener('change', () => refresh(false));
  form.addEventListener('submit', event => {
    if (event.submitter?.formNoValidate || form.checkValidity()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    refresh(true);
    const invalid = form.querySelector(':invalid:not(fieldset)');
    const panel = invalid && invalid.closest('[data-step-panel]');
    if (panel) show(panels.indexOf(panel));
    if (invalid) invalid.reportValidity();
  });

  refresh(false);
  show(0);
});

// Result tabs: show one result view at a time. Without JS every view stays visible.
document.querySelectorAll('[data-tabs]').forEach(root => {
  const tabs = [...root.querySelectorAll('[data-tab]')];
  const panels = [...root.querySelectorAll('[data-tab-panel]')];
  if (!tabs.length || tabs.length !== panels.length) return;
  let current = 0;
  function show(index, focusTab) {
    current = (index + tabs.length) % tabs.length;
    panels.forEach((panel, i) => { panel.hidden = i !== current; });
    tabs.forEach((tab, i) => {
      tab.setAttribute('aria-selected', String(i === current));
      tab.tabIndex = i === current ? 0 : -1;
    });
    if (focusTab) tabs[current].focus();
  }
  root.classList.add('is-enhanced');
  tabs.forEach((tab, i) => tab.addEventListener('click', () => show(i)));
  root.querySelector('[role="tablist"]').addEventListener('keydown', event => {
    const moves = { ArrowRight: current + 1, ArrowLeft: current - 1, Home: 0, End: tabs.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    show(moves[event.key], true);
  });
  show(0);
});

// Preserve user control over whether entries are fictional or user supplied.
// Native form validation and server validation both remain active.
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', event => {
    const submitter = event.submitter;
    const skipsValidation = submitter?.formNoValidate;
    if (!skipsValidation && !form.checkValidity()) return;
    const button = submitter || form.querySelector('button[type="submit"]');
    if (!button) return;
    // A disabled submitter is not sent, so keep its name/value (e.g. action=import) in a hidden copy.
    if (button.name) {
      const copy = document.createElement('input');
      copy.type = 'hidden'; copy.name = button.name; copy.value = button.value;
      form.appendChild(copy);
    }
    button.textContent = button.dataset.busyLabel || (skipsValidation ? '불러오는 중…' : '계산 중…');
    button.disabled = true;
  });
});

// Industry -> suggested start-up costs (01). The select carries {industry: {field: value}} as JSON.
document.querySelectorAll('[data-suggest-source]').forEach(select => {
  const form = select.closest('form');
  let table = {};
  try { table = JSON.parse(select.dataset.suggestSource); } catch (e) { return; }
  const fill = () => {
    const values = table[select.value] || {};
    Object.entries(values).forEach(([name, value]) => {
      const input = form.elements[name];
      if (input) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); }
    });
  };
  select.addEventListener('change', fill);
  form.querySelectorAll('[data-suggest-fill]').forEach(button => button.addEventListener('click', fill));
});

// Money inputs: show the amount in 만 원 / 억 원 under the field so long numbers are easy to read.
function readableWon(value) {
  const n = Number(value);
  if (!value || !isFinite(n) || n < 10000) return '';
  const eok = Math.floor(n / 1e8), man = Math.round((n % 1e8) / 1e4);
  return '= ' + [eok ? eok.toLocaleString('ko-KR') + '억' : '', man ? man.toLocaleString('ko-KR') + '만' : ''].filter(Boolean).join(' ') + ' 원';
}
document.querySelectorAll('input[data-money]').forEach(input => {
  const hint = document.createElement('small');
  hint.className = 'money-hint';
  hint.setAttribute('aria-live', 'polite');
  input.insertAdjacentElement('afterend', hint);
  const update = () => { hint.textContent = readableWon(input.value); };
  input.addEventListener('input', update);
  update();
});

// Chip buttons that fill a text field (e.g. pick a dish in 02).
document.querySelectorAll('[data-fill-target]').forEach(button => {
  const target = document.getElementById(button.dataset.fillTarget);
  if (!target) return;
  const mark = () => document.querySelectorAll(`[data-fill-target="${button.dataset.fillTarget}"]`)
    .forEach(b => b.classList.toggle('is-selected', b.dataset.fillValue === target.value));
  button.addEventListener('click', () => { target.value = button.dataset.fillValue; target.dispatchEvent(new Event('input', { bubbles: true })); mark(); });
  target.addEventListener('input', mark);
  mark();
});

// 03: picking a menu fills its volume and a starting price from 02 and shows its ingredient cost.
document.querySelectorAll('[data-dish-info]').forEach(select => {
  let info = {};
  try { info = JSON.parse(select.dataset.dishInfo); } catch (e) { return; }
  const form = select.closest('form');
  const tag = form.querySelector('[data-dish-cost]');
  select.addEventListener('change', () => {
    const d = info[select.value];
    if (!d) return;
    if (form.elements.volume) form.elements.volume.value = d.volume;
    if (form.elements.price) { form.elements.price.value = d.price; form.elements.price.dispatchEvent(new Event('input', { bubbles: true })); }
    if (tag) tag.textContent = `← 02 재료비 관리 · 1인분 재료비 ${d.cost}원`;
  });
});
