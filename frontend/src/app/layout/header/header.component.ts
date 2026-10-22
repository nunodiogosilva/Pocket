import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { rxResource, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, distinctUntilChanged, switchMap, of } from 'rxjs';
import { UserService } from '../../core/services/user.service';
import { SearchService } from '../../features/search/search.service';
import { SearchSuggestion, SearchSuggestionsResponse } from '../../core/models/file.model';
import { DriveController } from '../../features/drive/services/drive-controller';
import { FileIconComponent } from '../../shared/components/file-icon/file-icon.component';
import { FileSizePipe } from '../../shared/pipes/file-size.pipe';

/**
 * Top bar: brand, global semantic-search bar (with autocomplete suggestions)
 * and the Tailscale identity badge.
 */
@Component({
  selector: 'app-header',
  imports: [FileIconComponent, FileSizePipe],
  templateUrl: './header.component.html',
})
export class HeaderComponent {
  private readonly userService = inject(UserService);
  private readonly searchService = inject(SearchService);
  private readonly driveController = inject(DriveController);

  @ViewChild('searchInput') searchInputRef?: ElementRef<HTMLInputElement>;

  protected readonly query = signal('');
  protected readonly currentSearchText = signal('');
  protected readonly suggestions = signal<SearchSuggestionsResponse>({ folders: [], files: [] });
  protected readonly suggestionsOpen = signal(false);
  protected readonly isSearchingSuggestions = signal(false);

  protected readonly currentUser = rxResource({
    stream: () => this.userService.getCurrentUser(),
  });

  private readonly searchInput$ = new Subject<string>();

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
          return this.searchService.suggest(trimmed, 8);
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
        error: () => this.isSearchingSuggestions.set(false),
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
    if (
      this.currentSearchText().trim() &&
      (this.suggestions().folders.length > 0 || this.suggestions().files.length > 0)
    ) {
      this.suggestionsOpen.set(true);
    }
  }

  protected closeSuggestions() {
    // Slight delay to allow suggestion mousedown/click to execute.
    setTimeout(() => this.suggestionsOpen.set(false), 200);
  }

  protected executeSearch(val: string) {
    const trimmed = val.trim();
    this.query.set(trimmed);
    this.suggestionsOpen.set(false);
    this.driveController.setSearch(trimmed);
  }

  protected clearSearch() {
    this.query.set('');
    this.currentSearchText.set('');
    this.suggestions.set({ folders: [], files: [] });
    this.suggestionsOpen.set(false);
    if (this.searchInputRef) {
      this.searchInputRef.nativeElement.value = '';
    }
    this.driveController.clearSearch();
  }

  protected selectFolderSuggestion(folder: SearchSuggestion) {
    this.suggestionsOpen.set(false);
    this.currentSearchText.set('');
    if (this.searchInputRef) this.searchInputRef.nativeElement.value = '';
    this.driveController.navigateToFolder(folder);
  }

  protected selectFileSuggestion(file: SearchSuggestion) {
    this.suggestionsOpen.set(false);
    this.driveController.previewFile(file);
  }
}
