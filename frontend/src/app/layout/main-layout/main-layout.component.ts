import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from '../header/header.component';

/**
 * App shell: unites the top bar (header) and the active feature via the
 * router-outlet.
 *
 * Note: the drive's left sidebar (My Pocket / Shared Pockets / Bin navigation,
 * folder tree and storage quota) lives inside the Drive feature
 * (`features/drive/drive.component.html`) because it shares drag-and-drop and
 * selection state with the file list. The header here owns the global search
 * and the Tailscale identity badge.
 */
@Component({
  selector: 'app-main-layout',
  imports: [RouterOutlet, HeaderComponent],
  template: `
    <div class="flex h-dvh flex-col bg-[#f8fafd] text-[#1f1f1f]">
      <app-header />
      <div class="flex min-h-0 flex-1">
        <router-outlet />
      </div>
    </div>
  `,
})
export class MainLayoutComponent {}
