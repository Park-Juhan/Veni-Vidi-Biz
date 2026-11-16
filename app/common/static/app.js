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
    if (form.checkValidity()) return;
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
  form.addEventListener('submit', () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.textContent = '계산 중…'; button.disabled = true; }
  });
});
