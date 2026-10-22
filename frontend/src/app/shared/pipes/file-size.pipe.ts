import { Pipe, PipeTransform } from '@angular/core';

/**
 * Formats a byte count into a human readable size (KB, MB, GB, TB).
 *
 * Replaces the several private `formatSize` helpers that were duplicated
 * across the app shell and the drive feature.
 */
@Pipe({ name: 'fileSize' })
export class FileSizePipe implements PipeTransform {
  transform(bytes?: number | null): string {
    if (bytes === undefined || bytes === null || bytes === 0) {
      return '0 B';
    }
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
}
