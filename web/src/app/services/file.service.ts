import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpEvent, HttpParams, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface FileItem {
  id: number;
  filename: string;
  file_size: number;
  mime_type: string;
  parent_id: number | null;
  is_folder: boolean;
  created_at: string;
  is_deleted?: boolean;
  deleted_at?: string | null;
  days_left?: number;
  /** Best-matching text from the file; only set on search results. */
  snippet?: string | null;
  /** Shared metadata */
  owner_name?: string | null;
  owner_login?: string;
  permission?: string;
}

export interface DirectoryContent {
  folders: FileItem[];
  files: FileItem[];
}

export interface SearchSuggestion {
  id: number;
  filename: string;
  is_folder: boolean;
  file_size: number;
  mime_type: string;
  snippet?: string | null;
  parent_id?: number | null;
}

export interface SearchSuggestionsResponse {
  folders: SearchSuggestion[];
  files: SearchSuggestion[];
}

export interface UploadResult {
  status: string;
  file_id: number;
  filename: string;
}

export interface ShareLink {
  share_url: string;
  expires_at: string;
}

export interface UserProfile {
  id: number;
  login: string;
  name: string | null;
  email: string | null;
  profile_pic?: string | null;
}

export interface StorageUsage {
  used_bytes: number;
  total_bytes: number;
  file_count: number;
  folder_count: number;
}

export interface ShareUserResult {
  status: string;
  file_id: number;
  shared_with_login: string;
}

@Injectable({
  providedIn: 'root'
})
export class FileService {
  private http = inject(HttpClient);
  private apiUrl = '/api';

  getCurrentUser(): Observable<UserProfile> {
    return this.http.get<UserProfile>(`${this.apiUrl}/auth/me`);
  }

  getUserStorage(): Observable<StorageUsage> {
    return this.http.get<StorageUsage>(`${this.apiUrl}/auth/storage`);
  }

  getFiles(parentId: number | null = null): Observable<DirectoryContent> {
    const query = parentId ? `?parent_id=${parentId}` : '';
    return this.http.get<DirectoryContent>(`${this.apiUrl}/files${query}`);
  }

  getSharedWithMe(): Observable<DirectoryContent> {
    return this.http.get<DirectoryContent>(`${this.apiUrl}/files/shared-with-me`);
  }

  getFileDownloadUrl(fileId: number): string {
    return `${this.apiUrl}/files/${fileId}/download`;
  }

  getFolderDownloadUrl(folderId: number): string {
    return `${this.apiUrl}/folders/${folderId}/download`;
  }

  getFileContent(fileId: number): Observable<string> {
    return this.http.get(this.getFileDownloadUrl(fileId), {
      responseType: 'text'
    });
  }

  uploadFile(
    file: File,
    parentId: number | null = null,
    relativePath: string | null = null
  ): Observable<HttpEvent<UploadResult>> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    if (parentId) {
      formData.append('parent_id', parentId.toString());
    }
    if (relativePath) {
      formData.append('relative_path', relativePath);
    }

    // Upload progress requires the XHR API (see app.config.ts)
    const req = new HttpRequest('POST', `${this.apiUrl}/files/upload`, formData, {
      reportUploadProgress: true,
      responseType: 'json'
    });

    return this.http.request<UploadResult>(req);
  }

  createFolder(name: string, parentId: number | null = null): Observable<FileItem> {
    return this.http.post<FileItem>(`${this.apiUrl}/folders`, {
      name,
      parent_id: parentId
    });
  }

  renameItem(itemId: number, name: string, isFolder: boolean): Observable<FileItem> {
    const endpoint = isFolder ? `${this.apiUrl}/folders/${itemId}/rename` : `${this.apiUrl}/files/${itemId}/rename`;
    return this.http.patch<FileItem>(endpoint, { name });
  }

  generateShareLink(itemId: number, isFolder = false): Observable<ShareLink> {
    const endpoint = isFolder ? `${this.apiUrl}/folders/${itemId}/share` : `${this.apiUrl}/files/${itemId}/share`;
    return this.http.post<ShareLink>(endpoint, {});
  }

  shareWithUser(itemId: number, login: string, permission = 'read', isFolder = false): Observable<ShareUserResult> {
    const endpoint = isFolder ? `${this.apiUrl}/folders/${itemId}/share-user` : `${this.apiUrl}/files/${itemId}/share-user`;
    return this.http.post<ShareUserResult>(endpoint, {
      login,
      permission
    });
  }

  deleteItem(itemId: number, isFolder = false): Observable<{ status: string }> {
    const endpoint = isFolder ? `${this.apiUrl}/folders/${itemId}` : `${this.apiUrl}/files/${itemId}`;
    return this.http.delete<{ status: string }>(endpoint);
  }

  deleteFile(fileId: number): Observable<{ status: string; file_id?: number }> {
    return this.http.delete<{ status: string; file_id?: number }>(`${this.apiUrl}/files/${fileId}`);
  }

  getBinItems(): Observable<FileItem[]> {
    return this.http.get<FileItem[]>(`${this.apiUrl}/bin`);
  }

  restoreFromBin(itemId: number): Observable<{ status: string; id: number }> {
    return this.http.post<{ status: string; id: number }>(`${this.apiUrl}/bin/${itemId}/restore`, {});
  }

  permanentDeleteItem(itemId: number): Observable<{ status: string; id: number }> {
    return this.http.delete<{ status: string; id: number }>(`${this.apiUrl}/bin/${itemId}`);
  }

  emptyBin(): Observable<{ status: string; deleted_count?: number }> {
    return this.http.delete<{ status: string; deleted_count?: number }>(`${this.apiUrl}/bin`);
  }

  search(query: string, limit = 20): Observable<DirectoryContent> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return new Observable<DirectoryContent>((subscriber) => {
      this.http.get<FileItem[]>(`${this.apiUrl}/search`, { params }).subscribe({
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

  getSearchSuggestions(query: string, limit = 8): Observable<SearchSuggestionsResponse> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return this.http.get<SearchSuggestionsResponse>(`${this.apiUrl}/search/suggest`, { params });
  }
}
