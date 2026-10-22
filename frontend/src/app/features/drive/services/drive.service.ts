import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpEvent, HttpParams, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  DirectoryContent,
  FileItem,
  ShareLink,
  ShareUserResult,
  StorageUsage,
  UploadResult,
} from '../../../core/models/file.model';

export * from '../../../core/models/file.model';

/**
 * Drive data access for the FastAPI items endpoints.
 *
 * HTTP calls use relative paths; the `ApiPrefixInterceptor`
 * (`core/interceptors/api-prefix.interceptor.ts`) prepends
 * `environment.apiUrl`. The DOM-facing download URL helpers keep the explicit
 * base because `<a href>` / iframe `src` do not pass through HttpClient.
 */
@Injectable({ providedIn: 'root' })
export class DriveService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = environment.apiUrl;

  // --- Directory & items -----------------------------------------------------
  getFiles(parentId: number | null = null): Observable<FileItem[]> {
    const params = new HttpParams().set('type', 'file');
    const finalParams = parentId ? params.set('parent_id', parentId) : params;
    return this.http.get<FileItem[]>('/items', { params: finalParams });
  }

  getFolders(parentId: number | null = null): Observable<FileItem[]> {
    const params = new HttpParams().set('type', 'folder');
    const finalParams = parentId ? params.set('parent_id', parentId) : params;
    return this.http.get<FileItem[]>('/items', { params: finalParams });
  }

  getItems(parentId: number | null = null): Observable<FileItem[]> {
    const params = parentId ? new HttpParams().set('parent_id', parentId) : undefined;
    return this.http.get<FileItem[]>('/items', { params });
  }

  getDirectoryContents(parentId: number | null = null): Observable<DirectoryContent> {
    const params = parentId === null ? undefined : new HttpParams().set('parent_id', parentId);
    return this.http.get<DirectoryContent>('/items/directory', { params });
  }

  getSharedFolderContents(parentId: number | null): Observable<DirectoryContent> {
    const params = parentId === null ? undefined : new HttpParams().set('parent_id', parentId);
    return this.http.get<DirectoryContent>('/items/shared-with-me', { params });
  }

  getItem(itemId: number): Observable<FileItem> {
    return this.http.get<FileItem>(`/items/${itemId}`);
  }

  getFolder(folderId: number): Observable<FileItem> {
    return this.getItem(folderId);
  }

  // --- Downloads & content ---------------------------------------------------
  getFileDownloadUrl(fileId: number): string {
    return `${this.apiBase}/items/${fileId}/download`;
  }

  getFolderDownloadUrl(folderId: number): string {
    return this.getFileDownloadUrl(folderId);
  }

  getFileContent(fileId: number): Observable<string> {
    return this.http.get(this.getFileDownloadUrl(fileId), { responseType: 'text' });
  }

  // --- Upload / create / mutate ---------------------------------------------
  uploadFile(
    file: File,
    parentId: number | null = null,
    relativePath: string | null = null,
  ): Observable<HttpEvent<UploadResult>> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    if (parentId) formData.append('parent_id', parentId.toString());
    if (relativePath) formData.append('relative_path', relativePath);

    // Upload progress requires the XHR API (see app.config.ts)
    const req = new HttpRequest('POST', '/items/upload', formData, {
      reportUploadProgress: true,
      responseType: 'json',
    });
    return this.http.request<UploadResult>(req);
  }

  createFolder(name: string, parentId: number | null = null): Observable<FileItem> {
    return this.http.post<FileItem>('/items', { name, parent_id: parentId });
  }

  renameItem(itemId: number, name: string): Observable<FileItem> {
    return this.http.patch<FileItem>(`/items/${itemId}/rename`, { name });
  }

  moveItem(itemId: number, targetParentId: number | null): Observable<FileItem> {
    return this.http.patch<FileItem>(`/items/${itemId}/move`, { target_parent_id: targetParentId });
  }

  // --- Sharing ---------------------------------------------------------------
  generateShareLink(itemId: number): Observable<ShareLink> {
    return this.http.post<ShareLink>(`/items/${itemId}/share`, {});
  }

  shareWithUser(itemId: number, login: string, permission = 'read'): Observable<ShareUserResult> {
    return this.http.post<ShareUserResult>(`/items/${itemId}/share-user`, { login, permission });
  }

  // --- Delete / bin ----------------------------------------------------------
  deleteItem(itemId: number): Observable<{ status: string; id?: number }> {
    return this.http.delete<{ status: string; id?: number }>(`/items/${itemId}`);
  }

  getBinItems(): Observable<FileItem[]> {
    return this.http.get<FileItem[]>('/items/bin');
  }

  restoreFromBin(itemId: number): Observable<{ status: string; id: number }> {
    return this.http.post<{ status: string; id: number }>(`/items/bin/${itemId}`, {});
  }

  permanentDeleteItem(itemId: number): Observable<{ status: string; id: number }> {
    return this.http.delete<{ status: string; id: number }>(`/items/bin/${itemId}`);
  }

  emptyBin(): Observable<{ status: string; deleted_count?: number }> {
    return this.http.delete<{ status: string; deleted_count?: number }>('/items/bin');
  }

  // --- Storage ---------------------------------------------------------------
  getUserStorage(): Observable<StorageUsage> {
    return this.http.get<StorageUsage>('/items/storage');
  }
}
