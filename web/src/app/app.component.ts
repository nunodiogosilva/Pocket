import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { rxResource, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, distinctUntilChanged, switchMap, of } from 'rxjs';
import { FileManager } from './components/file-manager/file-manager.component';
import { FileIconComponent } from './components/file-icon/file-icon.component';
import { FileService, SearchSuggestion, SearchSuggestionsResponse } from './services/file.service';

@Component({
  imports: [FileManager, FileIconComponent],
  selector: 'app-root',
  styleUrl: './app.component.css',
  templateUrl: './app.component.html',
})
export class App {
  private readonly fileService = inject(FileService);

  @ViewChild('fileManager') fileManager?: FileManager;
  @ViewChild('searchInput') searchInputRef?: ElementRef<HTMLInputElement>;

  protected readonly query = signal('');
  protected readonly currentSearchText = signal('');
  protected readonly suggestions = signal<SearchSuggestionsResponse>({ folders: [], files: [] });
  protected readonly suggestionsOpen = signal(false);
  protected readonly isSearchingSuggestions = signal(false);

  private readonly searchInput$ = new Subject<string>();

  protected readonly currentUser = rxResource({
    stream: () => this.fileService.getCurrentUser(),
  });

  constructor() {
    this.searchInput$
      .pipe(
        debounceTime(200),
        distinctUntilChanged(),
        switchMap((term) => {
          const trimmed = term.trim();
          if (!trimmed) {
            this.isSearchingSuggestions.set(false);
            return of<SearchSuggestionsResponse>({ folders: [], files: [] });
          }
          this.isSearchingSuggestions.set(true);
          return this.fileService.getSearchSuggestions(trimmed, 8);
        }),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (res) => {
          this.isSearchingSuggestions.set(false);
          this.suggestions.set(res);
          if (this.currentSearchText().trim()) {
            this.suggestionsOpen.set(true);
          }
        },
        error: () => {
          this.isSearchingSuggestions.set(false);
        },
      });
  }

  protected onSearchInput(val: string) {
    this.currentSearchText.set(val);
    if (!val.trim()) {
      this.suggestions.set({ folders: [], files: [] });
      this.suggestionsOpen.set(false);
      return;
    }
    this.searchInput$.next(val);
  }

  protected onSearchFocus() {
    if (this.currentSearchText().trim() && (this.suggestions().folders.length > 0 || this.suggestions().files.length > 0)) {
      this.suggestionsOpen.set(true);
    }
  }

  protected closeSuggestions() {
    // Slight delay to allow suggestion mousedown/click to execute
    setTimeout(() => {
      this.suggestionsOpen.set(false);
    }, 200);
  }

  protected executeSearch(val: string) {
    const trimmed = val.trim();
    this.query.set(trimmed);
    this.suggestionsOpen.set(false);
  }

  protected clearSearch() {
    this.query.set('');
    this.currentSearchText.set('');
    this.suggestions.set({ folders: [], files: [] });
    this.suggestionsOpen.set(false);
    if (this.searchInputRef) {
      this.searchInputRef.nativeElement.value = '';
    }
  }

  protected selectFolderSuggestion(folder: SearchSuggestion) {
    this.suggestionsOpen.set(false);
    this.currentSearchText.set('');
    if (this.searchInputRef) {
      this.searchInputRef.nativeElement.value = '';
    }
    this.fileManager?.navigateToFolder(folder);
  }

  protected selectFileSuggestion(file: SearchSuggestion) {
    this.suggestionsOpen.set(false);
    this.fileManager?.openPreviewById(file);
  }

  protected formatSize(bytes: number): string {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB'];
    let val = bytes / 1024;
    let unit = 0;
    while (val >= 1024 && unit < units.length - 1) {
      val /= 1024;
      unit++;
    }
    return `${val.toFixed(val < 10 ? 1 : 0)} ${units[unit]}`;
  }

  protected fileIconColor(type: string): string {
    if (!type) return 'text-slate-500';
    if (type.startsWith('image/')) return 'text-red-500';
    if (type.startsWith('video/')) return 'text-rose-700';
    if (type.startsWith('audio/')) return 'text-purple-600';
    if (type === 'application/pdf') return 'text-red-700';
    if (/zip|tar|rar|7z/.test(type)) return 'text-amber-600';
    if (/sheet|excel|csv/.test(type)) return 'text-green-600';
    if (type.startsWith('text/') || /json|javascript|python/.test(type)) return 'text-blue-600';
    return 'text-slate-500';
  }
}

