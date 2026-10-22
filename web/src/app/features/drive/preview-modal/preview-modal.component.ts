import {
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { FileItem, DriveService } from '../services/drive.service';
import { FileIconComponent } from '../../../shared/components/file-icon/file-icon.component';

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

@Component({
  selector: 'app-preview-modal',
  standalone: true,
  imports: [FileIconComponent],
  templateUrl: './preview-modal.component.html',
  styleUrl: './preview-modal.component.css',
})
export class PreviewModal {
  readonly file = input.required<FileItem>();
  readonly closed = output<void>();

  private readonly fileService = inject(DriveService);
  private readonly sanitizer = inject(DomSanitizer);

  @ViewChild('modalContent') modalContent?: ElementRef<HTMLDivElement>;

  protected readonly Math = Math;
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly textContent = signal<string>('');
  protected readonly markdownHtml = signal<string>('');
  protected readonly csvData = signal<CsvData | null>(null);
  protected readonly csvFilter = signal('');
  protected readonly zoomLevel = signal(1);
  protected readonly copySuccess = signal(false);

  protected readonly downloadUrl = computed(() =>
    this.fileService.getFileDownloadUrl(this.file().id)
  );

  protected readonly sanitizedUrl = computed<SafeResourceUrl>(() =>
    this.sanitizer.bypassSecurityTrustResourceUrl(this.downloadUrl())
  );

  protected readonly previewKind = computed<PreviewKind>(() => {
    const f = this.file();
    const ext = (f.filename.split('.').pop() || '').toLowerCase();
    const mime = (f.mime_type || '').toLowerCase();

    if (ext === 'md' || ext === 'markdown') return 'markdown';
    if (ext === 'csv' || ext === 'tsv' || mime === 'text/csv') return 'csv';
    if (ext === 'pdf' || mime === 'application/pdf') return 'pdf';
    if (
      ['mp4', 'mov', 'webm', 'ogg', 'mkv', 'm4v'].includes(ext) ||
      mime.startsWith('video/')
    )
      return 'video';
    if (
      ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'].includes(ext) ||
      mime.startsWith('audio/')
    )
      return 'audio';
    if (
      ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'].includes(ext) ||
      mime.startsWith('image/')
    )
      return 'image';
    if (
      [
        'txt', 'json', 'yml', 'yaml', 'xml', 'html', 'css', 'js', 'ts', 'py',
        'sh', 'sql', 'toml', 'ini', 'env', 'log', 'java', 'c', 'cpp', 'rs', 'go'
      ].includes(ext) ||
      mime.startsWith('text/')
    )
      return 'text';

    return 'unsupported';
  });

  protected readonly filteredCsvRows = computed(() => {
    const data = this.csvData();
    if (!data) return [];
    const filter = this.csvFilter().trim().toLowerCase();
    if (!filter) return data.rows;
    return data.rows.filter((row) =>
      row.some((cell) => cell.toLowerCase().includes(filter))
    );
  });

  protected readonly lineNumberedText = computed(() => {
    const text = this.textContent();
    return text ? text.split('\n') : [];
  });

  ngOnInit() {
    this.loadPreview();
  }

  @HostListener('window:keydown.escape')
  onEscape() {
    this.closed.emit();
  }

  protected loadPreview() {
    const kind = this.previewKind();
    if (kind === 'markdown' || kind === 'csv' || kind === 'text') {
      this.loading.set(true);
      this.error.set(null);
      this.fileService.getFileContent(this.file().id).subscribe({
        next: (content) => {
          this.textContent.set(content);
          if (kind === 'markdown') {
            this.markdownHtml.set(this.renderMarkdown(content));
          } else if (kind === 'csv') {
            const isTsv = this.file().filename.toLowerCase().endsWith('.tsv');
            this.csvData.set(this.parseCsv(content, isTsv ? '\t' : ','));
          }
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set('Failed to fetch file content.');
          this.loading.set(false);
        },
      });
    } else {
      // For media, pdf, and images, browser streams directly via downloadUrl
      this.loading.set(false);
    }
  }

  protected copyContent() {
    const text = this.textContent();
    if (text) {
      navigator.clipboard.writeText(text).then(() => {
        this.copySuccess.set(true);
        setTimeout(() => this.copySuccess.set(false), 2000);
      });
    }
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

  protected formatSize(bytes: number): string {
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

  /** Client-side RFC 4180 CSV parser */
  private parseCsv(text: string, delimiter = ','): CsvData {
    const rows: string[][] = [];
    let currentRow: string[] = [];
    let currentCell = '';
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      const nextChar = text[i + 1];

      if (char === '"') {
        if (inQuotes && nextChar === '"') {
          currentCell += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === delimiter && !inQuotes) {
        currentRow.push(currentCell.trim());
        currentCell = '';
      } else if ((char === '\r' || char === '\n') && !inQuotes) {
        if (char === '\r' && nextChar === '\n') {
          i++;
        }
        currentRow.push(currentCell.trim());
        if (currentRow.length > 1 || (currentRow.length === 1 && currentRow[0] !== '')) {
          rows.push(currentRow);
        }
        currentRow = [];
        currentCell = '';
      } else {
        currentCell += char;
      }
    }

    if (currentCell !== '' || currentRow.length > 0) {
      currentRow.push(currentCell.trim());
      if (currentRow.length > 1 || (currentRow.length === 1 && currentRow[0] !== '')) {
        rows.push(currentRow);
      }
    }

    if (rows.length === 0) {
      return { headers: [], rows: [] };
    }

    const headers = rows[0];
    const dataRows = rows.slice(1);
    return { headers, rows: dataRows };
  }

  /** Pure Client-Side Markdown Parser */
  private renderMarkdown(md: string): string {
    const escapeHtml = (str: string) =>
      str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

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
      if (inList) {
        output.push(listType === 'ul' ? '</ul>' : '</ol>');
        inList = false;
      }
    };

    const flushTable = () => {
      if (inTable && tableBuffer.length > 0) {
        output.push(this.renderMarkdownTable(tableBuffer));
        inTable = false;
        tableBuffer = [];
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Fenced Code Blocks
      if (line.trim().startsWith('```')) {
        if (inCodeBlock) {
          flushList();
          output.push(
            `<div class="my-4 rounded-xl overflow-hidden bg-slate-900 border border-slate-800 shadow-sm"><div class="flex items-center justify-between px-4 py-1.5 bg-slate-800/80 text-xs text-slate-400 font-mono"><span>${escapeHtml(
              codeLang || 'plaintext'
            )}</span></div><pre class="p-4 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed"><code>${escapeHtml(
              codeBuffer.join('\n')
            )}</code></pre></div>`
          );
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

      if (inCodeBlock) {
        codeBuffer.push(line);
        continue;
      }

      // Tables
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        flushList();
        inTable = true;
        tableBuffer.push(line);
        continue;
      } else if (inTable) {
        flushTable();
      }

      // Horizontal Rules
      if (/^(\*\*\*|---|___)$/.test(line.trim())) {
        flushList();
        output.push('<hr class="my-6 border-slate-200 dark:border-slate-700" />');
        continue;
      }

      // Headings
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

      // Blockquotes
      if (line.startsWith('>')) {
        flushList();
        const quoteText = this.inlineMarkdown(escapeHtml(line.replace(/^>\s?/, '')));
        output.push(
          `<blockquote class="my-3 border-l-4 border-blue-500 bg-blue-50/60 px-4 py-2 text-sm italic text-slate-700 rounded-r-lg">${quoteText}</blockquote>`
        );
        continue;
      }

      // Lists
      const ulMatch = line.match(/^(\*|-|\+)\s+(.*)$/);
      const olMatch = line.match(/^(\d+)\.\s+(.*)$/);

      if (ulMatch) {
        if (!inList || listType !== 'ul') {
          flushList();
          output.push('<ul class="my-2.5 list-disc space-y-1.5 pl-6 text-sm text-slate-800">');
          inList = true;
          listType = 'ul';
        }
        output.push(`<li>${this.inlineMarkdown(escapeHtml(ulMatch[2]))}</li>`);
        continue;
      }

      if (olMatch) {
        if (!inList || listType !== 'ol') {
          flushList();
          output.push('<ol class="my-2.5 list-decimal space-y-1.5 pl-6 text-sm text-slate-800">');
          inList = true;
          listType = 'ol';
        }
        output.push(`<li>${this.inlineMarkdown(escapeHtml(olMatch[2]))}</li>`);
        continue;
      }

      flushList();

      // Blank line
      if (!line.trim()) {
        continue;
      }

      // Regular Paragraph
      output.push(`<p class="my-2 text-sm leading-relaxed text-slate-800">${this.inlineMarkdown(escapeHtml(line))}</p>`);
    }

    flushList();
    flushTable();

    return output.join('\n');
  }

  private inlineMarkdown(str: string): string {
    return str
      // Bold + Italic
      .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
      // Bold
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>')
      // Italic
      .replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
      // Strikethrough
      .replace(/~~(.*?)~~/g, '<del class="line-through text-slate-400">$1</del>')
      // Inline Code
      .replace(
        /`([^`]+)`/g,
        '<code class="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-pink-600 border border-slate-200">$1</code>'
      )
      // Links
      .replace(
        /\[(.*?)\]\((.*?)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline font-medium hover:text-blue-800">$1</a>'
      );
  }

  private renderMarkdownTable(lines: string[]): string {
    if (lines.length < 2) return '';
    const parseRow = (line: string) =>
      line
        .trim()
        .replace(/^\||\|$/g, '')
        .split('|')
        .map((cell) => cell.trim());

    const headerCols = parseRow(lines[0]);
    const bodyLines = lines.slice(2); // Skip separator row

    let html = `<div class="my-4 overflow-x-auto rounded-xl border border-slate-200 shadow-sm"><table class="w-full text-left text-xs divide-y divide-slate-200">`;
    html += `<thead class="bg-slate-50 font-semibold text-slate-700"><tr>`;
    for (const h of headerCols) {
      html += `<th class="px-4 py-2.5">${this.inlineMarkdown(h)}</th>`;
    }
    html += `</tr></thead><tbody class="divide-y divide-slate-100 bg-white">`;

    for (const rowLine of bodyLines) {
      const cols = parseRow(rowLine);
      html += `<tr class="hover:bg-slate-50/80">`;
      for (let c = 0; c < headerCols.length; c++) {
        html += `<td class="px-4 py-2 text-slate-700">${this.inlineMarkdown(cols[c] || '')}</td>`;
      }
      html += `</tr>`;
    }

    html += `</tbody></table></div>`;
    return html;
  }
}
