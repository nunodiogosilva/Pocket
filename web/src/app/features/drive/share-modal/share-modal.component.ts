import { Component, ElementRef, OnInit, afterNextRender, inject, input, output, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FileItem, DriveService, ShareLink } from '../services/drive.service';

@Component({
  imports: [DatePipe],
  selector: 'app-share-modal',
  styleUrl: './share-modal.component.css',
  templateUrl: './share-modal.component.html',
})
export class ShareModal implements OnInit {
  private readonly fileService = inject(DriveService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  readonly file = input.required<FileItem>();
  readonly closed = output<void>();

  protected readonly link = signal<ShareLink | null>(null);
  protected readonly error = signal(false);
  protected readonly copied = signal(false);

  // User-to-user sharing
  protected readonly userShareInput = signal('');
  protected readonly userShareLoading = signal(false);
  protected readonly userShareSuccess = signal<string | null>(null);
  protected readonly userShareError = signal<string | null>(null);

  constructor() {
    afterNextRender(() => this.dialog().nativeElement.showModal());
  }

  ngOnInit() {
    this.fileService.generateShareLink(this.file().id).subscribe({
      next: (link) => this.link.set(link),
      error: () => this.error.set(true),
    });
  }

  protected async copy(input: HTMLInputElement) {
    try {
      await navigator.clipboard.writeText(input.value);
    } catch {
      input.select();
      document.execCommand('copy');
    }
    this.copied.set(true);
  }

  protected shareWithUser() {
    const login = this.userShareInput().trim();
    if (!login) return;

    this.userShareLoading.set(true);
    this.userShareError.set(null);
    this.userShareSuccess.set(null);

    this.fileService.shareWithUser(this.file().id, login, 'read').subscribe({
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
}
