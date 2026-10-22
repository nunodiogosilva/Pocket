import { Component, computed, input } from '@angular/core';

export type FileCategory =
  | 'folder'
  | 'audio'
  | 'video'
  | 'pdf'
  | 'markdown'
  | 'text'
  | 'code'
  | 'image'
  | 'spreadsheet'
  | 'presentation'
  | 'archive'
  | 'document'
  | 'generic';

export function getFileCategory(filename: string, mimeType = '', isFolder = false): FileCategory {
  if (isFolder) return 'folder';

  const ext = (filename.split('.').pop() || '').toLowerCase();
  const mime = (mimeType || '').toLowerCase();

  // 1. Audio
  if (mime.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma', 'opus', 'aiff'].includes(ext)) {
    return 'audio';
  }

  // 2. Video
  if (mime.startsWith('video/') || ['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv', 'm4v', '3gp'].includes(ext)) {
    return 'video';
  }

  // 3. PDF
  if (mime === 'application/pdf' || ext === 'pdf') {
    return 'pdf';
  }

  // 4. Markdown
  if (ext === 'md' || ext === 'markdown' || mime === 'text/markdown') {
    return 'markdown';
  }

  // 5. Code / Development
  if (
    ['js', 'ts', 'jsx', 'tsx', 'py', 'html', 'css', 'scss', 'json', 'yaml', 'yml', 'c', 'cpp', 'h', 'hpp', 'rs', 'go', 'java', 'kt', 'php', 'sh', 'bash', 'zsh', 'sql', 'xml'].includes(ext) ||
    /javascript|typescript|python|json|yaml|xml|x-sh/.test(mime)
  ) {
    return 'code';
  }

  // 6. Text
  if (ext === 'txt' || ext === 'log' || ext === 'ini' || ext === 'conf' || mime === 'text/plain') {
    return 'text';
  }

  // 7. Image
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff'].includes(ext)) {
    return 'image';
  }

  // 8. Spreadsheet
  if (['xlsx', 'xls', 'csv', 'tsv', 'ods'].includes(ext) || /sheet|excel|csv/.test(mime)) {
    return 'spreadsheet';
  }

  // 9. Presentation
  if (['pptx', 'ppt', 'key', 'odp'].includes(ext) || /presentation|powerpoint/.test(mime)) {
    return 'presentation';
  }

  // 10. Archive
  if (['zip', 'tar', 'gz', 'bz2', '7z', 'rar', 'xz', 'tgz'].includes(ext) || /zip|tar|rar|7z|compressed/.test(mime)) {
    return 'archive';
  }

  // 11. Word Document
  if (['docx', 'doc', 'rtf', 'odt'].includes(ext) || /document|msword|wordprocessingml/.test(mime)) {
    return 'document';
  }

  return 'generic';
}

@Component({
  selector: 'app-file-icon',
  templateUrl: './file-icon.component.html',
  standalone: true,
})
export class FileIconComponent {
  readonly filename = input<string>('');
  readonly mimeType = input<string>('');
  readonly isFolder = input<boolean>(false);
  readonly size = input<'sm' | 'md' | 'lg' | 'xl'>('md');
  readonly customClass = input<string>('');

  readonly color = input<string>('');

  readonly category = computed<FileCategory>(() =>
    getFileCategory(this.filename(), this.mimeType(), this.isFolder())
  );

  readonly sizeClass = computed(() => {
    switch (this.size()) {
      case 'sm':
        return 'size-4';
      case 'lg':
        return 'size-8';
      case 'xl':
        return 'size-11';
      case 'md':
      default:
        return 'size-5';
    }
  });

  readonly colorClass = computed(() => {
    if (this.color()) return this.color();
    switch (this.category()) {
      case 'folder':
        return 'text-slate-700';
      case 'audio':
        return 'text-purple-600';
      case 'video':
        return 'text-rose-600';
      case 'pdf':
        return 'text-red-600';
      case 'markdown':
        return 'text-sky-600';
      case 'text':
        return 'text-slate-600';
      case 'code':
        return 'text-emerald-600';
      case 'image':
        return 'text-blue-500';
      case 'spreadsheet':
        return 'text-green-600';
      case 'presentation':
        return 'text-amber-500';
      case 'archive':
        return 'text-amber-700';
      case 'document':
        return 'text-blue-600';
      case 'generic':
      default:
        return 'text-slate-500';
    }
  });
}
