import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Drive } from '../drive.component';

export interface DriveNavigableItem {
  id: number;
  filename: string;
  mime_type?: string;
  file_size?: number;
  parent_id?: number | null;
}

/**
 * Bridges cross-cutting actions from the app shell (header search, sidebar)
 * to the currently active {@link Drive} instance, and to the router for pure
 * navigation.
 *
 * The Drive component registers itself here on init and unregisters on
 * destroy, so the shell can trigger "navigate to folder", "preview file" and
 * "run a search" without holding a direct reference to the component instance.
 */
@Injectable({ providedIn: 'root' })
export class DriveController {
  private readonly router = inject(Router);
  private drive: Drive | null = null;

  register(drive: Drive): void {
    this.drive = drive;
  }

  unregister(drive: Drive): void {
    if (this.drive === drive) {
      this.drive = null;
    }
  }

  /** Navigate the drive to a specific folder. */
  navigateToFolder(folder: DriveNavigableItem): void {
    this.drive?.navigateToFolder(folder);
  }

  /** Open the preview modal for a file. */
  previewFile(item: DriveNavigableItem): void {
    this.drive?.previewFileById(item);
  }

  /** Run a semantic search inside the drive. */
  setSearch(query: string): void {
    this.drive?.searchQuery.set(query);
  }

  /** Clear any active search in the drive. */
  clearSearch(): void {
    this.drive?.searchQuery.set('');
  }

  /** Programmatic route navigation (used when the drive is not yet active). */
  routeTo(path: string): void {
    this.router.navigateByUrl(path);
  }
}
