export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Document {
  id: number;
  uuid: string;
  original_filename: string;
  stored_filename: string;
  file_size: number;
  mime_type: string;
  status: 'pending' | 'detected' | 'processing' | 'completed' | 'failed';
  created_at: string;
  thumbnail_url?: string;
  processed_url?: string;
  corners?: CornerPoints;
}

export interface CornerPoints {
  top_left: [number, number];
  top_right: [number, number];
  bottom_right: [number, number];
  bottom_left: [number, number];
}

export interface ScanSettings {
  filter_mode: 'color' | 'grayscale' | 'bw' | 'scan';
  brightness: number;
  contrast: number;
  rotation: number;
  auto_enhance: boolean;
}

export interface DetectResponse {
  document_uuid: string;
  corners: CornerPoints;
  confidence: number;
  preview_url: string;
}

export interface ProcessResponse {
  document_uuid: string;
  processed_url: string;
  thumbnail_url: string;
  status: string;
}

export interface OCRResponse {
  document_uuid: string;
  text: string;
  confidence: number;
  language: string;
}

export interface ExportResponse {
  download_url: string;
  filename: string;
  file_size: number;
  expires_at: string;
}

export type PdfPageSize = 'auto' | 'a4' | 'letter' | 'legal' | 'folio';
