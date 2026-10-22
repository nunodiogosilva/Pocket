import { Routes } from '@angular/router';
import { driveRoutes } from './features/drive/drive.routes';

/**
 * Root routing.
 *
 * The drive (file explorer) feature renders inside the app shell
 * (`MainLayoutComponent`) which provides the global header (search + Tailscale
 * badge) and the router-outlet. The drive routes keep their absolute-looking
 * paths (`my-pocket`, `shared-pockets`, `bin`) because the shell parent uses
 * `path: ''`.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'my-pocket' },
  {
    path: '',
    loadComponent: () => import('./layout/main-layout/main-layout.component').then((m) => m.MainLayoutComponent),
    children: [...driveRoutes],
  },
  { path: '**', redirectTo: 'my-pocket' },
];
