import { HttpInterceptorFn } from '@angular/common/http';
import { catchError } from 'rxjs';

/**
 * Global HTTP error handling.
 *
 * Centralises logging so individual components do not each need to wire up
 * their own console noise. Errors are logged once here and then re-thrown so
 * the existing per-call `.subscribe({ error })` handlers and `rxResource`
 * error states keep working exactly as before.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((err: { status?: number; url?: string }) => {
      console.error(
        `[HTTP] ${req.method} ${req.url}${err?.status ? ` -> ${err.status}` : ''}`,
        err,
      );
      throw err;
    }),
  );
