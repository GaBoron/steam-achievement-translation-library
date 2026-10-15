import { el } from './elements.js';

let nextId = 0;

/** A visible, single-choice facet. Native radios retain their keyboard model. */
export function createFilterGroup({ label, options, value, onChange, className = '' }) {
  const name = `catalog-filter-${++nextId}`;
  const choices = el('div', { className: 'filter-options' });
  const node = el('fieldset', { className: `filter-group ${className}` }, el('legend', {}, label), choices);
  let selected = value;
  let inputs = [];

  function setValue(value) {
    selected = value;
    inputs.forEach(input => { input.checked = input.value === value; });
  }

  function setOptions(options) {
    inputs = [];
    choices.replaceChildren();
    for (const [value, label] of options) {
      const input = el('input', { type: 'radio', name, value, onchange: () => {
        if (!input.checked) return;
        selected = value;
        onChange(value);
      } });
      inputs.push(input);
      choices.append(el('label', { className: 'filter-option' }, input, el('span', {}, label)));
    }
    setValue(selected);
  }

  setOptions(options);
  return { node, setValue, setOptions };
}
