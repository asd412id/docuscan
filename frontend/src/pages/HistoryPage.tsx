import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { documentService } from '@/services/documents';
import { useScanStore } from '@/store/scanStore';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { 
  FileText, 
  Trash2, 
  Download, 
  Eye,
  FolderOpen,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
} from 'lucide-react';
import type { Document } from '@/types';

function ThumbnailImage({ doc }: { doc: Document }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;

    const loadThumbnail = async () => {
      setIsLoading(true);
      setError(false);
      
      try {
        // Try thumbnail first, fallback to processed, then original
        const type = doc.status === 'completed' ? 'thumbnail' : 'original';
        url = await documentService.getImageUrl(doc.uuid, type);
        
        if (!cancelled) {
          setImageUrl(url);
          setIsLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setIsLoading(false);
        }
      }
    };

    loadThumbnail();

    return () => {
      cancelled = true;
      if (url) {
        documentService.revokeImageUrl(url);
      }
    };
  }, [doc.uuid, doc.status]);

  if (isLoading) {
    return <Skeleton className="w-full h-full" />;
  }

  if (error || !imageUrl) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <ImageIcon className="w-12 h-12 text-muted-foreground" />
      </div>
    );
  }

  return (
    <img
      src={imageUrl}
      alt={doc.original_filename}
      className="w-full h-full object-cover"
    />
  );
}

export function HistoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setCurrentDocument, setCorners } = useScanStore();
  
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [deleteUuid, setDeleteUuid] = useState<string | null>(null);
  const pageSize = 12;

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await documentService.list(page, pageSize);
      setDocuments(result.documents);
      setTotal(result.total);
    } catch (error) {
      toast.error(t('errors.networkError'));
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [page, t]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleView = async (doc: Document) => {
    // Add document to store and set as current
    setCurrentDocument(doc);
    if (doc.corners) {
      setCorners(doc.corners);
    }
    // Navigate to scan page with the document's step based on status
    navigate('/', { state: { viewDocument: doc } });
  };

  const handleDelete = async () => {
    if (!deleteUuid) return;
    
    try {
      await documentService.delete(deleteUuid);
      setDocuments(prev => prev.filter(d => d.uuid !== deleteUuid));
      setTotal(prev => prev - 1);
      toast.success(t('common.success'));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setDeleteUuid(null);
    }
  };

  const handleDownload = async (doc: Document) => {
    try {
      const type = doc.status === 'completed' ? 'processed' : 'original';
      const url = `/api/documents/${doc.uuid}/${type}`;
      await documentService.downloadFile(url, doc.original_filename);
    } catch {
      toast.error(t('common.error'));
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="container mx-auto p-4 max-w-6xl">
      <div className="flex items-center gap-3 mb-6">
        <FileText className="w-8 h-8 text-primary" />
        <h1 className="text-2xl font-bold">{t('documents.title')}</h1>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="overflow-hidden">
              <Skeleton className="aspect-[4/3] w-full" />
              <CardContent className="p-3 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : documents.length === 0 ? (
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <FolderOpen className="w-16 h-16 text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold mb-2">{t('documents.empty')}</h2>
            <p className="text-muted-foreground mb-4">{t('documents.emptyHint')}</p>
            <Button onClick={() => navigate('/')}>
              {t('scan.upload')}
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {documents.map((doc) => (
              <Card key={doc.uuid} className="overflow-hidden group">
                <div className="relative aspect-[4/3] bg-muted">
                  <ThumbnailImage doc={doc} />
                  {/* Action buttons - always visible on mobile, hover on desktop */}
                  <div className="absolute inset-0 bg-black/50 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <Button size="sm" variant="secondary" onClick={() => handleView(doc)}>
                      <Eye className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => handleDownload(doc)}>
                      <Download className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => setDeleteUuid(doc.uuid)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                  {doc.status === 'completed' && (
                    <span className="absolute top-2 right-2 bg-green-500 text-white text-xs px-2 py-1 rounded">
                      {t('common.done')}
                    </span>
                  )}
                </div>
                <CardContent className="p-3">
                  <p className="font-medium truncate text-sm" title={doc.original_filename}>
                    {doc.original_filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(doc.file_size)} &bull; {formatDate(doc.created_at)}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPage(p => p - 1)}
                disabled={page === 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-muted-foreground px-4">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPage(p => p + 1)}
                disabled={page === totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </>
      )}

      <AlertDialog open={!!deleteUuid} onOpenChange={() => setDeleteUuid(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('common.confirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('documents.deleteConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
