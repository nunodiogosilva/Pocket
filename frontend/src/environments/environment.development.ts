/**
 * Development environment.
 *
 * `ng serve` proxies `/api/*` to the local FastAPI backend via
 * `proxy.conf.json`, so the relative base path is the same as production.
 */
export const environment = {
  production: false,
  apiUrl: '/api',
};
