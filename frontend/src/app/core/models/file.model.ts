export interface FileItem {
  id: number;
  filename: string;
  file_size: number;
  mime_type: string;
  parent_id: number | null;
  is_folder: boolean;
  created_at: string;
  is_deleted?: boolean;
  deleted_at?: string | null;
  days_left?: number;
  /** Best-matching text from the file; only set on search results. */
  snippet?: string | null;
  /** Shared metadata */
  owner_name?: string | null;
  owner_login?: string;
  permission?: string;
}

export interface DirectoryContent {
  folders: FileItem[];
  files: FileItem[];
}

export interface SearchSuggestion {
  id: number;
  filename: string;
  is_folder: boolean;
  file_size: number;
  mime_type: string;
  snippet?: string | null;
  parent_id?: number | null;
}

export interface SearchSuggestionsResponse {
  folders: SearchSuggestion[];
  files: SearchSuggestion[];
}

export interface UploadResult {
  status: string;
  file_id: number;
  filename: string;
}

export interface ShareLink {
  share_url: string;
  expires_at: string;
}

export interface UserProfile {
  id: number;
  login: string;
  name: string | null;
  email: string | null;
  profile_pic?: string | null;
}

export interface StorageUsage {
  used_bytes: number;
  total_bytes: number;
  file_count: number;
  folder_count: number;
}

export interface ShareUserResult {
  status: string;
  file_id: number;
  shared_with_login: string;
}
