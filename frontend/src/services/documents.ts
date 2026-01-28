import api from './api';
import type { 
  Document, 
  DetectResponse, 
  ProcessResponse, 
  OCRResponse, 
  ExportResponse,
  CornerPoints,
  ScanSettings,
  PdfPageSize
} from '@/types';

// Background task types
export interface BackgroundTaskResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  current: number;
  total: number;
  percentage: number;
  message: string;
  result?: Record<string, unknown>;
}

export const documentService = {
  async upload(file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post<Document>('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  
  async uploadBatch(files: File[]): Promise<Document[]> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    
    const response = await api.post<Document[]>('/documents/upload-batch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  
  async list(page = 1, pageSize = 20): Promise<{ documents: Document[]; total: number }> {
    const response = await api.get('/documents/', { params: { page, page_size: pageSize } });
    return response.data;
  },
  
  async get(uuid: string): Promise<Document> {
    const response = await api.get<Document>(`/documents/${uuid}`);
    return response.data;
  },
  
  async delete(uuid: string): Promise<void> {
    await api.delete(`/documents/${uuid}`);
  },

  async batchDelete(uuids: string[]): Promise<void> {
    await api.post('/documents/batch-delete', { document_uuids: uuids });
  },
  
  async getImageUrl(uuid: string, type: 'original' | 'processed' | 'thumbnail'): Promise<string> {
    const response = await api.get(`/documents/${uuid}/${type}`, {
      responseType: 'blob',
    });
    return URL.createObjectURL(response.data);
  },

  revokeImageUrl(url: string): void {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
  },

  async downloadFile(url: string, filename: string): Promise<void> {
    // Remove /api prefix if present since axios baseURL already has it
    const cleanUrl = url.startsWith('/api') ? url.slice(4) : url;
    const response = await api.get(cleanUrl, {
      responseType: 'blob',
    });
    
    const blobUrl = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
  },
};

export const scanService = {
  async detectEdges(documentUuid: string): Promise<DetectResponse> {
    const response = await api.post<DetectResponse>(`/scan/detect/${documentUuid}`);
    return response.data;
  },
  
  async process(
    documentUuid: string, 
    corners?: CornerPoints, 
    settings?: ScanSettings
  ): Promise<ProcessResponse> {
    const response = await api.post<ProcessResponse>('/scan/process', {
      document_uuid: documentUuid,
      corners,
      settings: settings || {
        filter_mode: 'color',
        brightness: 0,
        contrast: 0,
        rotation: 0,
        auto_enhance: true,
      },
    });
    return response.data;
  },
  
  async bulkProcess(
    documents: Array<{
      document_uuid: string;
      corners?: CornerPoints;
      settings?: ScanSettings;
    }>,
    defaultSettings?: ScanSettings
  ): Promise<ProcessResponse[]> {
    const response = await api.post<ProcessResponse[]>('/scan/bulk-process', {
      documents,
      default_settings: defaultSettings || {
        filter_mode: 'color',
        brightness: 0,
        contrast: 0,
        rotation: 0,
        auto_enhance: true,
      },
    });
    return response.data;
  },
  
  async ocr(documentUuid: string, lang = 'eng+ind'): Promise<OCRResponse> {
    const response = await api.post<OCRResponse>(`/scan/ocr/${documentUuid}`, null, {
      params: { lang },
    });
    return response.data;
  },
  
  async export(
    documentUuids: string[], 
    format: 'pdf' | 'png' | 'jpg' | 'zip' = 'pdf', 
    quality = 90,
    mergePdf = true,
    pageSize: PdfPageSize = 'auto',
    searchable = false
  ): Promise<ExportResponse> {
    const response = await api.post<ExportResponse>('/scan/export', {
      document_uuids: documentUuids,
      format,
      quality,
      merge_pdf: mergePdf,
      page_size: pageSize,
      searchable,
    });
    return response.data;
  },
};

// Background task service
export const taskService = {
  /**
   * Start background processing for a single document
   */
  async startProcess(
    documentUuid: string,
    corners?: CornerPoints,
    settings?: ScanSettings
  ): Promise<BackgroundTaskResponse> {
    const response = await api.post<BackgroundTaskResponse>(`/tasks/process/${documentUuid}`, {
      corners,
      settings_data: settings,
    });
    return response.data;
  },

  /**
   * Start background processing for multiple documents
   */
  async startBulkProcess(
    documents: Array<{
      document_uuid: string;
      corners?: CornerPoints;
      settings?: ScanSettings;
    }>,
    defaultSettings?: ScanSettings
  ): Promise<BackgroundTaskResponse> {
    const response = await api.post<BackgroundTaskResponse>('/tasks/bulk-process', {
      documents: documents.map(d => ({
        document_uuid: d.document_uuid,
        corners: d.corners ? {
          top_left: d.corners.top_left,
          top_right: d.corners.top_right,
          bottom_right: d.corners.bottom_right,
          bottom_left: d.corners.bottom_left,
        } : undefined,
        settings: d.settings,
      })),
      default_settings: defaultSettings,
    });
    return response.data;
  },

  /**
   * Get current status of a background task
   */
  async getStatus(taskId: string): Promise<TaskStatusResponse> {
    const response = await api.get<TaskStatusResponse>(`/tasks/status/${taskId}`);
    return response.data;
  },

  /**
   * Cancel a running background task
   */
  async cancel(taskId: string): Promise<void> {
    await api.post(`/tasks/cancel/${taskId}`);
  },

  /**
   * Apply completed task results to the database
   */
  async applyResults(taskId: string): Promise<{ status: string; documents_updated: number }> {
    const response = await api.post<{ status: string; documents_updated: number }>(
      `/tasks/complete/${taskId}`
    );
    return response.data;
  },

  /**
   * Poll task status until completion or timeout
   */
  async pollUntilComplete(
    taskId: string,
    onProgress?: (status: TaskStatusResponse) => void,
    pollInterval = 1000,
    maxAttempts = 600 // 10 minutes with 1s interval
  ): Promise<TaskStatusResponse> {
    let attempts = 0;
    
    while (attempts < maxAttempts) {
      const status = await this.getStatus(taskId);
      
      if (onProgress) {
        onProgress(status);
      }
      
      if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
        return status;
      }
      
      await new Promise(resolve => setTimeout(resolve, pollInterval));
      attempts++;
    }
    
    throw new Error('Task polling timeout');
  },
};
