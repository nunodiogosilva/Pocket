/**
 * Production environment.
 *
 * `apiUrl` is the base path the backend is served under. In production the
 * web bundle and the FastAPI backend are both served from the same origin
 * (see `web/nginx.conf`), so a relative base path is all we need. The
 * `ApiPrefixInterceptor` prepends this to every HttpClient request.
 */
export const environment = {
  production: true,
  apiUrl: '/api',
};
