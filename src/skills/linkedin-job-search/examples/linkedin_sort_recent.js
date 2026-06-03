// Click feed "Sort by" and choose "Recent" — standard DOM only (no Playwright selectors).
(() => {
  const sortBtn = document.querySelector(
    'button[aria-label*="Sort"], button[aria-label*="sort"], [data-test-sort-toggle]'
  );
  if (sortBtn) {
    sortBtn.click();
    const recent = Array.from(document.querySelectorAll('button, [role="menuitem"], li'))
      .find((el) => /recent/i.test(el.textContent || ''));
    if (recent) {
      recent.click();
      return { sorted: true, method: 'menu' };
    }
  }
  return { sorted: false, hint: 'Adjust selectors for current LinkedIn DOM' };
})()
