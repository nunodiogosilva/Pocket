import { Routes } from '@angular/router';
import { Drive } from './drive.component';

/**
 * Routes for the drive (file explorer) feature and its folder sub-routes.
 *
 * The same `Drive` instance is kept alive across these routes (and their folder
 * sub-routes) via the `ReuseManagerFileStrategy` in `app.config.ts`, so the
 * 'My Pocket' sidebar tree does not reset when you switch between
 * My Pocket / Shared Pockets / Bin.
 *
 * Note: `Drive` is imported directly (rather than via `loadComponent`) so the
 * route-reuse strategy can match on `route.routeConfig.component === Drive`.
 */
export const driveRoutes: Routes = [
  { path: 'my-pocket/folders/:folder_id', component: Drive, data: { tab: 'pocket' } },
  { path: 'my-pocket', component: Drive, data: { tab: 'pocket' } },
  { path: 'shared-pockets/folders/:folder_id', component: Drive, data: { tab: 'shared' } },
  { path: 'shared-pockets', component: Drive, data: { tab: 'shared' } },
  { path: 'bin', component: Drive, data: { tab: 'bin' } },
];
