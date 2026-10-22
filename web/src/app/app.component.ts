import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/**
 * Root component shell. Hosts the router-outlet that the routed
 * `MainLayoutComponent` (header + feature outlet) renders into.
 *
 * IMPORTANT: do NOT render `app-main-layout` here directly — the layout is
 * already provided as the parent route in `app.routes.ts`. Rendering it here as
 * well would instantiate the layout (and its header/navbar) twice.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: `<router-outlet />`,
})
export class App {}
