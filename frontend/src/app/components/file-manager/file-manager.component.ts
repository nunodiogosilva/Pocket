import { Component, computed, inject, model, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpEventType } from '@angular/common/http';
import { rxResource } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { DirectoryContent, FileItem, FileService } from '../../services/file.service';
import { ShareModal } from '../share-modal/share-modal.component';
import { PreviewModal } from '../preview-modal/preview-modal.component';
import { FileIconComponent } from '../file-icon/file-icon.component';

interface Upload {
  id: number;
  name: string;
  progress: number;
  status: 'queued' | 'uploading' | 'done' | 'error';
}

@Component({
  imports: [DatePipe, ShareModal, PreviewModal, FileIconComponent],
  selector: 'app-file-manager',
  styleUrl: './file-manager.component.css',
  templateUrl: './file-manager.component.html',
})
export class FileManager {
  private readonly fileService = inject(FileService);
  private nextUploadId = 0;

  /** Semantic search query; when set, search results replace the folder listing. */
  readonly searchQuery = model('');

  /** Active navigation tab: 'pocket' for personal cloud, 'shared' for shared with me, 'bin' for recycle bin */
  readonly activeTab = signal<'pocket' | 'shared' | 'bin'>('pocket');

  /** View mode: 'grid' or 'list', persisted to localStorage */
  readonly viewMode = signal<'grid' | 'list'>(
    (typeof localStorage !== 'undefined' && (localStorage.getItem('bitpocket_view_mode') as 'grid' | 'list')) || 'grid',
  );

  /** Folders opened down to the current one. */
  protected readonly path = signal<FileItem[]>([]);
  protected readonly currentFolderId = computed(() => this.path().at(-1)?.id ?? null);

  /** Content rxResource supporting My Pocket, Shared, Bin, and Semantic Search */
  protected readonly content = rxResource({
    params: () => ({
      tab: this.activeTab(),
      folderId: this.currentFolderId(),
      query: this.searchQuery(),
    }),
    stream: ({ params }) => {
      if (params.query) {
        return this.fileService.search(params.query);
      }
      if (params.tab === 'bin') {
        return new Observable<DirectoryContent>((subscriber) => {
          this.fileService.getBinItems().subscribe({
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
      if (params.tab === 'shared' && params.folderId === null) {
        return this.fileService.getSharedWithMe();
      }
      return this.fileService.getFiles(params.folderId);
    },
  });

  protected readonly folders = computed(() => this.content.value()?.folders ?? []);
  protected readonly files = computed(() => this.content.value()?.files ?? []);
  protected readonly items = computed<FileItem[]>(() => [
    ...(this.content.value()?.folders ?? []),
    ...(this.content.value()?.files ?? []),
  ]);
  protected readonly totalItems = computed(() => this.items().length);

  /** Storage consumption rxResource */
  protected readonly storage = rxResource({
    stream: () => this.fileService.getUserStorage(),
  });
  protected readonly storageUsed = computed(() => this.storage.value()?.used_bytes ?? 0);
  protected readonly storageTotal = computed(() => this.storage.value()?.total_bytes ?? (50 * 1024 * 1024 * 1024));
  protected readonly storagePercent = computed(() =>
    Math.min(100, Math.round((this.storageUsed() / (this.storageTotal() || 1)) * 100))
  );

  protected readonly uploads = signal<Upload[]>([]);
  protected readonly activeUploads = computed(
    () => this.uploads().filter((u) => u.status === 'uploading' || u.status === 'queued').length,
  );

  protected readonly shareTarget = signal<FileItem | null>(null);
  protected readonly previewTarget = signal<FileItem | null>(null);
  protected readonly deleteConfirmTarget = signal<FileItem | null>(null);
  protected readonly deleting = signal(false);

  // Rename state
  protected readonly renameTarget = signal<FileItem | null>(null);
  protected readonly renameInput = signal('');
  protected readonly renaming = signal(false);

  // Bin specific state
  protected readonly emptyBinConfirmOpen = signal(false);
  protected readonly emptyingBin = signal(false);
  protected readonly restoringItemId = signal<number | null>(null);

  // New folder dialog & menu
  protected readonly newMenuOpen = signal(false);
  protected readonly newFolderOpen = signal(false);
  protected readonly newFolderName = signal('');
  protected readonly creatingFolder = signal(false);

  // Drag & drop state
  protected readonly isDraggingOver = signal(false);

  setViewMode(mode: 'grid' | 'list') {
    this.viewMode.set(mode);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('bitpocket_view_mode', mode);
    }
  }

  selectTab(tab: 'pocket' | 'shared' | 'bin') {
    this.activeTab.set(tab);
    this.searchQuery.set('');
    this.path.set([]);
  }

  public navigateToFolder(folder: { id: number; filename: string }) {
    this.searchQuery.set('');
    this.activeTab.set('pocket');
    this.path.set([
      {
        id: folder.id,
        filename: folder.filename,
        is_folder: true,
        file_size: 0,
        mime_type: '',
        parent_id: null,
        created_at: new Date().toISOString(),
      },
    ]);
  }

  public previewFileById(item: {
    id: number;
    filename: string;
    mime_type?: string;
    file_size?: number;
    parent_id?: number | null;
  }) {
    this.previewTarget.set({
      id: item.id,
      filename: item.filename,
      is_folder: false,
      file_size: item.file_size ?? 0,
      mime_type: item.mime_type ?? 'application/octet-stream',
      parent_id: item.parent_id ?? null,
      created_at: new Date().toISOString(),
    });
  }

  public openPreviewById(item: {
    id: number;
    filename: string;
    mime_type?: string;
    file_size?: number;
    parent_id?: number | null;
  }) {
    this.previewFileById(item);
  }

  protected openFolder(folder: FileItem) {
    if (this.activeTab() === 'bin') {
      return; // Inside bin, folders cannot be navigated into directly until restored
    }
    this.searchQuery.set('');
    this.path.update((path) => [...path, folder]);
  }

  protected goTo(depth: number) {
    this.searchQuery.set('');
    this.path.update((path) => path.slice(0, depth));
  }

  protected openPreview(file: FileItem) {
    if (!file.is_folder) {
      this.previewTarget.set(file);
    }
  }

  protected startRename(item: FileItem) {
    this.renameTarget.set(item);
    this.renameInput.set(item.filename);
  }

  protected submitRename() {
    const target = this.renameTarget();
    const newName = this.renameInput().trim();
    if (!target || !newName) return;

    this.renaming.set(true);
    this.fileService.renameItem(target.id, newName, target.is_folder).subscribe({
      next: () => {
        this.renaming.set(false);
        this.renameTarget.set(null);
        this.content.reload();
      },
      error: (err) => {
        this.renaming.set(false);
        alert(err?.error?.detail || 'Failed to rename item.');
      },
    });
  }

  protected deleteItem(item: FileItem) {
    this.deleting.set(true);
    if (this.activeTab() === 'bin') {
      this.fileService.permanentDeleteItem(item.id).subscribe({
        next: () => {
          this.deleting.set(false);
          this.deleteConfirmTarget.set(null);
          this.content.reload();
          this.storage.reload();
        },
        error: () => {
          this.deleting.set(false);
          alert('Failed to permanently delete item.');
        },
      });
    } else {
      this.fileService.deleteItem(item.id, item.is_folder).subscribe({
        next: () => {
          this.deleting.set(false);
          this.deleteConfirmTarget.set(null);
          this.content.reload();
          this.storage.reload();
        },
        error: () => {
          this.deleting.set(false);
          alert('Failed to delete item.');
        },
      });
    }
  }

  protected restoreItem(item: FileItem) {
    this.restoringItemId.set(item.id);
    this.fileService.restoreFromBin(item.id).subscribe({
      next: () => {
        this.restoringItemId.set(null);
        this.content.reload();
        this.storage.reload();
      },
      error: () => {
        this.restoringItemId.set(null);
        alert('Failed to restore item.');
      },
    });
  }

  protected emptyBin() {
    this.emptyingBin.set(true);
    this.fileService.emptyBin().subscribe({
      next: () => {
        this.emptyingBin.set(false);
        this.emptyBinConfirmOpen.set(false);
        this.content.reload();
        this.storage.reload();
      },
      error: () => {
        this.emptyingBin.set(false);
        alert('Failed to empty bin.');
      },
    });
  }

  protected createFolder() {
    const name = this.newFolderName().trim();
    if (!name) return;

    this.creatingFolder.set(true);
    this.fileService.createFolder(name, this.currentFolderId()).subscribe({
      next: () => {
        this.creatingFolder.set(false);
        this.newFolderOpen.set(false);
        this.newFolderName.set('');
        this.content.reload();
        this.storage.reload();
      },
      error: () => {
        this.creatingFolder.set(false);
        alert('Failed to create folder.');
      },
    });
  }

  protected getDownloadUrl(item: FileItem): string {
    if (item.is_folder) {
      return this.fileService.getFolderDownloadUrl(item.id);
    }
    return this.fileService.getFileDownloadUrl(item.id);
  }

  private readonly uploadQueue: { id: number; file: File; relativePath: string | null; retries: number }[] = [];
  private activeUploadCount = 0;
  private readonly MAX_CONCURRENT_UPLOADS = 2;
  private reloadTimer: any = null;

  protected onFilesSelected(input: HTMLInputElement) {
    this.newMenuOpen.set(false);
    for (const file of Array.from(input.files ?? [])) {
      this.enqueueUpload(file);
    }
    input.value = '';
  }

  protected onFolderSelected(input: HTMLInputElement) {
    this.newMenuOpen.set(false);
    for (const file of Array.from(input.files ?? [])) {
      const relativePath = (file as any).webkitRelativePath || file.name;
      this.enqueueUpload(file, relativePath);
    }
    input.value = '';
  }

  protected onDragOver(event: DragEvent) {
    if (this.activeTab() === 'bin') return;
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(true);
  }

  protected onDragLeave(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);
  }

  protected async onDrop(event: DragEvent) {
    if (this.activeTab() === 'bin') return;
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);

    const items = event.dataTransfer?.items;
    if (items && items.length > 0) {
      const allFiles: { file: File; relativePath: string }[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (typeof (item as any).webkitGetAsEntry === 'function') {
          const entry = (item as any).webkitGetAsEntry();
          if (entry) {
            const files = await this.readEntryRecursive(entry);
            allFiles.push(...files);
          }
        }
      }

      if (allFiles.length > 0) {
        for (const { file, relativePath } of allFiles) {
          this.enqueueUpload(file, relativePath);
        }
        return;
      }
    }

    const files = event.dataTransfer?.files;
    if (files) {
      for (const file of Array.from(files)) {
        this.enqueueUpload(file);
      }
    }
  }

  private async readEntryRecursive(entry: any, basePath = ''): Promise<{ file: File; relativePath: string }[]> {
    if (entry.isFile) {
      return new Promise((resolve) => {
        entry.file((file: File) => {
          resolve([{ file, relativePath: basePath ? `${basePath}/${file.name}` : file.name }]);
        });
      });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const currentDirName = basePath ? `${basePath}/${entry.name}` : entry.name;
      const entries: any[] = await new Promise((resolve) => {
        const results: any[] = [];
        const readEntriesBatch = () => {
          reader.readEntries((batch: any[]) => {
            if (!batch.length) {
              resolve(results);
            } else {
              results.push(...batch);
              readEntriesBatch();
            }
          });
        };
        readEntriesBatch();
      });

      const childFiles = await Promise.all(
        entries.map((child) => this.readEntryRecursive(child, currentDirName))
      );
      return childFiles.flat();
    }
    return [];
  }

  private enqueueUpload(file: File, relativePath: string | null = null) {
    const id = ++this.nextUploadId;
    const displayName = relativePath || file.name;
    this.uploads.update((uploads) => [
      ...uploads,
      { id, name: displayName, progress: 0, status: 'queued' },
    ]);

    this.uploadQueue.push({ id, file, relativePath, retries: 0 });
    this.processUploadQueue();
  }

  private processUploadQueue() {
    while (this.activeUploadCount < this.MAX_CONCURRENT_UPLOADS && this.uploadQueue.length > 0) {
      const item = this.uploadQueue.shift();
      if (!item) break;

      this.activeUploadCount++;
      this.patchUpload(item.id, { status: 'uploading' });

      this.fileService.uploadFile(item.file, this.currentFolderId(), item.relativePath).subscribe({
        next: (event) => {
          if (event.type === HttpEventType.UploadProgress) {
            const progress = event.total ? Math.round((100 * event.loaded) / event.total) : 0;
            this.patchUpload(item.id, { progress });
          } else if (event.type === HttpEventType.Response) {
            this.patchUpload(item.id, { progress: 100, status: 'done' });
            this.activeUploadCount--;
            this.scheduleContentReload();
            this.processUploadQueue();
          }
        },
        error: () => {
          if (item.retries < 2) {
            // Auto-retry transient server errors after short delay
            item.retries++;
            setTimeout(() => {
              this.uploadQueue.unshift(item);
              this.activeUploadCount--;
              this.processUploadQueue();
            }, 1000);
          } else {
            this.patchUpload(item.id, { status: 'error' });
            this.activeUploadCount--;
            this.scheduleContentReload();
            this.processUploadQueue();
          }
        },
      });
    }
  }

  private scheduleContentReload() {
    if (this.reloadTimer) {
      clearTimeout(this.reloadTimer);
    }
    // Debounce reloads so we don't spam the server while multiple files complete
    this.reloadTimer = setTimeout(() => {
      this.content.reload();
      this.storage.reload();
    }, 1500);
  }

  private patchUpload(id: number, changes: Partial<Upload>) {
    this.uploads.update((uploads) =>
      uploads.map((upload) => (upload.id === id ? { ...upload, ...changes } : upload)),
    );
  }

  protected formatSize(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    const units = ['KB', 'MB', 'GB', 'TB'];
    let value = bytes / 1024;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
  }

  protected iconColor({ mime_type: type }: FileItem): string {
    if (type.startsWith('image/')) return 'text-red-500';
    if (type.startsWith('video/')) return 'text-rose-700';
    if (type.startsWith('audio/')) return 'text-purple-600';
    if (type === 'application/pdf') return 'text-red-700';
    if (/zip|tar|rar|7z|compressed/.test(type)) return 'text-amber-600';
    if (/sheet|excel|csv/.test(type)) return 'text-green-600';
    if (/presentation|powerpoint/.test(type)) return 'text-yellow-500';
    if (type.startsWith('text/') || /document|msword|json|xml/.test(type)) return 'text-blue-600';
    return 'text-gray-500';
  }
}
