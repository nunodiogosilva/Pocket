import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  DirectoryContent,
  FileItem,
  SearchSuggestionsResponse,
} from '../../core/models/file.model';

export * from '../../core/models/file.model';

/**
 * Semantic search data access (powered by sqlite-vec on the backend).
 *
 * HTTP calls use relative paths; the `ApiPrefixInterceptor` prepends
 * `environment.apiUrl`.
 */
@Injectable({ providedIn: 'root' })
export class SearchService {
  private readonly http = inject(HttpClient);

  /** Semantic + keyword search over the user's accessible files. */
  search(query: string, limit = 20): Observable<DirectoryContent> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return new Observable<DirectoryContent>((subscriber) => {
      this.http.get<FileItem[]>('/search', { params }).subscribe({
        next: (items) => {
          subscriber.next({
            folders: items.filter((i) => i.is_folder),
            files: items.filter((i) => !i.is_folder),
          });
          subscriber.complete();
        },
        error: (err) => subscriber.error(err),
      });
    });
  }

  /** Autocomplete suggestions, separated into folders and files. */
  suggest(query: string, limit = 8): Observable<SearchSuggestionsResponse> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return this.http.get<SearchSuggestionsResponse>('/search/suggest', { params });
  }
}
