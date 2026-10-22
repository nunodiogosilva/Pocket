import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { provideRouter, withComponentInputBinding, RouteReuseStrategy } from '@angular/router';
import { routes } from './app.routes';
import { ReuseManagerFileStrategy } from './core/router/reuse-manager-file.strategy';
import { apiPrefixInterceptor } from './core/interceptors/api-prefix.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // XHR instead of the default fetch API: fetch cannot report upload progress.
    // Interceptors: prepend the backend base URL and centralise error logging.
    provideHttpClient(withXhr(), withInterceptors([apiPrefixInterceptor, errorInterceptor])),
    provideRouter(routes, withComponentInputBinding()),
    // Keep the FileManager instance (and its sidebar tree state) alive across
    // My Pocket / Shared Pockets / Bin and their folder sub-routes.
    { provide: RouteReuseStrategy, useClass: ReuseManagerFileStrategy },
  ]
};
