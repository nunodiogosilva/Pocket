import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';

/**
 * Prepends the backend base URL (`environment.apiUrl`) to every relative
 * HttpClient request so the domain services can stay origin-agnostic.
 *
 * Absolute URLs (full `http(s)://…`, `blob:`, `data:`) and requests that are
 * already prefixed with the API base are passed through untouched, which keeps
 * the interceptor idempotent and safe to register globally.
 */
export const apiPrefixInterceptor: HttpInterceptorFn = (req, next) => {
  if (
    req.url.startsWith('http://') ||
    req.url.startsWith('https://') ||
    req.url.startsWith('blob:') ||
    req.url.startsWith('data:') ||
    req.url.startsWith(environment.apiUrl)
  ) {
    return next(req);
  }

  const path = req.url.startsWith('/') ? req.url : `/${req.url}`;
  return next(req.clone({ url: `${environment.apiUrl}${path}` }));
};
