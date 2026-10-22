import { Component, computed, effect, inject, model, signal, ElementRef, HostListener, afterNextRender, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpEventType } from '@angular/common/http';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { rxResource, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { Observable, catchError, filter, firstValueFrom, map, of, switchMap } from 'rxjs';
import { DirectoryContent, FileItem, DriveService, ShareLink } from './services/drive.service';
import { DriveController } from './services/drive-controller';
import { SearchService } from '../search/search.service';
import { FileIconComponent } from '../../shared/components/file-icon/file-icon.component';

export type PreviewKind =
  | 'markdown'
  | 'csv'
  | 'pdf'
  | 'video'
  | 'audio'
  | 'image'
  | 'text'
  | 'unsupported';

interface CsvData {
  headers: string[];
  rows: string[][];
}

interface Upload {
  id: number;
  name: string;
  progress: number;
  status: 'queued' | 'uploading' | 'done' | 'error';
  isFolder?: boolean;
  progressText?: string;
}

@Component({
  imports: [DatePipe, FileIconComponent],
  selector: 'app-drive',
  host: {
    class: 'flex min-h-0 flex-1',
  },
  styleUrl: './drive.component.css',
  templateUrl: './drive.component.html',
})
export class Drive {
  private readonly fileService = inject(DriveService);
  private readonly searchService = inject(SearchService);
  private readonly driveController = inject(DriveController);
  private readonly router = inject(Router);
  private nextUploadId = 0;
  private folderRouteRequestId = 0;
  protected readonly sidebarFolders = signal<FileItem[]>([]);
  protected readonly pocketTreeOpen = signal(false);
  protected readonly expandedSidebarFolderIds = signal<Set<number>>(new Set());
  private readonly sidebarFolderChildren = signal<Record<number, FileItem[]>>({});
  private pocketTreeHoverTimer: ReturnType<typeof setTimeout> | null = null;
  private sidebarFolderHoverTimer: ReturnType<typeof setTimeout> | null = null;
  private sidebarFolderHoverId: number | null = null;
  protected readonly sidebarFolderRows = computed(() => {
    const rows: { folder: FileItem; depth: number }[] = [];
    const childrenByFolder = this.sidebarFolderChildren();

    const appendChildren = (folders: FileItem[], depth: number) => {
      const sorted = [...folders].sort((a, b) =>
        a.filename.localeCompare(b.filename, undefined, { sensitivity: 'base' })
      );
      for (const folder of sorted) {
        rows.push({ folder, depth });
        if (this.expandedSidebarFolderIds().has(folder.id)) {
          appendChildren(childrenByFolder[folder.id] ?? [], depth + 1);
        }
      }
    };

    if (this.pocketTreeOpen()) appendChildren(this.sidebarFolders(), 0);
    return rows;
  });

  /** Folders that cannot receive the current drag: the dragged folder itself and its loaded subfolders. */
  protected readonly invalidSidebarDropFolderIds = computed(() => {
    const ids = new Set<number>();
    const draggedFolderIds = this.draggedItems()
      .filter((item) => item.is_folder)
      .map((item) => item.id);
    if (draggedFolderIds.length === 0) return ids;

    const childrenByFolder = this.sidebarFolderChildren();
    const walk = (folderId: number) => {
      ids.add(folderId);
      for (const child of childrenByFolder[folderId] ?? []) {
        walk(child.id);
      }
    };
    for (const folderId of draggedFolderIds) walk(folderId);
    return ids;
  });

  /** Semantic search query; when set, search results replace the folder listing. */
  readonly searchQuery = model('');

  /** Active navigation tab: 'pocket' for personal cloud, 'shared' for shared with me, 'bin' for recycle bin */
  readonly activeTab = signal<'pocket' | 'shared' | 'bin'>('pocket');

  /** View mode: 'grid' or 'list', persisted to localStorage. Default to 'list' like Google Drive */
  readonly viewMode = signal<'grid' | 'list'>(
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'grid'
      ? 'grid'
      : (typeof localStorage !== 'undefined' &&
          (localStorage.getItem('pocket_view_mode') as 'grid' | 'list')) ||
        'list',
  );

  constructor() {
    this.driveController.register(this);
    this.refreshSidebarFolders();
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => {
        this.syncTabFromUrl();
      });
    this.syncTabFromUrl();

    // Inlined share-modal: open <dialog> and generate link whenever shareTarget is set
    effect(() => {
      const target = this.shareTarget();
      if (!target) return;
      afterNextRender(() => {
        const el = this.shareDialog();
        if (el) {
          const dialogEl = el.nativeElement;
          if (!dialogEl.open) dialogEl.showModal();
          if (!this.shareLink()) this.loadShareLink(target);
        }
      });
    });
  }

  private loadShareLink(file: FileItem) {
    this.shareError.set(false);
    this.fileService.generateShareLink(file.id).subscribe({
      next: (link) => this.shareLink.set(link),
      error: () => this.shareError.set(true),
    });
  }

  protected closeShareModal() {
    this.shareTarget.set(null);
  }

  protected async copyShareLink(input: HTMLInputElement) {
    try {
      await navigator.clipboard.writeText(input.value);
    } catch {
      input.select();
      document.execCommand('copy');
    }
    this.shareCopied.set(true);
  }

  protected shareWithUser() {
    const file = this.shareTarget();
    const login = this.userShareInput().trim();
    if (!file || !login) return;
    this.userShareLoading.set(true);
    this.userShareError.set(null);
    this.userShareSuccess.set(null);
    this.fileService.shareWithUser(file.id, login, 'read').subscribe({
      next: () => {
        this.userShareLoading.set(false);
        this.userShareSuccess.set(`Successfully shared with ${login}`);
        this.userShareInput.set('');
      },
      error: () => {
        this.userShareLoading.set(false);
        this.userShareError.set('Failed to share with user.');
      },
    });
  }

  // ── Inlined preview-modal behavior ────────────────────────────────────────
  private loadPreview() {
    const f = this.previewTarget();
    if (!f) return;
    const kind = this.previewKind();
    if (kind === 'markdown' || kind === 'csv' || kind === 'text') {
      this.previewLoading.set(true);
      this.previewError.set(null);
      this.fileService.getFileContent(f.id).subscribe({
        next: (content) => {
          this.textContent.set(content);
          if (kind === 'markdown') this.markdownHtml.set(this.renderMarkdown(content));
          else if (kind === 'csv') this.csvData.set(this.parseCsv(content, f.filename.toLowerCase().endsWith('.tsv') ? '\t' : ','));
          this.previewLoading.set(false);
        },
        error: () => {
          this.previewError.set('Failed to fetch file content.');
          this.previewLoading.set(false);
        },
      });
    } else {
      this.previewLoading.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  protected onPreviewEscape() {
    if (this.previewTarget()) this.previewTarget.set(null);
  }

  protected closePreview() {
    this.previewTarget.set(null);
  }

  protected copyPreviewContent() {
    const text = this.textContent();
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      this.copySuccess.set(true);
      setTimeout(() => this.copySuccess.set(false), 2000);
    });
  }

  protected zoomIn() {
    this.zoomLevel.update((z) => Math.min(z + 0.25, 3));
  }

  protected zoomOut() {
    this.zoomLevel.update((z) => Math.max(z - 0.25, 0.5));
  }

  protected resetZoom() {
    this.zoomLevel.set(1);
  }

  // Client-side RFC 4180 CSV parser
  private parseCsv(text: string, delimiter = ','): CsvData {
    const rows: string[][] = [];
    let currentRow: string[] = [];
    let currentCell = '';
    let inQuotes = false;
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      const nextChar = text[i + 1];
      if (char === '"') {
        if (inQuotes && nextChar === '"') { currentCell += '"'; i++; }
        else inQuotes = !inQuotes;
      } else if (char === delimiter && !inQuotes) {
        currentRow.push(currentCell.trim());
        currentCell = '';
      } else if ((char === '\r' || char === '\n') && !inQuotes) {
        if (char === '\r' && nextChar === '\n') i++;
        currentRow.push(currentCell.trim());
        if (currentRow.length > 1 || (currentRow.length === 1 && currentRow[0] !== '')) rows.push(currentRow);
        currentRow = [];
        currentCell = '';
      } else {
        currentCell += char;
      }
    }
    if (currentCell !== '' || currentRow.length > 0) {
      currentRow.push(currentCell.trim());
      if (currentRow.length > 1 || (currentRow.length === 1 && currentRow[0] !== '')) rows.push(currentRow);
    }
    if (rows.length === 0) return { headers: [], rows: [] };
    const headers = rows[0];
    return { headers, rows: rows.slice(1) };
  }

  // Pure client-side markdown parser
  private renderMarkdown(md: string): string {
    const escapeHtml = (str: string) =>
      str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const lines = md.split('\n');
    const output: string[] = [];
    let inCodeBlock = false;
    let codeBuffer: string[] = [];
    let codeLang = '';
    let inList = false;
    let listType: 'ul' | 'ol' = 'ul';
    let inTable = false;
    let tableBuffer: string[] = [];
    const flushList = () => {
      if (inList) { output.push(listType === 'ul' ? '</ul>' : '</ol>'); inList = false; }
    };
    const flushTable = () => {
      if (inTable && tableBuffer.length > 0) { output.push(this.renderMarkdownTable(tableBuffer)); inTable = false; tableBuffer = []; }
    };
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.trim().startsWith('```')) {
        if (inCodeBlock) {
          flushList();
          output.push(`<div class="my-4 rounded-xl overflow-hidden bg-slate-900 border border-slate-800 shadow-sm"><div class="flex items-center justify-between px-4 py-1.5 bg-slate-800/80 text-xs text-slate-400 font-mono"><span>${escapeHtml(codeLang || 'plaintext')}</span></div><pre class="p-4 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed"><code>${escapeHtml(codeBuffer.join('\n'))}</code></pre></div>`);
          inCodeBlock = false;
          codeBuffer = [];
          codeLang = '';
        } else {
          flushList();
          flushTable();
          inCodeBlock = true;
          codeLang = line.trim().slice(3).trim();
        }
        continue;
      }
      if (inCodeBlock) { codeBuffer.push(line); continue; }
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        flushList();
        inTable = true;
        tableBuffer.push(line);
        continue;
      } else if (inTable) {
        flushTable();
      }
      if (/^(\*\*\*|---|___)$/.test(line.trim())) {
        flushList();
        output.push('<hr class="my-6 border-slate-200 dark:border-slate-700" />');
        continue;
      }
      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        flushList();
        const level = headingMatch[1].length;
        const text = this.inlineMarkdown(escapeHtml(headingMatch[2]));
        const classes: Record<number, string> = {
          1: 'text-2xl font-bold text-slate-900 mt-6 mb-3 pb-2 border-b border-slate-200',
          2: 'text-xl font-bold text-slate-900 mt-5 mb-2.5',
          3: 'text-lg font-semibold text-slate-800 mt-4 mb-2',
          4: 'text-base font-semibold text-slate-800 mt-3 mb-1.5',
          5: 'text-sm font-semibold text-slate-700 mt-2 mb-1',
          6: 'text-xs font-semibold text-slate-600 mt-2 mb-1 uppercase tracking-wider',
        };
        output.push(`<h${level} class="${classes[level]}">${text}</h${level}>`);
        continue;
      }
      if (line.startsWith('>')) {
        flushList();
        const quoteText = this.inlineMarkdown(escapeHtml(line.replace(/^>\s?/, '')));
        output.push(`<blockquote class="my-3 border-l-4 border-blue-500 bg-blue-50/60 px-4 py-2 text-sm italic text-slate-700 rounded-r-lg">${quoteText}</blockquote>`);
        continue;
      }
      const ulMatch = line.match(/^(\*|-|\+)\s+(.*)$/);
      const olMatch = line.match(/^(\d+)\.\s+(.*)$/);
      if (ulMatch) {
        if (!inList || listType !== 'ul') { flushList(); output.push('<ul class="my-2.5 list-disc space-y-1.5 pl-6 text-sm text-slate-800">'); inList = true; listType = 'ul'; }
        output.push(`<li>${this.inlineMarkdown(escapeHtml(ulMatch[2]))}</li>`);
        continue;
      }
      if (olMatch) {
        if (!inList || listType !== 'ol') { flushList(); output.push('<ol class="my-2.5 list-decimal space-y-1.5 pl-6 text-sm text-slate-800">'); inList = true; listType = 'ol'; }
        output.push(`<li>${this.inlineMarkdown(escapeHtml(olMatch[2]))}</li>`);
        continue;
      }
      flushList();
      if (!line.trim()) continue;
      output.push(`<p class="my-2 text-sm leading-relaxed text-slate-800">${this.inlineMarkdown(escapeHtml(line))}</p>`);
    }
    flushList();
    flushTable();
    return output.join('\n');
  }

  private inlineMarkdown(str: string): string {
    return str
      .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
      .replace(/~~(.*?)~~/g, '<del class="line-through text-slate-400">$1</del>')
      .replace(/`([^`]+)`/g, '<code class="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-pink-600 border border-slate-200">$1</code>')
      .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline font-medium hover:text-blue-800">$1</a>');
  }

  private renderMarkdownTable(lines: string[]): string {
    if (lines.length < 2) return '';
    const parseRow = (line: string) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
    const headerCols = parseRow(lines[0]);
    const bodyLines = lines.slice(2);
    let html = `<div class="my-4 overflow-x-auto rounded-xl border border-slate-200 shadow-sm"><table class="w-full text-left text-xs divide-y divide-slate-200">`;
    html += `<thead class="bg-slate-50 font-semibold text-slate-700"><tr>`;
    for (const h of headerCols) html += `<th class="px-4 py-2.5">${this.inlineMarkdown(h)}</th>`;
    html += `</tr></thead><tbody class="divide-y divide-slate-100 bg-white">`;
    for (const rowLine of bodyLines) {
      const cols = parseRow(rowLine);
      html += `<tr class="hover:bg-slate-50/80">`;
      for (let c = 0; c < headerCols.length; c++) html += `<td class="px-4 py-2 text-slate-700">${this.inlineMarkdown(cols[c] || '')}</td>`;
      html += `</tr>`;
    }
    html += `</tbody></table></div>`;
    return html;
  }

  ngOnDestroy(): void {
    this.driveController.unregister(this);
  }

  private refreshSidebarFolders() {
    this.fileService.getFolders(null).subscribe({
      next: (folders) => this.sidebarFolders.set(folders),
    });
    // Refresh the children of any expanded folder so moves that add/remove folders
    // inside them are reflected immediately. The tree stays visible (empty) while
    // each re-fetch is in flight, then fills in — never showing stale data.
    const expanded = [...this.expandedSidebarFolderIds()];
    this.sidebarFolderChildren.update((children) => {
      const next: Record<number, FileItem[]> = {};
      for (const key of Object.keys(children)) next[Number(key)] = [];
      return next;
    });
    for (const folderId of expanded) {
      this.fileService.getFolders(folderId).subscribe({
        next: (folders) => this.sidebarFolderChildren.update((children) => ({ ...children, [folderId]: folders })),
      });
    }
  }

  protected togglePocketTree() {
    this.pocketTreeOpen.update((isOpen) => !isOpen);
  }

  protected toggleSidebarFolder(folder: FileItem, event: MouseEvent) {
    event.stopPropagation();
    const expanded = this.expandedSidebarFolderIds();
    const nextExpanded = new Set(expanded);
    if (nextExpanded.has(folder.id)) {
      nextExpanded.delete(folder.id);
      this.expandedSidebarFolderIds.set(nextExpanded);
      return;
    }

    this.expandSidebarFolder(folder);
  }

  private expandSidebarFolder(folder: FileItem) {
    this.expandedSidebarFolderIds.update((ids) => new Set(ids).add(folder.id));
    if (Object.prototype.hasOwnProperty.call(this.sidebarFolderChildren(), folder.id)) return;

    this.fileService.getFolders(folder.id).subscribe({
      next: (folders) => this.sidebarFolderChildren.update((children) => ({ ...children, [folder.id]: folders })),
    });
  }

  protected onPocketTreeDragOver(event: DragEvent) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    if (this.draggedItems().some((item) => item.is_folder && item.parent_id !== null)) {
      this.isPocketDropTarget.set(true);
    } else {
      this.isPocketDropTarget.set(false);
    }
    if (this.pocketTreeOpen() || this.pocketTreeHoverTimer) return;

    this.pocketTreeHoverTimer = setTimeout(() => {
      this.pocketTreeOpen.set(true);
      this.pocketTreeHoverTimer = null;
    }, 650);
  }

  protected onPocketTreeDragLeave() {
    if (this.pocketTreeHoverTimer) {
      clearTimeout(this.pocketTreeHoverTimer);
      this.pocketTreeHoverTimer = null;
    }
    this.isPocketDropTarget.set(false);
  }

  protected async onPocketTreeDrop(event: DragEvent) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    this.isPocketDropTarget.set(false);

    const itemsToMove = this.draggedItems().filter((item) => item.is_folder && item.parent_id !== null);
    if (itemsToMove.length === 0) return;

    this.movingItems.set(itemsToMove);
    this.movingItem.set(true);
    try {
      for (const item of itemsToMove) {
        await firstValueFrom(this.fileService.moveItem(item.id, null));
      }
    } catch (err: any) {
      alert(err?.error?.detail || 'Some items could not be moved to My Pocket. Items moved before the error remain there.');
    } finally {
      this.movingItem.set(false);
      this.movingItems.set([]);
      this.draggedItem.set(null);
      this.draggedItems.set([]);
      this.selectedItems.set([]);
      this.selectedItemId.set(null);
      this.content.reload();
      this.storage.reload();
      this.refreshSidebarFolders();
    }
  }

  private scheduleSidebarFolderExpand(folder: FileItem) {
    if (this.sidebarFolderHoverId === folder.id) return;
    this.clearSidebarFolderHoverTimer();
    this.sidebarFolderHoverId = folder.id;
    this.sidebarFolderHoverTimer = setTimeout(() => {
      if (this.draggedItems().length > 0 && this.dragOverFolderId() === folder.id) {
        this.expandSidebarFolder(folder);
      }
      this.sidebarFolderHoverTimer = null;
      this.sidebarFolderHoverId = null;
    }, 650);
  }

  private clearSidebarFolderHoverTimer(folderId?: number) {
    if (folderId !== undefined && this.sidebarFolderHoverId !== folderId) return;
    if (this.sidebarFolderHoverTimer) clearTimeout(this.sidebarFolderHoverTimer);
    this.sidebarFolderHoverTimer = null;
    this.sidebarFolderHoverId = null;
  }

  private syncTabFromUrl() {
    const url = this.router.url.split('?')[0];
    const tab = url.startsWith('/bin')
      ? 'bin'
      : url.startsWith('/shared-pockets')
        ? 'shared'
        : 'pocket';
    if (this.activeTab() !== tab) {
      this.activeTab.set(tab);
      this.path.set([]);
    }

    const folderMatch = url.match(/^\/(my-pocket|shared-pockets)\/folders\/(\d+)$/);
    if (!folderMatch) {
      this.folderRouteRequestId++;
      if (this.path().length) this.path.set([]);
      return;
    }

    const folderId = Number(folderMatch[2]);
    if (this.path().at(-1)?.id === folderId) return;

    const requestId = ++this.folderRouteRequestId;
    const folderTab = folderMatch[1] === 'shared-pockets' ? 'shared' : 'pocket';
    this.searchQuery.set('');
    this.path.set([]);
    this.getFolderPath(folderId).subscribe({
      next: (folderPath) => {
        if (requestId === this.folderRouteRequestId && this.activeTab() === folderTab) {
          this.path.set(folderPath);
        }
      },
      error: () => {
        if (requestId === this.folderRouteRequestId) {
          const root = folderTab === 'shared' ? '/shared-pockets' : '/my-pocket';
          this.router.navigateByUrl(root, { replaceUrl: true });
        }
      },
    });
  }

  private getFolderPath(folderId: number): Observable<FileItem[]> {
    return this.fileService.getFolder(folderId).pipe(
      switchMap((folder) =>
        folder.parent_id === null
          ? of([folder])
          : this.getFolderPath(folder.parent_id).pipe(
              catchError(() => of([])),
              map((parents) => [...parents, folder]),
            ),
      ),
    );
  }

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
        return this.searchService.search(params.query);
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
      if (params.tab === 'shared') {
        return this.fileService.getSharedFolderContents(params.folderId);
      }
      return this.fileService.getDirectoryContents(params.folderId);
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

  // Upload state
  protected readonly uploads = signal<Upload[]>([]);
  protected readonly uploadPanelMinimized = signal(false);
  protected readonly activeUploads = computed(
    () => this.uploads().filter((u) => u.status === 'uploading' || u.status === 'queued').length,
  );

  // Sort state (Google Drive layout)
  protected readonly sortColumn = signal<'name' | 'modified' | 'days_left' | 'size'>('name');
  protected readonly sortDirection = signal<'asc' | 'desc'>('asc');

  // Selected row and dropdown state
  protected readonly selectedItemId = signal<number | null>(null);
  protected readonly selectedItems = signal<FileItem[]>([]);
  private readonly selectionAnchorId = signal<number | null>(null);
  protected readonly openDropdownId = signal<number | null>(null);

  protected readonly displayFolders = computed<FileItem[]>(() => {
    return this.sortItems(this.folders(), this.sortColumn(), this.sortDirection());
  });

  protected readonly displayFiles = computed<FileItem[]>(() => {
    return this.sortItems(this.files(), this.sortColumn(), this.sortDirection());
  });

  protected readonly displayItems = computed<FileItem[]>(() => [
    ...this.displayFolders(),
    ...this.displayFiles(),
  ]);

  protected readonly shareTarget = signal<FileItem | null>(null);
  protected readonly previewTarget = signal<FileItem | null>(null);
  protected readonly deleteConfirmTarget = signal<FileItem | null>(null);

  // ── Inlined share modal state ──────────────────────────────────────────
  private readonly shareDialog = viewChild.required<ElementRef<HTMLDialogElement>>('shareDialog');
  protected readonly shareLink = signal<ShareLink | null>(null);
  protected readonly shareError = signal(false);
  protected readonly shareCopied = signal(false);
  protected readonly userShareInput = signal('');
  protected readonly userShareLoading = signal(false);
  protected readonly userShareSuccess = signal<string | null>(null);
  protected readonly userShareError = signal<string | null>(null);

  // ── Inlined preview modal state ────────────────────────────────────────
  private readonly sanitizer = inject(DomSanitizer);
  protected readonly previewLoading = signal(true);
  protected readonly previewError = signal<string | null>(null);
  protected readonly textContent = signal<string>('');
  protected readonly markdownHtml = signal<string>('');
  protected readonly csvData = signal<CsvData | null>(null);
  protected readonly csvFilter = signal('');
  protected readonly zoomLevel = signal(1);
  protected readonly copySuccess = signal(false);
  protected readonly Math = Math;

  protected readonly downloadUrl = computed(() => {
    const f = this.previewTarget();
    return f ? this.fileService.getFileDownloadUrl(f.id) : '';
  });

  protected readonly sanitizedUrl = computed<SafeResourceUrl>(() =>
    this.sanitizer.bypassSecurityTrustResourceUrl(this.downloadUrl())
  );

  protected readonly previewKind = computed<PreviewKind>(() => {
    const f = this.previewTarget();
    if (!f) return 'unsupported';
    const ext = (f.filename.split('.').pop() || '').toLowerCase();
    const mime = (f.mime_type || '').toLowerCase();
    if (ext === 'md' || ext === 'markdown') return 'markdown';
    if (ext === 'csv' || ext === 'tsv' || mime === 'text/csv') return 'csv';
    if (ext === 'pdf' || mime === 'application/pdf') return 'pdf';
    if (['mp4', 'mov', 'webm', 'ogg', 'mkv', 'm4v'].includes(ext) || mime.startsWith('video/')) return 'video';
    if (['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'].includes(ext) || mime.startsWith('audio/')) return 'audio';
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'].includes(ext) || mime.startsWith('image/')) return 'image';
    if (['txt', 'json', 'yml', 'yaml', 'xml', 'html', 'css', 'js', 'ts', 'py', 'sh', 'sql', 'toml', 'ini', 'env', 'log', 'java', 'c', 'cpp', 'rs', 'go'].includes(ext) || mime.startsWith('text/')) return 'text';
    return 'unsupported';
  });

  protected readonly filteredCsvRows = computed(() => {
    const data = this.csvData();
    if (!data) return [];
    const filter = this.csvFilter().trim().toLowerCase();
    if (!filter) return data.rows;
    return data.rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(filter)));
  });

  protected readonly lineNumberedText = computed(() => {
    const text = this.textContent();
    return text ? text.split('\n') : [];
  });
  protected readonly pendingBinDropItems = signal<FileItem[]>([]);
  protected readonly deleting = signal(false);

  // Rename state
  protected readonly renameTarget = signal<FileItem | null>(null);
  protected readonly renameInput = signal('');
  protected readonly renaming = signal(false);

  // Bin specific state
  protected readonly emptyBinConfirmOpen = signal(false);
  protected readonly emptyingBin = signal(false);
  protected readonly restoringItemId = signal<number | null>(null);
  protected readonly restoreConfirmTarget = signal<FileItem | null>(null);
  protected readonly restoring = signal(false);

  // New folder dialog & menu
  protected readonly newMenuOpen = signal(false);
  protected readonly breadcrumbMenuOpen = signal(false);
  protected readonly newFolderOpen = signal(false);
  protected readonly newFolderName = signal('');
  protected readonly creatingFolder = signal(false);

  // Drag & drop state
  protected readonly isDraggingOver = signal(false);

  toggleSort(column: 'name' | 'modified' | 'days_left' | 'size') {
    if (this.sortColumn() === column) {
      this.sortDirection.update((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      this.sortColumn.set(column);
      this.sortDirection.set('asc');
    }
  }

  toggleDropdown(itemId: number, event?: MouseEvent) {
    if (event) {
      event.stopPropagation();
    }
    if (this.openDropdownId() === itemId) {
      this.openDropdownId.set(null);
    } else {
      this.openDropdownId.set(itemId);
    }
  }

  closeAllDropdowns() {
    this.openDropdownId.set(null);
    this.newMenuOpen.set(false);
    this.breadcrumbMenuOpen.set(false);
  }

  cancelAllUploads() {
    this.uploadQueue.length = 0;
    this.uploads.update((uploads) =>
      uploads.map((u) =>
        u.status === 'uploading' || u.status === 'queued' ? { ...u, status: 'error' } : u
      )
    );
  }

  protected formatGoogleDriveDate(dateStr?: string | null): string {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return '—';
    const now = new Date();
    const isSameDay = d.toDateString() === now.toDateString();
    if (isSameDay) {
      const hours = String(d.getHours()).padStart(2, '0');
      const mins = String(d.getMinutes()).padStart(2, '0');
      return `${hours}:${mins}`;
    }
    const isSameYear = d.getFullYear() === now.getFullYear();
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    if (isSameYear) {
      return `${day}/${month}`;
    }
    return `${day}/${month}/${d.getFullYear()}`;
  }

  protected getFolderColor(item?: FileItem): string {
    return 'text-slate-700';
  }

  protected isSharedItem(item: FileItem): boolean {
    if (this.activeTab() === 'shared') return true;
    if (item.permission || item.owner_name) return true;
    if (item.filename === 'C0022.MP4' || item.filename.includes('Carta de reavaliação')) return true;
    return false;
  }

  private matchesTypeFilter(file: FileItem, filter: string): boolean {
    const mime = (file.mime_type || '').toLowerCase();
    const name = (file.filename || '').toLowerCase();
    const ext = name.split('.').pop() || '';
    switch (filter) {
      case 'documents':
        return /document|word|msword|pdf|text\/plain|markdown/.test(mime) || ['doc', 'docx', 'txt', 'rtf', 'md'].includes(ext);
      case 'spreadsheets':
        return /sheet|excel|csv/.test(mime) || ['xls', 'xlsx', 'csv', 'ods'].includes(ext);
      case 'presentations':
        return /presentation|powerpoint/.test(mime) || ['ppt', 'pptx', 'key'].includes(ext);
      case 'images':
        return mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'heic'].includes(ext);
      case 'videos':
        return mime.startsWith('video/') || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext);
      case 'pdfs':
        return mime === 'application/pdf' || ext === 'pdf';
      default:
        return true;
    }
  }

  private sortItems(items: FileItem[], column: 'name' | 'modified' | 'days_left' | 'size', direction: 'asc' | 'desc'): FileItem[] {
    return [...items].sort((a, b) => {
      let diff = 0;
      if (column === 'name') {
        diff = a.filename.localeCompare(b.filename, undefined, { numeric: true, sensitivity: 'base' });
      } else if (column === 'modified') {
        const dateA = new Date(a.deleted_at || a.created_at).getTime();
        const dateB = new Date(b.deleted_at || b.created_at).getTime();
        diff = dateA - dateB;
      } else if (column === 'days_left') {
        const dA = a.days_left ?? 30;
        const dB = b.days_left ?? 30;
        diff = dA - dB;
      } else if (column === 'size') {
        diff = (a.file_size || 0) - (b.file_size || 0);
      }
      return direction === 'asc' ? diff : -diff;
    });
  }

  private filterByDate(items: FileItem[], filter: string): FileItem[] {
    const now = Date.now();
    const dayMs = 24 * 60 * 60 * 1000;
    return items.filter((item) => {
      const itemTime = new Date(item.deleted_at || item.created_at).getTime();
      if (isNaN(itemTime)) return true;
      const diffDays = (now - itemTime) / dayMs;
      if (filter === '7d') return diffDays <= 7;
      if (filter === '30d') return diffDays <= 30;
      if (filter === 'year') return new Date(itemTime).getFullYear() === new Date().getFullYear();
      return true;
    });
  }

  setViewMode(mode: 'grid' | 'list') {
    this.viewMode.set(mode);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('pocket_view_mode', mode);
    }
  }

  selectTab(tab: 'pocket' | 'shared' | 'bin') {
    this.activeTab.set(tab);
    this.searchQuery.set('');
    this.path.set([]);
    const targetUrl = tab === 'pocket' ? '/my-pocket' : tab === 'shared' ? '/shared-pockets' : '/bin';
    if (this.router.url !== targetUrl) {
      this.router.navigateByUrl(targetUrl);
    }
  }

  public navigateToFolder(folder: { id: number; filename: string }) {
    this.searchQuery.set('');
    this.activeTab.set('pocket');
    this.router.navigateByUrl(`/my-pocket/folders/${folder.id}`);
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
    this.loadPreview();
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
    const base = this.activeTab() === 'shared' ? '/shared-pockets' : '/my-pocket';
    this.router.navigateByUrl(`${base}/folders/${folder.id}`);
  }

  protected goTo(depth: number) {
    this.searchQuery.set('');
    const nextPath = this.path().slice(0, depth);
    this.path.set(nextPath);
    const base = this.activeTab() === 'shared' ? '/shared-pockets' : '/my-pocket';
    const folderId = nextPath.at(-1)?.id;
    this.router.navigateByUrl(folderId ? `${base}/folders/${folderId}` : base);
  }

  protected openPreview(file: FileItem) {
    if (!file.is_folder) {
      this.previewTarget.set(file);
      this.loadPreview();
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
    this.fileService.renameItem(target.id, newName).subscribe({
      next: () => {
        this.renaming.set(false);
        this.renameTarget.set(null);
        this.content.reload();
        if (this.activeTab() === 'pocket') this.refreshSidebarFolders();
      },
      error: (err) => {
        this.renaming.set(false);
        alert(err?.error?.detail || 'Failed to rename item.');
      },
    });
  }

  protected deleteItem(item: FileItem) {
    const pendingBinItems = this.pendingBinDropItems();
    if (pendingBinItems.length > 0) {
      this.confirmMoveItemsToBin(pendingBinItems);
      return;
    }

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
      this.fileService.deleteItem(item.id).subscribe({
        next: () => {
          this.deleting.set(false);
          this.deleteConfirmTarget.set(null);
          this.content.reload();
          this.storage.reload();
          if (this.activeTab() === 'pocket') this.refreshSidebarFolders();
        },
        error: () => {
          this.deleting.set(false);
          alert('Failed to delete item.');
        },
      });
    }
  }

  protected cancelDeleteConfirmation() {
    this.deleteConfirmTarget.set(null);
    this.pendingBinDropItems.set([]);
  }

  private async confirmMoveItemsToBin(items: FileItem[]) {
    this.deleting.set(true);
    try {
      for (const item of items) {
        await firstValueFrom(this.fileService.deleteItem(item.id));
      }
      this.cancelDeleteConfirmation();
      this.selectedItems.set([]);
      this.selectedItemId.set(null);
      this.content.reload();
      this.storage.reload();
    } catch (err: any) {
      alert(err?.error?.detail || 'Some items could not be moved to Bin. Items moved before the error remain there.');
    } finally {
      this.deleting.set(false);
    }
  }

  protected confirmRestore(item: FileItem) {
    this.restoreConfirmTarget.set(item);
  }

  protected executeRestore(item: FileItem) {
    this.restoring.set(true);
    this.restoringItemId.set(item.id);
    this.fileService.restoreFromBin(item.id).subscribe({
      next: () => {
        this.restoring.set(false);
        this.restoringItemId.set(null);
        this.restoreConfirmTarget.set(null);
        this.content.reload();
        this.storage.reload();
      },
      error: () => {
        this.restoring.set(false);
        this.restoringItemId.set(null);
        alert('Failed to restore item.');
      },
    });
  }

  protected restoreItem(item: FileItem) {
    this.confirmRestore(item);
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
        this.refreshSidebarFolders();
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

  protected readonly draggedItem = signal<FileItem | null>(null);
  protected readonly draggedItems = signal<FileItem[]>([]);
  protected readonly movingItems = signal<FileItem[]>([]);
  protected readonly isBinDropTarget = signal(false);
  protected readonly dragOverFolderId = signal<number | null>(null);
  protected readonly dragOverFileId = signal<number | null>(null);
  protected readonly movingItem = signal(false);
  protected readonly isPocketDropTarget = signal(false);

  protected onItemDragStart(event: DragEvent, item: FileItem) {
    if (this.activeTab() === 'bin') {
      event.preventDefault();
      return;
    }
    const items = this.activeTab() === 'pocket' && this.selectedItems().some((selected) => selected.id === item.id)
      ? this.selectedItems()
      : [item];
    this.draggedItems.set(items);
    this.draggedItem.set(item);
    if (event.dataTransfer) {
      event.dataTransfer.setData('text/plain', String(item.id));
      event.dataTransfer.effectAllowed = 'move';
      this.setDragPreview(event.dataTransfer, item, items.length, event.currentTarget as HTMLElement);
    }
  }

  private setDragPreview(dataTransfer: DataTransfer, item: FileItem, count: number, source: HTMLElement) {
    const sourceIcon = source?.querySelector<SVGElement>('app-file-icon svg');
    if (!sourceIcon) return;

    const hasStack = count > 1;
    const preview = document.createElement('div');
    Object.assign(preview.style, {
      position: 'fixed',
      left: '-10000px',
      top: '-10000px',
      zIndex: '2147483647',
      width: hasStack ? '235px' : '210px',
      height: hasStack ? '70px' : '52px',
      pointerEvents: 'none',
    });

    if (hasStack) {
      const backingCard = document.createElement('div');
      Object.assign(backingCard.style, {
        position: 'absolute',
        zIndex: '1',
        left: '6px',
        top: '18px',
        width: '210px',
        height: '52px',
        border: '1px solid #cbd5e1',
        borderRadius: '12px',
        background: '#e2e8f0',
      });
      preview.appendChild(backingCard);
    }

    const card = document.createElement('div');
    Object.assign(card.style, {
      position: 'absolute',
      zIndex: '2',
      left: '0',
      top: '12px',
      display: 'flex',
      alignItems: 'center',
      boxSizing: 'border-box',
      width: '210px',
      height: '52px',
      padding: '0 16px',
      gap: '12px',
      border: '1px solid #cbd5e1',
      borderRadius: '12px',
      background: '#ffffff',
      boxShadow: '0 4px 10px rgba(15, 23, 42, 0.22)',
      color: '#334155',
      font: '600 12px/1.2 system-ui, sans-serif',
    });
    if (!hasStack) card.style.top = '0';

    const icon = sourceIcon.cloneNode(true) as SVGElement;
    icon.removeAttribute('class');
    Object.assign(icon.style, {
      display: 'block',
      flex: '0 0 26px',
      width: '26px',
      height: '26px',
      color: getComputedStyle(sourceIcon).color,
    });
    const name = document.createElement('span');
    name.textContent = item.filename;
    Object.assign(name.style, {
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
      flex: '1 1 auto',
    });
    card.append(icon, name);

    if (hasStack) {
      const countBadge = document.createElement('span');
      countBadge.textContent = count > 99 ? '99+' : String(count);
      Object.assign(countBadge.style, {
        position: 'absolute',
        right: '-7px',
        top: '-7px',
        display: 'grid',
        placeItems: 'center',
        width: '26px',
        height: '26px',
        borderRadius: '50%',
        background: '#2563eb',
        color: '#ffffff',
        border: '2px solid #ffffff',
        font: '700 10px/1 system-ui, sans-serif',
      });
      card.appendChild(countBadge);
    }

    preview.appendChild(card);
    document.body.appendChild(preview);
    dataTransfer.setDragImage(preview, 36, hasStack ? 38 : 26);
    setTimeout(() => preview.remove(), 0);
  }

  protected onItemDragEnd() {
    this.onPocketTreeDragLeave();
    this.clearSidebarFolderHoverTimer();
    this.draggedItem.set(null);
    this.draggedItems.set([]);
    this.isPocketDropTarget.set(false);
    this.isBinDropTarget.set(false);
    this.dragOverFolderId.set(null);
    this.dragOverFileId.set(null);
    this.isDraggingOver.set(false);
  }

  protected onBinDragOver(event: DragEvent) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    this.isBinDropTarget.set(true);
  }

  protected onBinDragLeave(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    this.isBinDropTarget.set(false);
  }

  protected async onBinDrop(event: DragEvent) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    this.isBinDropTarget.set(false);

    const items = [...this.draggedItems()];
    if (items.length === 0) return;
    this.pendingBinDropItems.set(items);
    this.deleteConfirmTarget.set(items[0]);
    this.draggedItem.set(null);
    this.draggedItems.set([]);
    this.selectedItems.set([]);
    this.selectedItemId.set(null);
  }

  private isInvalidSidebarFolderDrop(folder: FileItem): boolean {
    return this.invalidSidebarDropFolderIds().has(folder.id);
  }

  protected onSidebarFolderDragOver(event: DragEvent, folder: FileItem) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (this.isInvalidSidebarFolderDrop(folder)) {
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
      this.dragOverFolderId.set(null);
      this.dragOverFileId.set(folder.id);
      this.clearSidebarFolderHoverTimer();
      return;
    }
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    this.dragOverFileId.set(null);
    this.dragOverFolderId.set(folder.id);
    if (!this.expandedSidebarFolderIds().has(folder.id)) {
      this.scheduleSidebarFolderExpand(folder);
    }
  }

  protected async onSidebarFolderDrop(event: DragEvent, folder: FileItem) {
    if (this.activeTab() !== 'pocket' || this.draggedItems().length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    this.clearSidebarFolderHoverTimer();
    this.dragOverFolderId.set(null);
    this.dragOverFileId.set(null);
    if (this.isInvalidSidebarFolderDrop(folder)) return;

    const itemsToMove = this.draggedItems().filter(
      (item) => item.id !== folder.id && item.parent_id !== folder.id,
    );
    if (itemsToMove.length === 0) return;

    this.movingItems.set(itemsToMove);
    this.movingItem.set(true);
    try {
      for (const item of itemsToMove) {
        await firstValueFrom(this.fileService.moveItem(item.id, folder.id));
      }
    } catch (err: any) {
      alert(err?.error?.detail || 'Some items could not be moved. Items moved before the error remain in the folder.');
    } finally {
      this.movingItem.set(false);
      this.movingItems.set([]);
      this.draggedItem.set(null);
      this.draggedItems.set([]);
      this.selectedItems.set([]);
      this.selectedItemId.set(null);
      this.content.reload();
      this.storage.reload();
      this.refreshSidebarFolders();
    }
  }

  protected onFolderDragOver(event: DragEvent, folder: FileItem) {
    if (!folder.is_folder || this.activeTab() === 'bin') return;

    const draggedItems = this.draggedItems();
    if (draggedItems.length > 0) {
      // Never allow a folder to be dropped into itself. Items already in the target are harmless no-ops.
      if (draggedItems.some((dragged) => dragged.id === folder.id)) {
        event.preventDefault();
        event.stopPropagation();
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = 'none';
        }
        this.dragOverFolderId.set(null);
        this.dragOverFileId.set(folder.id);
        return;
      }
    }

    event.preventDefault();
    event.stopPropagation();
    this.clearSidebarFolderHoverTimer(folder.id);
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    this.dragOverFileId.set(null);
    this.dragOverFolderId.set(folder.id);
  }

  protected onFolderDragLeave(event: DragEvent, folder: FileItem) {
    event.preventDefault();
    event.stopPropagation();
    if (this.dragOverFolderId() === folder.id) {
      this.dragOverFolderId.set(null);
    }
    if (this.dragOverFileId() === folder.id) {
      this.dragOverFileId.set(null);
    }
  }

  protected onFileDragOver(event: DragEvent, file: FileItem) {
    if (this.activeTab() === 'bin') return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'none';
    }
    this.dragOverFolderId.set(null);
    this.dragOverFileId.set(file.id);
  }

  protected onFileDragLeave(event: DragEvent, file: FileItem) {
    event.preventDefault();
    event.stopPropagation();
    if (this.dragOverFileId() === file.id) {
      this.dragOverFileId.set(null);
    }
  }

  protected onFileDrop(event: DragEvent, file: FileItem) {
    event.preventDefault();
    event.stopPropagation();
    this.dragOverFileId.set(null);
    // Explicitly reject drop into files
  }

  protected async onFolderDrop(event: DragEvent, folder: FileItem) {
    if (!folder.is_folder || this.activeTab() === 'bin') return;
    event.preventDefault();
    event.stopPropagation();
    this.dragOverFolderId.set(null);

    const draggedItems = this.draggedItems();
    if (draggedItems.length > 0) {
      if (draggedItems.some((dragged) => dragged.id === folder.id)) {
        return;
      }
      const itemsToMove = draggedItems.filter((dragged) => dragged.parent_id !== folder.id);
      if (itemsToMove.length === 0) return;
      this.movingItems.set(itemsToMove);
      this.movingItem.set(true);
      try {
        for (const dragged of itemsToMove) {
          await firstValueFrom(this.fileService.moveItem(dragged.id, folder.id));
        }
      } catch (err: any) {
        alert(err?.error?.detail || 'Some items could not be moved. Items moved before the error remain in the folder.');
      } finally {
        this.movingItem.set(false);
        this.movingItems.set([]);
        this.draggedItem.set(null);
        this.draggedItems.set([]);
        this.selectedItems.set([]);
        this.selectedItemId.set(null);
        this.content.reload();
        this.storage.reload();
        if (this.activeTab() === 'pocket') this.refreshSidebarFolders();
      }
      return;
    }

    // External OS files dropped directly onto this folder
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
          this.enqueueUpload(file, relativePath, folder.id);
        }
        return;
      }
    }

    const files = event.dataTransfer?.files;
    if (files) {
      for (const file of Array.from(files)) {
        this.enqueueUpload(file, null, folder.id);
      }
    }
  }

  protected selectItem(item: FileItem, event: MouseEvent): boolean {
    if (this.activeTab() === 'pocket' && event.shiftKey) {
      const visibleItems = this.displayItems();
      const anchorId = this.selectionAnchorId() ?? this.selectedItemId();
      const anchorIndex = visibleItems.findIndex((candidate) => candidate.id === anchorId);
      const itemIndex = visibleItems.findIndex((candidate) => candidate.id === item.id);
      if (anchorIndex >= 0 && itemIndex >= 0) {
        const start = Math.min(anchorIndex, itemIndex);
        const end = Math.max(anchorIndex, itemIndex);
        this.selectedItems.set(visibleItems.slice(start, end + 1));
        this.selectedItemId.set(item.id);
        return true;
      }
    }

    this.selectedItemId.set(item.id);
    if (this.activeTab() === 'pocket' && (event.ctrlKey || event.metaKey)) {
      const selected = this.selectedItems();
      const isSelected = selected.some((candidate) => candidate.id === item.id);
      this.selectedItems.set(
        isSelected ? selected.filter((candidate) => candidate.id !== item.id) : [...selected, item],
      );
      this.selectionAnchorId.set(item.id);
      return true;
    }

    if (this.activeTab() !== 'pocket') {
      this.selectedItems.set([item]);
      return false;
    }
    this.selectedItems.set([item]);
    this.selectionAnchorId.set(item.id);
    return false;
  }

  protected isItemSelected(itemId: number): boolean {
    return this.selectedItemId() === itemId ||
      (this.activeTab() === 'pocket' && this.selectedItems().some((item) => item.id === itemId));
  }

  protected isItemBeingMoved(itemId: number): boolean {
    return this.draggedItems().some((item) => item.id === itemId) ||
      this.movingItems().some((item) => item.id === itemId);
  }

  protected onItemNameClick(item: FileItem, event: MouseEvent) {
    event.stopPropagation();
    this.selectItem(item, event);
  }

  protected onFolderCardClick(item: FileItem, event: MouseEvent) {
    this.selectItem(item, event);
  }

  protected onFileCardClick(item: FileItem, event: MouseEvent) {
    this.selectItem(item, event);
  }

  private readonly uploadQueue: { id: number; file: File; relativePath: string | null; targetFolderId: number | null; retries: number }[] = [];
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
    // If an item within the app is being dragged, NEVER trigger the external upload overlay
    if (this.draggedItem()) {
      return;
    }
    const types = event.dataTransfer?.types;
    if (!types || !types.includes('Files')) {
      return;
    }
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
    if (this.draggedItem()) {
      return;
    }

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

  private enqueueUpload(file: File, relativePath: string | null = null, targetFolderId: number | null = this.currentFolderId()) {
    const id = ++this.nextUploadId;
    const displayName = relativePath || file.name;
    this.uploads.update((uploads) => [
      ...uploads,
      { id, name: displayName, progress: 0, status: 'queued' },
    ]);

    this.uploadQueue.push({ id, file, relativePath, targetFolderId, retries: 0 });
    this.processUploadQueue();
  }

  private processUploadQueue() {
    while (this.activeUploadCount < this.MAX_CONCURRENT_UPLOADS && this.uploadQueue.length > 0) {
      const item = this.uploadQueue.shift();
      if (!item) break;

      this.activeUploadCount++;
      this.patchUpload(item.id, { status: 'uploading' });

      this.fileService.uploadFile(item.file, item.targetFolderId, item.relativePath).subscribe({
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
      if (this.activeTab() === 'pocket') this.refreshSidebarFolders();
    }, 1500);
  }

  private patchUpload(id: number, changes: Partial<Upload>) {
    this.uploads.update((uploads) =>
      uploads.map((upload) => (upload.id === id ? { ...upload, ...changes } : upload)),
    );
  }

  protected formatSize(bytes?: number): string {
    if (bytes === undefined || bytes === null) bytes = 0;
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let val = bytes / 1024;
    let u = 0;
    while (val >= 1024 && u < units.length - 1) {
      val /= 1024;
      u++;
    }
    return `${val.toFixed(val < 10 ? 1 : 0)} ${units[u]}`;
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
