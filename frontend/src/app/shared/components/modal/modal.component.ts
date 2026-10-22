import { Component, input, output } from '@angular/core';

/**
 * Reusable modal container (backdrop + header + projected body).
 *
 * A "dumb" shell for lightweight dialogs such as rename / new-folder /
 * confirmations. Content is projected via `<ng-content/>`. Closes on backdrop
 * click or the `Escape` key. The heavier share / preview dialogs keep their
 * own bespoke markup and do not use this component.
 */
@Component({
  selector: 'app-modal',
  template: `
    <div
      class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      (click)="close()"
    >
      <div
        class="flex flex-col w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200/80"
        (click)="$event.stopPropagation()"
      >
        @if (title()) {
          <header class="flex items-center justify-between gap-3 px-5 py-3.5 bg-slate-50 border-b border-slate-200 shrink-0">
            <h2 class="text-sm font-semibold text-slate-900 truncate">{{ title() }}</h2>
            <button
              type="button"
              class="rounded-full p-1.5 text-slate-500 hover:bg-slate-200 cursor-pointer"
              aria-label="Close"
              (click)="close()"
            >
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </header>
        }
        <div class="p-5">
          <ng-content></ng-content>
        </div>
      </div>
    </div>
  `,
  host: {
    '(window:keydown.escape)': 'onEscape()',
  },
})
export class ModalComponent {
  readonly title = input('');
  readonly closed = output<void>();

  protected close(): void {
    this.closed.emit();
  }

  protected onEscape(): void {
    this.closed.emit();
  }
}
