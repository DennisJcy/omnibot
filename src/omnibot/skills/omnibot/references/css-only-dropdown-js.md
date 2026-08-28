# CSS-Only Dropdown JavaScript Recipe

Use only after semantic find, refs, selectors, DOM, and mouse fallback cannot expose or select the dropdown option.

Example for a visible trigger like `按留言时间排序` and a target option text:

```js
const triggerText = '按留言时间排序';
const optionText = '目标选项文本';

const visibleElements = [...document.querySelectorAll('button, [role="button"], [aria-haspopup], div, span, li')]
  .filter((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
  });

const byExactText = (text) => visibleElements.find((el) => el.textContent?.trim() === text);
const trigger = byExactText(triggerText);
if (!trigger) {
  return { ok: false, reason: 'trigger-not-found', triggerText, optionText };
}

trigger.click();
await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

const option = [...document.querySelectorAll('div, span, li, button, [role="option"], [role="menuitem"]')]
  .filter((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
  })
  .find((el) => el.textContent?.trim() === optionText);

if (!option) {
  return { ok: false, reason: 'option-not-found-after-trigger-click', triggerText, optionText };
}

option.click();
await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

return {
  ok: true,
  triggerText,
  optionText,
  selectedText: trigger.textContent?.trim(),
};
```

Verify with page state after running the script: selected label, sorted result order, result count, URL/query state, or another user-visible condition.
