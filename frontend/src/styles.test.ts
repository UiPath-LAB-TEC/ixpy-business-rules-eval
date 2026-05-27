import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, test } from 'vitest';

const styles = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

function cssBlock(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = styles.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`));
  if (!match) throw new Error(`Missing CSS block for ${selector}`);
  return match[1];
}

describe('review page layout styles', () => {
  test('keeps the document viewer narrower than the rule evidence pane', () => {
    const reviewLayout = cssBlock('.review-layout');
    const columns = reviewLayout.match(/grid-template-columns:\s*minmax\((\d+)px,\s*var\(--review-viewer-width,\s*(\d+)%\)\)\s*(\d+)px\s*minmax\((\d+)px,\s*1fr\)/);

    expect(columns).not.toBeNull();
    const [, viewerMinimum, defaultViewerWidth, resizerWidth, rulesMinimum] = columns!;

    expect(Number(viewerMinimum)).toBeLessThanOrEqual(420);
    expect(Number(defaultViewerWidth)).toBeLessThan(50);
    expect(Number(resizerWidth)).toBeGreaterThanOrEqual(10);
    expect(Number(rulesMinimum)).toBeGreaterThanOrEqual(520);
  });

  test('lets the viewer and rules panes shrink inside the review grid', () => {
    const panels = cssBlock('.viewer-panel, .rule-panel');

    expect(panels).toContain('min-width: 0');
  });

  test('collapses the far-left app navigation by default sizing contract', () => {
    const collapsedShell = cssBlock('.app-shell.sidebar-collapsed');
    const hiddenSidebarText = cssBlock('.sidebar-collapsed .brand span, .sidebar-collapsed .nav-item span');

    expect(collapsedShell).toContain('grid-template-columns: 72px 1fr');
    expect(hiddenSidebarText).toContain('display: none');
  });

  test('wraps dense rule evidence tables instead of widening the pane', () => {
    const ruleTables = cssBlock('.rule-panel table');
    const ruleCells = cssBlock('.rule-panel th, .rule-panel td');

    expect(ruleTables).toContain('table-layout: fixed');
    expect(ruleCells).toContain('overflow-wrap: anywhere');
  });

  test('exposes a draggable divider between the document viewer and rules pane', () => {
    const resizer = cssBlock('.review-resizer');

    expect(resizer).toContain('cursor: col-resize');
    expect(resizer).toContain('touch-action: none');
  });
});
