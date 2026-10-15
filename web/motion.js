/** Content updates stay synchronous; animation never delays state or focus. */
import { append } from './elements.js';

const active = new WeakMap();
const easing = 'cubic-bezier(0.2, 0, 0, 1)';
const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export function animateChange(node) {
  active.get(node)?.cancel();
  if (reduced() || typeof node.animate !== 'function') return;
  const animation = node.animate([
    { opacity: 0, transform: 'translateY(6px)' },
    { opacity: 1, transform: 'translateY(0)' },
  ], { duration: 200, easing });
  active.set(node, animation);
  animation.finished.catch(() => {}).finally(() => {
    if (active.get(node) === animation) active.delete(node);
  });
}

export function replaceContent(node, ...children) {
  node.replaceChildren();
  append(node, ...children);
  animateChange(node);
}

export function transitionTheme(update) {
  if (!reduced() && typeof document.startViewTransition === 'function') {
    const transition = document.startViewTransition(update);
    transition.finished.catch(() => {});
  } else update();
}

export function bindDisclosure(details) {
  const summary = details.querySelector('summary');
  const content = summary?.nextElementSibling;
  if (!summary || !content) return () => {};
  let wanted = details.open;
  let animation;
  let generation = 0;
  const toggle = async event => {
    event.preventDefault();
    wanted = !wanted;
    const version = ++generation;
    const height = details.open ? content.getBoundingClientRect().height : 0;
    const opacity = details.open ? Number.parseFloat(getComputedStyle(content).opacity) : 0;
    animation?.cancel();
    if (reduced() || typeof content.animate !== 'function') {
      details.open = wanted;
      content.style.overflow = '';
      return;
    }
    details.open = true;
    content.style.overflow = 'hidden';
    animation = content.animate([
      { height: `${height}px`, opacity },
      { height: `${wanted ? content.scrollHeight : 0}px`, opacity: wanted ? 1 : 0 },
    ], { duration: 200, easing, fill: 'both' });
    try { await animation.finished; } catch { /* A newer toggle owns the panel. */ }
    if (version !== generation) return;
    details.open = wanted;
    animation.cancel();
    content.style.overflow = '';
  };
  summary.addEventListener('click', toggle);
  return () => {
    generation++;
    animation?.cancel();
    summary.removeEventListener('click', toggle);
    content.style.overflow = '';
  };
}
