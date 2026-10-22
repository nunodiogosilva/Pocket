import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { UserProfile } from '../models/file.model';

/**
 * Global singleton exposing the authenticated Tailscale user's profile.
 *
 * The endpoint (`GET /api/user`) is served by the FastAPI backend and
 * authenticated via the Tailscale Identity header. The base URL is added by
 * the `ApiPrefixInterceptor`, so this service stays origin-agnostic.
 */
@Injectable({ providedIn: 'root' })
export class UserService {
  private readonly http = inject(HttpClient);

  /** Fetch the currently authenticated Tailscale user profile. */
  getCurrentUser(): Observable<UserProfile> {
    return this.http.get<UserProfile>('/user');
  }
}
