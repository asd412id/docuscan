import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { documentService } from '@/services/documents';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle2, GripVertical } from 'lucide-react';
import type { Document } from '@/types';

interface ThumbnailGridProps {
  documents: Document[];
  currentUuid?: string;
  selectedUuids?: string[];
  onSelect: (doc: Document) => void;
  onMultiSelect?: (uuid: string) => void;
  onReorder?: (fromIndex: number, toIndex: number) => void;
  multiSelectMode?: boolean;
}

interface ThumbnailCache {
  [uuid: string]: string;
}

export function ThumbnailGrid({
  documents,
  currentUuid,
  selectedUuids = [],
  onSelect,
  onMultiSelect,
  onReorder,
  multiSelectMode = false,
}: ThumbnailGridProps) {
  const { t } = useTranslation();
  const [thumbnails, setThumbnails] = useState<ThumbnailCache>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  // Track blob URLs for proper cleanup
  const blobUrlsRef = useRef<Set<string>>(new Set());

  // Function to safely revoke a blob URL
  const revokeBlobUrl = useCallback((url: string) => {
    if (url && blobUrlsRef.current.has(url)) {
      documentService.revokeImageUrl(url);
      blobUrlsRef.current.delete(url);
    }
  }, []);

  // Cleanup removed documents' blob URLs
  useEffect(() => {
    const currentUuids = new Set(documents.map(d => d.uuid));
    
    setThumbnails(prev => {
      const newThumbnails: ThumbnailCache = {};
      
      for (const [uuid, url] of Object.entries(prev)) {
        if (currentUuids.has(uuid)) {
          // Keep this thumbnail
          newThumbnails[uuid] = url;
        } else {
          // Document removed, revoke its blob URL
          revokeBlobUrl(url);
        }
      }
      
      return newThumbnails;
    });
  }, [documents, revokeBlobUrl]);

  // Load thumbnails for documents
  useEffect(() => {
    let isMounted = true;

    const loadThumbnails = async () => {
      for (const doc of documents) {
        if (doc.status !== 'completed') continue;

        if (thumbnails[doc.uuid] || loading[doc.uuid]) continue;

        setLoading((prev) => ({ ...prev, [doc.uuid]: true }));

        try {
          const url = await documentService.getImageUrl(doc.uuid, 'thumbnail');
          if (isMounted) {
            blobUrlsRef.current.add(url);
            setThumbnails((prev) => ({ ...prev, [doc.uuid]: url }));
          } else {
            documentService.revokeImageUrl(url);
          }
        } catch {
          // Ignore errors
        } finally {
          if (isMounted) {
            setLoading((prev) => ({ ...prev, [doc.uuid]: false }));
          }
        }
      }
    };

    loadThumbnails();

    return () => {
      isMounted = false;
    };
  }, [documents, thumbnails, loading]);

  // Cleanup all blob URLs on unmount
  useEffect(() => {
    return () => {
      blobUrlsRef.current.forEach(url => {
        documentService.revokeImageUrl(url);
      });
      blobUrlsRef.current.clear();
    };
  }, []);

  const handleClick = (doc: Document, e: React.MouseEvent) => {
    if (multiSelectMode && onMultiSelect) {
      e.preventDefault();
      onMultiSelect(doc.uuid);
    } else {
      onSelect(doc);
    }
  };

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, index: number) => {
    if (multiSelectMode) return; // Disable drag in multi-select mode
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', index.toString());
    // Make the drag image slightly transparent
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '0.5';
    }
  };

  const handleDragEnd = (e: React.DragEvent) => {
    setDraggedIndex(null);
    setDragOverIndex(null);
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '1';
    }
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (draggedIndex !== null && index !== draggedIndex) {
      setDragOverIndex(index);
    }
  };

  const handleDragLeave = () => {
    setDragOverIndex(null);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    const dragIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
    
    if (!isNaN(dragIndex) && dragIndex !== dropIndex && onReorder) {
      onReorder(dragIndex, dropIndex);
    }
    
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  if (documents.length <= 1) return null;

  return (
    <div className="flex gap-2 overflow-x-auto py-2 px-1">
      {documents.map((doc, index) => {
        const isSelected = selectedUuids.includes(doc.uuid);
        const isCurrent = doc.uuid === currentUuid;
        const thumbUrl = thumbnails[doc.uuid];
        const isLoading = loading[doc.uuid];
        const isDragging = draggedIndex === index;
        const isDragOver = dragOverIndex === index;

        return (
          <div
            key={doc.uuid}
            draggable={!multiSelectMode && !!onReorder}
            onDragStart={(e) => handleDragStart(e, index)}
            onDragEnd={handleDragEnd}
            onDragOver={(e) => handleDragOver(e, index)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, index)}
            className={cn(
              'relative flex-shrink-0',
              isDragOver && 'border-l-2 border-primary pl-1',
              isDragging && 'opacity-50'
            )}
          >
            <button
              onClick={(e) => handleClick(doc, e)}
              className={cn(
                'relative w-16 h-20 rounded-md overflow-hidden border-2 transition-all',
                isCurrent && !multiSelectMode
                  ? 'border-primary ring-2 ring-primary/30'
                  : 'border-muted hover:border-muted-foreground/50',
                isSelected && multiSelectMode && 'border-primary ring-2 ring-primary/30',
                'focus:outline-none focus:ring-2 focus:ring-primary/50'
              )}
            >
              {isLoading || !thumbUrl ? (
                <Skeleton className="w-full h-full" />
              ) : (
                <img
                  src={thumbUrl}
                  alt={`${t('common.page')} ${index + 1}`}
                  className="w-full h-full object-cover"
                  draggable={false}
                />
              )}
              
              {/* Drag handle indicator (only when reorder enabled) */}
              {onReorder && !multiSelectMode && (
                <div className="absolute top-0.5 left-0.5 opacity-50 hover:opacity-100">
                  <GripVertical className="w-3 h-3 text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)]" />
                </div>
              )}
              
              {/* Page number badge */}
              <span className="absolute bottom-0.5 right-0.5 text-[10px] bg-black/60 text-white px-1 rounded">
                {index + 1}
              </span>

              {/* Multi-select checkbox */}
              {multiSelectMode && isSelected && (
                <div className="absolute top-0.5 left-0.5 bg-primary rounded-full">
                  <CheckCircle2 className="w-4 h-4 text-white" />
                </div>
              )}

              {/* Status indicator for non-completed */}
              {doc.status !== 'completed' && (
                <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                  <span className="text-[8px] text-white font-medium">{t('common.pending')}</span>
                </div>
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
