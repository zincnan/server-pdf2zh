'use strict';

// The native select remains the form value used by preferences and task uploads.
class LanguagePicker {
  static opened = null;

  constructor(select) {
    this.select = select;
    this.languages = [];
    this.filtered = [];
    this.activeIndex = -1;
    const label = document.querySelector(`label[for="${select.id}"]`);
    const name = label.textContent;
    this.wrapper = document.createElement('div');
    this.wrapper.className = 'language-picker';
    this.trigger = document.createElement('button');
    this.trigger.type = 'button';
    this.trigger.id = select.id + '-trigger';
    this.trigger.className = 'language-trigger';
    this.trigger.setAttribute('role', 'combobox');
    this.trigger.setAttribute('aria-haspopup', 'dialog');
    this.trigger.setAttribute('aria-expanded', 'false');
    this.text = document.createElement('span');
    this.trigger.append(this.text);
    label.htmlFor = this.trigger.id;

    this.menu = document.createElement('div');
    this.menu.id = select.id + '-menu';
    this.menu.className = 'language-menu';
    this.menu.setAttribute('role', 'dialog');
    this.menu.setAttribute('aria-label', '选择' + name);
    this.menu.hidden = true;
    this.trigger.setAttribute('aria-controls', this.menu.id);
    this.search = document.createElement('input');
    this.search.type = 'text';
    this.search.autocomplete = 'off';
    this.search.spellcheck = false;
    this.search.placeholder = '搜索语言或代码';
    this.search.setAttribute('aria-label', '搜索' + name);
    this.search.setAttribute('role', 'combobox');
    this.search.setAttribute('aria-autocomplete', 'list');
    this.search.setAttribute('aria-expanded', 'true');
    this.list = document.createElement('div');
    this.list.id = select.id + '-options';
    this.list.className = 'language-options';
    this.list.setAttribute('role', 'listbox');
    this.list.setAttribute('aria-label', name + '候选项');
    this.search.setAttribute('aria-controls', this.list.id);
    this.empty = document.createElement('p');
    this.empty.className = 'language-empty';
    this.empty.textContent = '没有匹配的语言';
    this.empty.setAttribute('role', 'status');
    this.empty.hidden = true;
    this.menu.append(this.search, this.list, this.empty);
    select.before(this.wrapper);
    this.wrapper.append(this.trigger, this.menu, select);
    select.hidden = true;

    this.trigger.addEventListener('click', () => this.menu.hidden ? this.open() : this.close(true));
    this.trigger.addEventListener('keydown', (event) => {
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault(); this.open();
        if (event.key === 'Home') this.activate(0);
        if (event.key === 'End') this.activate(this.filtered.length - 1);
      }
    });
    this.search.addEventListener('input', () => this.render(true));
    this.search.addEventListener('keydown', (event) => {
      if (event.isComposing) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (this.filtered.length) this.activate((this.activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + this.filtered.length) % this.filtered.length);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (this.filtered[this.activeIndex]) this.choose(this.filtered[this.activeIndex].code);
      } else if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); this.close(true);
      } else if (event.key === 'Tab') this.close(true);
    });
    this.wrapper.addEventListener('focusout', (event) => {
      if (!this.wrapper.contains(event.relatedTarget)) this.close();
    });
    document.addEventListener('pointerdown', (event) => {
      if (!this.wrapper.contains(event.target)) this.close();
    });
    select.addEventListener('change', () => this.sync());
    window.addEventListener('resize', () => this.position());
    window.visualViewport?.addEventListener('resize', () => this.position());
    document.addEventListener('scroll', (event) => {
      if (event.target !== this.list) this.position();
    }, true);
  }

  setOptions(languages) {
    this.close();
    this.languages = languages;
    this.select.replaceChildren(...languages.map((language) => new Option(language.label, language.code)));
    this.sync();
  }

  sync() {
    const language = this.languages.find((entry) => entry.code === this.select.value);
    this.text.textContent = language?.label || '请选择语言';
    this.trigger.title = language?.label || '';
    this.trigger.disabled = this.select.disabled;
  }

  open() {
    if (this.trigger.disabled || !this.languages.length) return;
    LanguagePicker.opened?.close();
    LanguagePicker.opened = this;
    this.search.value = '';
    this.menu.hidden = false;
    this.trigger.setAttribute('aria-expanded', 'true');
    this.render(); this.position(); this.search.focus({preventScroll: true});
  }

  close(restoreFocus = false) {
    if (this.menu.hidden) return;
    this.menu.hidden = true;
    this.trigger.setAttribute('aria-expanded', 'false');
    if (LanguagePicker.opened === this) LanguagePicker.opened = null;
    if (restoreFocus) this.trigger.focus({preventScroll: true});
  }

  position() {
    if (this.menu.hidden) return;
    const rect = this.trigger.getBoundingClientRect();
    const viewport = window.visualViewport;
    const top = viewport?.offsetTop || 0;
    const bottom = top + (viewport?.height || window.innerHeight);
    if (rect.bottom < top || rect.top > bottom) {this.close(); return;}
    const above = rect.top - top - 12, below = bottom - rect.bottom - 12;
    const upwards = below < 180 && above > below;
    this.menu.classList.toggle('above', upwards);
    this.menu.style.maxHeight = Math.max(80, Math.min(320, upwards ? above : below)) + 'px';
    if (this.filtered.length) this.activate(this.activeIndex);
  }

  render(reset = false) {
    const query = this.search.value.trim().toLocaleLowerCase();
    this.filtered = this.languages.filter((language) => language.label.toLocaleLowerCase().includes(query) || language.code.toLowerCase().includes(query));
    this.list.replaceChildren(...this.filtered.map((language) => {
      const option = document.createElement('div');
      option.id = this.select.id + '-option-' + language.code;
      option.className = 'language-option';
      option.textContent = language.label;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(language.code === this.select.value));
      option.addEventListener('pointerdown', (event) => event.preventDefault());
      option.addEventListener('click', () => this.choose(language.code));
      return option;
    }));
    this.empty.hidden = this.filtered.length > 0;
    this.list.scrollTop = 0;
    const selected = reset ? 0 : this.filtered.findIndex((language) => language.code === this.select.value);
    this.activate(Math.max(0, selected));
  }

  activate(index) {
    this.activeIndex = index;
    Array.from(this.list.children).forEach((option, i) => option.classList.toggle('active', i === index));
    const active = this.list.children[index];
    if (active) {
      this.search.setAttribute('aria-activedescendant', active.id);
      // Scroll the option list only; scrollIntoView could move the whole page.
      if (active.offsetTop < this.list.scrollTop) this.list.scrollTop = active.offsetTop;
      else if (active.offsetTop + active.offsetHeight > this.list.scrollTop + this.list.clientHeight) this.list.scrollTop = active.offsetTop + active.offsetHeight - this.list.clientHeight;
    } else this.search.removeAttribute('aria-activedescendant');
  }

  choose(code) {
    this.select.value = code;
    this.select.dispatchEvent(new Event('change', {bubbles: true}));
    this.close(true);
  }
}
