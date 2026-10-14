import { el } from './elements.js';
import { animateChange } from './motion.js';

/** Panels stay mounted so preview choices and pending requests survive a tab switch. */
export function createDetailTabs({ label, panels, initial = 'downloads' }) {
  let selected = Math.max(0, panels.findIndex(panel => panel.id === initial));
  const buttons = panels.map(({ id, label }, index) => el('button', {
    type: 'button', role: 'tab', id: `${id}-tab`, className: 'project-tab',
    'aria-controls': `${id}-panel`, onclick: () => activate(index),
  }, label));
  const navigation = el('div', { className: 'project-tabs', role: 'tablist', 'aria-label': label,
    onkeydown: event => {
      const current = buttons.indexOf(event.target);
      if (current < 0) return;
      let next;
      if (event.key === 'ArrowRight') next = (current + 1) % buttons.length;
      if (event.key === 'ArrowLeft') next = (current + buttons.length - 1) % buttons.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = buttons.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      activate(next);
      buttons[next].focus();
    },
  }, buttons);

  panels.forEach(({ id, node }) => {
    node.id = `${id}-panel`;
    node.setAttribute('role', 'tabpanel');
    node.setAttribute('aria-labelledby', `${id}-tab`);
    node.tabIndex = 0;
  });

  function update() {
    panels.forEach(({ node }, index) => {
      node.hidden = index !== selected;
      buttons[index].setAttribute('aria-selected', String(index === selected));
      buttons[index].tabIndex = index === selected ? 0 : -1;
    });
  }

  function activate(index) {
    if (index === selected) return;
    selected = index;
    update();
    animateChange(panels[selected].node);
  }

  update();
  return { node: el('div', { className: 'project-content' }, navigation, panels.map(panel => panel.node)),
    get selectedId() { return panels[selected].id; },
    show(id) { const index = panels.findIndex(panel => panel.id === id); if (index >= 0) activate(index); },
  };
}
