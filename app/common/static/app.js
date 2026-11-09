// Step-by-step input for long forms (form[data-wizard]).
// Without JavaScript every step stays visible and the form still submits normally.
function setupWizard(form) {
  const steps = [...form.querySelectorAll('.wizard-step')];
  const progress = form.querySelector('.wizard-progress');
  const nav = form.querySelector('.wizard-nav');
  const submit = form.querySelector('button[type="submit"]');
  if (steps.length < 2 || !progress || !nav || !submit) return;
  const prev = nav.querySelector('[data-wizard-prev]');
  const next = nav.querySelector('[data-wizard-next]');
  const count = nav.querySelector('.wizard-count');
  const gotos = [...progress.querySelectorAll('[data-wizard-goto]')];
  let current = 0;
  let reached = 0;

  const stepValid = (index, report) => {
    for (const input of steps[index].querySelectorAll('input, select')) {
      if (!input.checkValidity()) { if (report) input.reportValidity(); return false; }
    }
    return true;
  };

  const show = (index, focus) => {
    current = index;
    reached = Math.max(reached, index);
    steps.forEach((step, i) => { step.hidden = i !== index; });
    gotos.forEach((button, i) => {
      const item = button.parentElement;
      item.classList.toggle('active', i === index);
      item.classList.toggle('done', i < index);
      button.disabled = i > reached;
      if (i === index) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
    });
    prev.disabled = index === 0;
    const last = index === steps.length - 1;
    next.hidden = last;
    submit.hidden = !last;
    count.textContent = `${index + 1} / ${steps.length} · ${steps[index].dataset.stepTitle}`;
    if (focus) {
      // Steps differ in height: return to the top of the wizard so the new step starts in view.
      if (progress.getBoundingClientRect().top < 0) progress.scrollIntoView({ block: 'start' });
      const first = steps[index].querySelector('input, select');
      if (first) first.focus({ preventScroll: true });
    }
  };

  const advance = () => { if (stepValid(current, true) && current < steps.length - 1) show(current + 1, true); };
  prev.addEventListener('click', () => show(Math.max(0, current - 1), true));
  next.addEventListener('click', advance);
  gotos.forEach((button, i) => button.addEventListener('click', () => { if (i <= reached) show(i, true); }));

  // Enter on an intermediate step moves forward instead of submitting.
  form.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input') && current < steps.length - 1) {
      event.preventDefault();
      advance();
    }
  });
  // Native validation cannot focus fields in hidden steps; open the step that holds the first invalid field.
  submit.addEventListener('click', event => {
    const invalid = steps.findIndex((_, i) => !stepValid(i, false));
    if (invalid >= 0) { event.preventDefault(); reached = Math.max(reached, invalid); show(invalid, false); stepValid(invalid, true); }
  });

  progress.hidden = false;
  nav.hidden = false;
  // After a server-side error the user typically fixes values from the start.
  show(0, false);
}

document.querySelectorAll('form[data-wizard]').forEach(setupWizard);

// Native form validation and server validation both remain active.
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', event => {
    if (event.defaultPrevented || !form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.textContent = '계산 중…'; button.disabled = true; }
  });
});
