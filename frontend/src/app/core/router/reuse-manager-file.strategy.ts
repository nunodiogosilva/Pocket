import { Injectable } from '@angular/core';
import { ActivatedRouteSnapshot, DetachedRouteHandle, RouteReuseStrategy } from '@angular/router';
import { Drive } from '../../features/drive/drive.component';

/**
 * Reuses the same Drive instance whenever navigation stays on a route that
 * renders Drive (My Pocket, Shared Pockets, Bin, and their folder sub-routes).
 *
 * Without this, switching between those route records destroys and recreates the
 * component, which wipes the sidebar tree state (open/collapsed, expanded folders).
 * The component already syncs its tab, path, and content from the URL on each
 * NavigationEnd, so a single shared instance is safe and keeps the tree stable.
 */
@Injectable()
export class ReuseManagerFileStrategy extends RouteReuseStrategy {
  private readonly handlersCache = new Map<string, DetachedRouteHandle>();
  private static readonly DRIVE_KEY = 'drive';

  private routeKey(route: ActivatedRouteSnapshot): string | null {
    if (route.routeConfig?.component === Drive) {
      return ReuseManagerFileStrategy.DRIVE_KEY;
    }
    return null;
  }

  override shouldReuseRoute(future: ActivatedRouteSnapshot, curr: ActivatedRouteSnapshot): boolean {
    // Reuse the component when both routes render FileManager, even across
    // different route records (tabs) and parameter sets (folder ids).
    return this.routeKey(future) === this.routeKey(curr) && this.routeKey(future) !== null;
  }

  override shouldDetach(route: ActivatedRouteSnapshot): boolean {
    return this.routeKey(route) !== null;
  }

  override store(route: ActivatedRouteSnapshot, handle: DetachedRouteHandle | null): void {
    const key = this.routeKey(route);
    if (key && handle) {
      this.handlersCache.set(key, handle);
    }
  }

  override shouldAttach(route: ActivatedRouteSnapshot): boolean {
    const key = this.routeKey(route);
    return key !== null && this.handlersCache.has(key);
  }

  override retrieve(route: ActivatedRouteSnapshot): DetachedRouteHandle | null {
    const key = this.routeKey(route);
    return key ? this.handlersCache.get(key) ?? null : null;
  }
}
