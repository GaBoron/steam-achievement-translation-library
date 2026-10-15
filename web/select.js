import { el } from './elements.js';

let nextId = 0;

// DOM focus stays on the combobox; browsing options does not change its value.
// Keyboard model: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/examples/combobox-select-only/
export function createSelect({ label, options, value, onChange, className = '' }) {
  const id = `select-${++nextId}`;
  const labelNode = el('span', { id: `${id}-label`, className: 'select-label' }, label);
  const valueNode = el('span', { id: `${id}-value`, className: 'select-value' });
  const trigger = el('button', {
    type: 'button', className: 'select-trigger', role: 'combobox',
    'aria-haspopup': 'listbox', 'aria-expanded': 'false',
    'aria-controls': `${id}-menu`, 'aria-labelledby': `${id}-label ${id}-value`,
  }, valueNode, el('span', { className: 'select-chevron', 'aria-hidden': 'true' }));
  const menu = el('div', {
    id: `${id}-menu`, className: 'select-menu', role: 'listbox',
    'aria-labelledby': `${id}-label`, hidden: true,
  });
  const node = el('div', { className: `select-field ${className}` }, labelNode, trigger, menu);
  const lifetime = new AbortController();
  let entries = [];
  let optionNodes = [];
  let selectedValue = '';
  let activeIndex = -1;
  let disabled = false;
  let opened = false;
  let disposed = false;
  let openingEvents;
  let animation;
  let typed = '';
  let typingTimer;

  function clearTyping() {
    clearTimeout(typingTimer);
    typed = '';
  }

  function updateSelection() {
    const selectedIndex = entries.findIndex(entry => entry[0] === selectedValue);
    valueNode.textContent = entries[selectedIndex]?.[1] || '';
    optionNodes.forEach((option, index) => {
      option.setAttribute('aria-selected', String(index === selectedIndex));
      option.classList.toggle('is-selected', index === selectedIndex);
    });
  }

  function setActive(index, scroll = true) {
    activeIndex = Math.max(0, Math.min(index, entries.length - 1));
    optionNodes.forEach((option, position) => option.classList.toggle('is-active', position === activeIndex));
    const option = optionNodes[activeIndex];
    if (opened && option) {
      trigger.setAttribute('aria-activedescendant', option.id);
      if (scroll) option.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    }
  }

  function animateMenu(entering) {
    animation?.cancel();
    animation = null;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || !menu.animate) return;
    const frames = [
      { opacity: 0, transform: 'translateY(-4px) scaleY(0.98)' },
      { opacity: 1, transform: 'translateY(0) scaleY(1)' },
    ];
    animation = menu.animate(entering ? frames : frames.reverse(), {
      duration: entering ? 150 : 100, easing: 'cubic-bezier(0.2, 0, 0, 1)',
    });
    return animation;
  }

  function close(commit = false, animated = true) {
    if (!opened) return;
    const nextValue = commit ? entries[activeIndex]?.[0] : selectedValue;
    const changed = nextValue !== undefined && nextValue !== selectedValue;
    if (changed) selectedValue = nextValue;
    opened = false;
    openingEvents?.abort();
    clearTyping();
    trigger.setAttribute('aria-expanded', 'false');
    trigger.removeAttribute('aria-activedescendant');
    menu.setAttribute('aria-hidden', 'true');
    menu.style.pointerEvents = 'none';
    updateSelection();
    const exiting = animated ? animateMenu(false) : (animation?.cancel(), null);
    const hide = () => {
      if (opened || disposed) return;
      menu.hidden = true;
      node.append(menu);
    };
    if (exiting) exiting.finished.then(hide).catch(() => {});
    else hide();
    if (changed) onChange?.(selectedValue);
  }

  function positionMenu() {
    if (!opened) return;
    if (!trigger.isConnected) return close(false, false);
    const bounds = trigger.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = (viewport?.offsetLeft || 0) + 8;
    const top = (viewport?.offsetTop || 0) + 8;
    const right = left + (viewport?.width || document.documentElement.clientWidth) - 16;
    const bottom = top + (viewport?.height || window.innerHeight) - 16;
    if (bounds.bottom < top || bounds.top > bottom || bounds.right < left || bounds.left > right) return close(false, false);
    menu.style.width = `${Math.min(Math.max(bounds.width, 180), right - left)}px`;
    const below = bottom - bounds.bottom - 4;
    const above = bounds.top - top - 4;
    const height = Math.min(menu.scrollHeight, 336);
    const downward = below >= Math.min(height, 240) || below >= above;
    const available = Math.max(0, downward ? below : above);
    if (available < 48) return close(false, false);
    menu.style.maxHeight = `${Math.min(height, available)}px`;
    menu.style.left = `${Math.max(left, Math.min(bounds.left, right - menu.offsetWidth))}px`;
    menu.style.top = `${downward ? bounds.bottom + 4 : bounds.top - 4 - menu.offsetHeight}px`;
    menu.style.transformOrigin = downward ? 'top' : 'bottom';
  }

  function open() {
    if (opened || disposed || trigger.disabled) return;
    animation?.cancel();
    opened = true;
    menu.hidden = false;
    menu.removeAttribute('aria-hidden');
    menu.style.pointerEvents = '';
    document.body.append(menu);
    trigger.setAttribute('aria-expanded', 'true');
    positionMenu();
    if (!opened) return;
    setActive(Math.max(0, entries.findIndex(entry => entry[0] === selectedValue)));
    animateMenu(true);
    openingEvents = new AbortController();
    const signal = openingEvents.signal;
    document.addEventListener('pointerdown', event => {
      if (!node.contains(event.target) && !menu.contains(event.target)) close(true);
    }, { signal });
    document.addEventListener('focusin', event => {
      if (event.target !== trigger && !menu.contains(event.target)) close(true);
    }, { signal });
    document.addEventListener('scroll', event => {
      if (!menu.contains(event.target)) positionMenu();
    }, { capture: true, passive: true, signal });
    window.addEventListener('resize', positionMenu, { passive: true, signal });
    viewportEvents(signal);
  }

  function viewportEvents(signal) {
    window.visualViewport?.addEventListener('resize', positionMenu, { passive: true, signal });
    window.visualViewport?.addEventListener('scroll', positionMenu, { passive: true, signal });
  }

  function typeAhead(character) {
    clearTimeout(typingTimer);
    typed += character.toLocaleLowerCase();
    typingTimer = setTimeout(clearTyping, 650);
    const repeated = [...typed].every(letter => letter === typed[0]);
    const prefix = repeated ? typed[0] : typed;
    const start = repeated ? activeIndex + 1 : 0;
    for (let offset = 0; offset < entries.length; offset++) {
      const index = (start + offset) % entries.length;
      if (entries[index][1].trimStart().toLocaleLowerCase().startsWith(prefix)) {
        setActive(index);
        break;
      }
    }
  }

  function onKeydown(event) {
    if (trigger.disabled || event.ctrlKey || event.metaKey) return;
    const wasOpen = opened;
    if (event.key === 'Tab') {
      close(true);
      return;
    }
    if (event.key === 'Escape') {
      if (opened) event.preventDefault();
      close();
      return;
    }
    if (event.key === 'ArrowUp' && event.altKey && opened) {
      event.preventDefault();
      close(true);
      return;
    }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'PageDown', 'PageUp', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      if (!opened) open();
      if (!opened) return;
      if (event.key === 'Home') setActive(0);
      else if (event.key === 'End') setActive(entries.length - 1);
      else if (event.key === 'ArrowDown' && wasOpen) setActive(activeIndex + 1);
      else if (event.key === 'ArrowUp') setActive(wasOpen ? activeIndex - 1 : 0);
      else if (event.key === 'PageDown') setActive(activeIndex + 10);
      else if (event.key === 'PageUp') setActive(activeIndex - 10);
      else if (wasOpen && (event.key === 'Enter' || event.key === ' ')) close(true);
    } else if (event.key.length === 1 && !event.altKey) {
      event.preventDefault();
      open();
      if (opened) typeAhead(event.key);
    }
  }

  function setValue(nextValue) {
    selectedValue = entries.some(entry => entry[0] === String(nextValue)) ? String(nextValue) : entries[0]?.[0] || '';
    updateSelection();
    if (opened) setActive(entries.findIndex(entry => entry[0] === selectedValue));
  }

  function updateDisabled() {
    trigger.disabled = disabled || !entries.length;
    trigger.setAttribute('aria-disabled', String(trigger.disabled));
    if (trigger.disabled) close(false, false);
  }

  function setOptions(nextOptions) {
    close(false, false);
    const seen = new Set();
    entries = nextOptions.filter(([key]) => {
      const normalized = String(key);
      if (seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    }).map(([key, text, group]) => [String(key), String(text), group ? String(group) : '']);
    optionNodes = [];
    menu.replaceChildren();
    let groupName = '';
    let container = menu;
    entries.forEach(([key, text, group], index) => {
      if (group !== groupName) {
        groupName = group;
        if (group) {
          const headingId = `${id}-group-${index}`;
          container = el('div', { role: 'group', 'aria-labelledby': headingId },
            el('div', { id: headingId, className: 'select-group-label' }, group));
          menu.append(container);
        } else container = menu;
      }
      const option = el('div', {
        id: `${id}-option-${index}`, className: 'select-option', role: 'option',
        'data-option-index': index, 'aria-selected': 'false',
      }, el('span', { className: 'select-option-check', 'aria-hidden': 'true' }), el('span', {}, text));
      optionNodes.push(option);
      container.append(option);
    });
    setValue(selectedValue);
    updateDisabled();
  }

  trigger.addEventListener('click', () => opened ? close() : open(), { signal: lifetime.signal });
  trigger.addEventListener('keydown', onKeydown, { signal: lifetime.signal });
  menu.addEventListener('pointerdown', event => {
    if (event.target.closest('.select-option')) event.preventDefault();
  }, { signal: lifetime.signal });
  menu.addEventListener('click', event => {
    const option = event.target.closest('.select-option');
    if (!opened || !option) return;
    setActive(Number(option.dataset.optionIndex), false);
    close(true);
    if (trigger.isConnected) trigger.focus({ preventScroll: true });
  }, { signal: lifetime.signal });
  setOptions(options);
  setValue(value);

  return {
    node,
    get value() { return selectedValue; },
    setValue,
    setOptions,
    setDisabled(nextDisabled) { disabled = Boolean(nextDisabled); updateDisabled(); },
    focus() { trigger.focus({ preventScroll: true }); },
    dispose() {
      close(false, false);
      disposed = true;
      lifetime.abort();
      animation?.cancel();
      clearTyping();
      menu.remove();
    },
  };
}
