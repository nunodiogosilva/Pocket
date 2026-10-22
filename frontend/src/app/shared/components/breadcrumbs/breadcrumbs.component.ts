import { Component, input, output } from '@angular/core';

export interface BreadcrumbItem {
  id: number;
  label: string;
}

/**
 * Folder-tree breadcrumbs (e.g. My Pocket › Documents › Work).
 *
 * "Dumb" presentational component: it renders the crumb trail and emits the
 * depth the user wants to navigate to, leaving routing to the host.
 */
@Component({
  selector: 'app-breadcrumbs',
  template: `
    <nav class="flex min-w-0 flex-1 items-center gap-1 text-xl font-bold text-slate-800" aria-label="Breadcrumb">
      @if (rootLabel()) {
        <button
          type="button"
          class="shrink-0 rounded-lg px-2.5 py-1 hover:bg-[#f0f4f9] transition cursor-pointer"
          (click)="navigate.emit(0)"
        >
          <span>{{ rootLabel() }}</span>
        </button>
      }
      @for (crumb of crumbs(); track crumb.id; let i = $index) {
        <span class="text-[#444746]" aria-hidden="true">›</span>
        <button
          type="button"
          class="truncate rounded-lg px-2.5 py-1 hover:bg-[#f0f4f9] transition cursor-pointer"
          (click)="navigate.emit(i + 1)"
        >
          <span>{{ crumb.label }}</span>
        </button>
      }
    </nav>
  `,
})
export class BreadcrumbsComponent {
  readonly crumbs = input<BreadcrumbItem[]>([]);
  readonly rootLabel = input('My Pocket');
  readonly navigate = output<number>();
}
