import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { useScanStore } from '@/store/scanStore';
import { documentService, scanService } from '@/services/documents';
import { useBulkBackgroundProcess } from '@/hooks/useBackgroundTask';
import { FileUpload } from '@/components/FileUpload';
import { CornerAdjust } from '@/components/CornerAdjust';
import { FilterControls } from '@/components/FilterControls';
import { ThumbnailGrid } from '@/components/ThumbnailGrid';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  Loader2, 
  ScanLine, 
  Download, 
  FileText, 
  Trash2,
  ChevronLeft,
  ChevronRight,
  Settings2,
  RefreshCw,
  CheckSquare,
  Square,
  Copy,
  X
} from 'lucide-react';
import type { CornerPoints, Document, PdfPageSize } from '@/types';

type Step = 'upload' | 'adjust' | 'process' | 'result';

export function ScanPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const {
    documents,
    currentDocument,
    corners,
    settings,
    isProcessing,
    addDocument,
    addDocuments,
    setDocuments,
    setCurrentDocument,
    removeDocument,
    reorderDocuments,
    setCorners,
    setSettings,
    setIsProcessing,
    updateDocument,
    getDocumentSettings,
  } = useScanStore();

  const [step, setStep] = useState<Step>('upload');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [ocrText, setOcrText] = useState('');
  const [isOcrLoading, setIsOcrLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [imageUrls, setImageUrls] = useState<{ original?: string; processed?: string }>({});
  const [isLoadingImage, setIsLoadingImage] = useState(false);
  const [processProgress, setProcessProgress] = useState({ current: 0, total: 0 });
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedUuids, setSelectedUuids] = useState<string[]>([]);
  
  // Export settings
  const [exportQuality, setExportQuality] = useState(90);
  const [exportPageSize, setExportPageSize] = useState<PdfPageSize>('auto');
  const [exportSearchable, setExportSearchable] = useState(false);
  
  // Delete confirmation dialogs
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [batchDeleteDialogOpen, setBatchDeleteDialogOpen] = useState(false);
  
  // Background processing hook for bulk operations
  const backgroundProcess = useBulkBackgroundProcess();
  
  // Track blob URLs for cleanup to prevent memory leaks
  const blobUrlsRef = useRef<Set<string>>(new Set());
  
  // Helper to revoke and remove a blob URL
  const revokeBlobUrl = useCallback((url: string | undefined) => {
    if (url && url.startsWith('blob:')) {
      documentService.revokeImageUrl(url);
      blobUrlsRef.current.delete(url);
    }
  }, []);
  
  // Helper to track a new blob URL
  const trackBlobUrl = useCallback((url: string) => {
    if (url.startsWith('blob:')) {
      blobUrlsRef.current.add(url);
    }
    return url;
  }, []);
  
  // Cleanup all tracked blob URLs on unmount
  useEffect(() => {
    return () => {
      blobUrlsRef.current.forEach(url => {
        documentService.revokeImageUrl(url);
      });
      blobUrlsRef.current.clear();
    };
  }, []);

  // Handle view document from history page
  useEffect(() => {
    const viewDoc = (location.state as { viewDocument?: Document })?.viewDocument;
    if (viewDoc) {
      // Add to documents if not already there
      if (!documents.find(d => d.uuid === viewDoc.uuid)) {
        addDocument(viewDoc);
      }
      setCurrentDocument(viewDoc);
      // Set appropriate step based on document status
      if (viewDoc.status === 'completed') {
        setStep('result');
      } else {
        setStep('adjust');
      }
      // Clear location state to prevent re-triggering
      window.history.replaceState({}, document.title);
    }
  }, [location.state, documents, addDocument, setCurrentDocument]);

  // Load image URLs when currentDocument changes
  useEffect(() => {
    if (!currentDocument) {
      // Revoke any existing URLs when no document
      revokeBlobUrl(imageUrls.original);
      revokeBlobUrl(imageUrls.processed);
      setImageUrls({});
      return;
    }

    const docUuid = currentDocument.uuid;
    const docStatus = currentDocument.status;
    
    let cancelled = false;

    const loadImages = async () => {
      setIsLoadingImage(true);
      
      // Revoke old URLs before loading new ones
      const oldOriginal = imageUrls.original;
      const oldProcessed = imageUrls.processed;
      
      try {
        const original = await documentService.getImageUrl(docUuid, 'original');
        if (!cancelled) {
          revokeBlobUrl(oldOriginal);
          trackBlobUrl(original);
          setImageUrls(prev => ({ ...prev, original }));
        } else {
          // If cancelled, revoke the newly fetched URL
          documentService.revokeImageUrl(original);
        }

        if (docStatus === 'completed') {
          const processed = await documentService.getImageUrl(docUuid, 'processed');
          if (!cancelled) {
            revokeBlobUrl(oldProcessed);
            trackBlobUrl(processed);
            setImageUrls(prev => ({ ...prev, processed }));
          } else {
            documentService.revokeImageUrl(processed);
          }
        }
      } catch (error) {
        console.error('Failed to load images:', error);
      } finally {
        if (!cancelled) {
          setIsLoadingImage(false);
        }
      }
    };

    loadImages();

    return () => {
      cancelled = true;
    };
  }, [currentDocument?.uuid, currentDocument?.status]);

  // Auto-detect edges when entering adjust step without corners
  useEffect(() => {
    if (step === 'adjust' && currentDocument && !corners && !isProcessing) {
      const detectEdges = async () => {
        setIsProcessing(true);
        try {
          const detection = await scanService.detectEdges(currentDocument.uuid);
          setCorners(detection.corners);
        } catch (error) {
          console.error('Failed to auto-detect edges:', error);
        } finally {
          setIsProcessing(false);
        }
      };
      detectEdges();
    }
  }, [step, currentDocument, corners, isProcessing, setCorners, setIsProcessing]);

  // Load processed image after processing
  const loadProcessedImage = async (docUuid: string) => {
    try {
      const processed = await documentService.getImageUrl(docUuid, 'processed');
      setImageUrls(prev => {
        // Revoke old processed URL before setting new one
        revokeBlobUrl(prev.processed);
        trackBlobUrl(processed);
        return { ...prev, processed };
      });
    } catch (error) {
      console.error('Failed to load processed image:', error);
    }
  };

  const handleFilesSelected = useCallback(async (files: File[]) => {
    setIsProcessing(true);
    setUploadProgress(0);
    
    try {
      const uploaded = await documentService.uploadBatch(files);
      
      // If uploading from upload step (fresh start), replace all documents
      // Otherwise (addMore from result step), append to existing
      if (step === 'upload') {
        setDocuments(uploaded);
      } else {
        addDocuments(uploaded);
      }
      
      if (uploaded.length > 0) {
        setCurrentDocument(uploaded[0]);
        setUploadProgress(50);
        
        const detection = await scanService.detectEdges(uploaded[0].uuid);
        setCorners(detection.corners);
        setUploadProgress(100);
        setStep('adjust');
      }
      
      toast.success(t('common.success'), {
        description: t('scan.filesUploaded', { count: uploaded.length }),
      });
    } catch (error) {
      toast.error(t('errors.uploadFailed'));
      console.error(error);
    } finally {
      setIsProcessing(false);
      setUploadProgress(0);
    }
  }, [step, setDocuments, addDocuments, setCurrentDocument, setCorners, setIsProcessing, t]);

  const handleDetect = async () => {
    if (!currentDocument) return;
    
    setIsProcessing(true);
    try {
      const detection = await scanService.detectEdges(currentDocument.uuid);
      setCorners(detection.corners);
      toast.success(t('common.success'), {
        description: t('scan.edgesDetected', { confidence: Math.round(detection.confidence * 100) }),
      });
    } catch {
      toast.error(t('errors.detectFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleProcess = async () => {
    if (!currentDocument) return;
    
    setIsProcessing(true);
    try {
      const result = await scanService.process(
        currentDocument.uuid,
        corners || undefined,
        settings
      );
      
      updateDocument(currentDocument.uuid, {
        status: 'completed',
        processed_url: result.processed_url,
        thumbnail_url: result.thumbnail_url,
      });
      
      // Load the processed image
      await loadProcessedImage(currentDocument.uuid);
      
      // If there are more documents, go to next one, otherwise go to result
      const currentIdx = documents.findIndex(d => d.uuid === currentDocument.uuid);
      const nextUnprocessed = documents.find((d, idx) => idx > currentIdx && d.status !== 'completed');
      
      if (nextUnprocessed) {
        setCurrentDocument(nextUnprocessed);
        toast.success(t('common.success'), {
          description: t('scan.documentProcessed', { current: currentIdx + 1, total: documents.length }),
        });
      } else {
        setStep('result');
        toast.success(t('common.success'), {
          description: t('scan.documentExported'),
        });
      }
    } catch {
      toast.error(t('errors.processFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleProcessAll = async () => {
    if (documents.length === 0) return;
    
    // Use background processing for 3+ documents for better UX with progress tracking
    const useBackground = documents.length >= 3;
    
    setIsProcessing(true);
    setProcessProgress({ current: 0, total: documents.length });
    
    try {
      // Build bulk process request with per-document settings
      const bulkDocs = documents.map(doc => {
        const docSettings = getDocumentSettings(doc.uuid);
        return {
          document_uuid: doc.uuid,
          corners: docSettings.corners,
          settings: docSettings.settings,
        };
      });
      
      if (useBackground) {
        // Use background task processing with progress tracking
        await backgroundProcess.startBulkProcess(bulkDocs, settings);
        // The hook will handle progress updates
        // We'll show a toast and wait for completion
        toast.info(t('scan.backgroundProcessing'), {
          description: `${documents.length} ${t('documents.count', { count: documents.length })}`,
        });
        return; // The useEffect below will handle completion
      }
      
      // Direct processing for smaller batches
      const results = await scanService.bulkProcess(bulkDocs, settings);
      
      // Update all documents
      results.forEach((result, idx) => {
        updateDocument(result.document_uuid, {
          status: 'completed',
          processed_url: result.processed_url,
          thumbnail_url: result.thumbnail_url,
        });
        setProcessProgress({ current: idx + 1, total: documents.length });
      });
      
      // Load first document's processed image and go to result
      if (results.length > 0) {
        await loadProcessedImage(documents[0].uuid);
        setCurrentDocument(documents[0]);
      }
      
      setStep('result');
      toast.success(t('common.success'), {
        description: t('scan.documentsProcessed', { count: results.length }),
      });
    } catch {
      toast.error(t('errors.processFailed'));
    } finally {
      if (!useBackground) {
        setIsProcessing(false);
        setProcessProgress({ current: 0, total: 0 });
      }
    }
  };

  // Handle background processing completion
  useEffect(() => {
    if (backgroundProcess.status?.status === 'completed' && backgroundProcess.status.result) {
      const applyAndFinish = async () => {
        try {
          // Apply results to database
          const applied = await backgroundProcess.applyResults();
          
          // Update local document states
          const results = backgroundProcess.status?.result?.results as Array<{
            document_uuid: string;
            status: string;
            processed_path?: string;
            thumbnail_path?: string;
          }> | undefined;
          
          if (results) {
            results.forEach(result => {
              if (result.status === 'completed') {
                updateDocument(result.document_uuid, {
                  status: 'completed',
                });
              }
            });
          }
          
          // Load first document's processed image and go to result
          if (documents.length > 0) {
            await loadProcessedImage(documents[0].uuid);
            setCurrentDocument(documents[0]);
          }
          
          setStep('result');
          toast.success(t('common.success'), {
            description: t('scan.documentsProcessed', { count: applied.documents_updated }),
          });
        } catch {
          toast.error(t('errors.processFailed'));
        } finally {
          setIsProcessing(false);
          setProcessProgress({ current: 0, total: 0 });
          backgroundProcess.reset();
        }
      };
      
      applyAndFinish();
    } else if (backgroundProcess.status?.status === 'failed') {
      toast.error(t('scan.backgroundFailed'), {
        description: backgroundProcess.status.message,
      });
      setIsProcessing(false);
      setProcessProgress({ current: 0, total: 0 });
      backgroundProcess.reset();
    }
  }, [backgroundProcess.status?.status]);

  // Sync background progress with local progress state
  useEffect(() => {
    if (backgroundProcess.isProcessing && backgroundProcess.progress.total > 0) {
      setProcessProgress({
        current: backgroundProcess.progress.current,
        total: backgroundProcess.progress.total,
      });
    }
  }, [backgroundProcess.progress, backgroundProcess.isProcessing]);

  const handleCancelBackgroundProcess = useCallback(async () => {
    await backgroundProcess.cancelProcess();
    setIsProcessing(false);
    setProcessProgress({ current: 0, total: 0 });
    toast.info(t('common.cancel'));
  }, [backgroundProcess, t]);

  const handleOCR = async () => {
    if (!currentDocument) return;
    
    setIsOcrLoading(true);
    try {
      const result = await scanService.ocr(currentDocument.uuid);
      setOcrText(result.text);
      toast.success(t('common.success'), {
        description: t('scan.textExtracted', { confidence: Math.round(result.confidence * 100) }),
      });
    } catch {
      toast.error(t('errors.ocrFailed'));
    } finally {
      setIsOcrLoading(false);
    }
  };

  const handleExport = async (format: 'pdf' | 'png' | 'jpg', all = false) => {
    const docsToExport = all 
      ? documents.filter(d => d.status === 'completed')
      : currentDocument ? [currentDocument] : [];
    
    if (docsToExport.length === 0) return;
    
    setIsProcessing(true);
    try {
      const uuids = docsToExport.map(d => d.uuid);
      // Only pass searchable option for PDF format
      const searchable = format === 'pdf' ? exportSearchable : false;
      const result = await scanService.export(uuids, format, exportQuality, true, exportPageSize, searchable);
      
      // Use authenticated download to avoid 401 errors
      await documentService.downloadFile(result.download_url, result.filename);
      
      toast.success(t('common.success'), {
        description: all 
          ? t('scan.documentsExported', { count: docsToExport.length })
          : t('scan.documentExported'),
      });
    } catch {
      toast.error(t('errors.exportFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExportZip = async () => {
    const docsToExport = documents.filter(d => d.status === 'completed');
    if (docsToExport.length === 0) return;
    
    setIsProcessing(true);
    try {
      const uuids = docsToExport.map(d => d.uuid);
      const result = await scanService.export(uuids, 'zip', exportQuality);
      
      await documentService.downloadFile(result.download_url, result.filename);
      
      toast.success(t('common.success'), {
        description: t('scan.exportedAsZip', { count: docsToExport.length }),
      });
    } catch {
      toast.error(t('errors.exportFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDelete = async () => {
    if (!currentDocument) return;
    
    try {
      await documentService.delete(currentDocument.uuid);
      
      const remaining = documents.filter(d => d.uuid !== currentDocument.uuid);
      
      // Remove from store AFTER we calculate remaining
      removeDocument(currentDocument.uuid);
      
      // Revoke current blob URLs
      revokeBlobUrl(imageUrls.original);
      revokeBlobUrl(imageUrls.processed);
      
      if (remaining.length > 0) {
        // Find current position and try to stay at same index or go to previous
        const deletedIndex = documents.findIndex(d => d.uuid === currentDocument.uuid);
        const newIndex = Math.min(deletedIndex, remaining.length - 1);
        const nextDoc = remaining[newIndex];
        
        setCurrentDocument(nextDoc);
        
        // Load processed image for the new current document
        if (nextDoc.status === 'completed') {
          setIsLoadingImage(true);
          try {
            const processed = await documentService.getImageUrl(nextDoc.uuid, 'processed');
            trackBlobUrl(processed);
            setImageUrls({ processed });
          } catch {
            // Ignore error
          } finally {
            setIsLoadingImage(false);
          }
        } else {
          setImageUrls({});
        }
      } else {
        // No documents left - reset everything
        setCurrentDocument(null);
        setImageUrls({});
        setOcrText('');
        setStep('upload');
      }
      
      toast.success(t('common.success'), {
        description: t('scan.documentDeleted'),
      });
    } catch {
      toast.error(t('common.error'));
    } finally {
      setDeleteDialogOpen(false);
    }
  };

  const handleCancel = async () => {
    if (!currentDocument) return;
    
    try {
      await documentService.delete(currentDocument.uuid);
      removeDocument(currentDocument.uuid);
      
      // Revoke current blob URLs
      revokeBlobUrl(imageUrls.original);
      revokeBlobUrl(imageUrls.processed);
      
      if (documents.length > 1) {
        const remaining = documents.filter(d => d.uuid !== currentDocument.uuid);
        setCurrentDocument(remaining[0] || null);
        // New document's images will be loaded by the useEffect
      } else {
        setCurrentDocument(null);
        setImageUrls({});
        setStep('upload');
      }
    } catch {
      toast.error(t('common.error'));
    } finally {
      setCancelDialogOpen(false);
    }
  };

  const handleReplace = () => {
    setStep('upload');
  };

  const currentIndex = documents.findIndex(d => d.uuid === currentDocument?.uuid);

  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentDocument(documents[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (currentIndex < documents.length - 1) {
      setCurrentDocument(documents[currentIndex + 1]);
    }
  };

  const handleToggleMultiSelect = () => {
    if (multiSelectMode) {
      // Exiting multi-select mode
      setSelectedUuids([]);
    }
    setMultiSelectMode(!multiSelectMode);
  };

  const handleMultiSelect = (uuid: string) => {
    setSelectedUuids(prev => 
      prev.includes(uuid) 
        ? prev.filter(id => id !== uuid)
        : [...prev, uuid]
    );
  };

  const handleSelectAll = () => {
    if (selectedUuids.length === documents.length) {
      setSelectedUuids([]);
    } else {
      setSelectedUuids(documents.map(d => d.uuid));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedUuids.length === 0) return;
    
    setIsProcessing(true);
    try {
      await documentService.batchDelete(selectedUuids);
      
      // Remove all selected documents from store
      const remaining = documents.filter(d => !selectedUuids.includes(d.uuid));
      
      selectedUuids.forEach(uuid => removeDocument(uuid));
      
      // Exit multi-select mode
      setMultiSelectMode(false);
      setSelectedUuids([]);
      
      // Revoke current blob URLs if current document was deleted
      if (currentDocument && selectedUuids.includes(currentDocument.uuid)) {
        revokeBlobUrl(imageUrls.original);
        revokeBlobUrl(imageUrls.processed);
      }
      
      if (remaining.length > 0) {
        // Select first remaining document
        setCurrentDocument(remaining[0]);
        if (remaining[0].status === 'completed') {
          setIsLoadingImage(true);
          try {
            const processed = await documentService.getImageUrl(remaining[0].uuid, 'processed');
            trackBlobUrl(processed);
            setImageUrls({ processed });
          } catch {
            // Ignore error
          } finally {
            setIsLoadingImage(false);
          }
        } else {
          setImageUrls({});
        }
      } else {
        // No documents left
        setCurrentDocument(null);
        setImageUrls({});
        setOcrText('');
        setStep('upload');
      }
      
      toast.success(t('common.success'), {
        description: t('scan.documentsDeleted', { count: selectedUuids.length }),
      });
    } catch {
      toast.error(t('common.error'));
    } finally {
      setIsProcessing(false);
      setBatchDeleteDialogOpen(false);
    }
  };

  return (
    <div className="container mx-auto p-4 max-w-6xl">
      <div className="flex items-center gap-3 mb-6">
        <ScanLine className="w-6 h-6 sm:w-8 sm:h-8 text-primary" />
        <h1 className="text-xl sm:text-2xl font-bold">{t('scan.title')}</h1>
      </div>

      {step === 'upload' && (
        <Card>
          <CardContent className="pt-6">
            <FileUpload 
              onFilesSelected={handleFilesSelected}
              disabled={isProcessing}
              isUploading={isProcessing}
              uploadProgress={uploadProgress}
            />
            {uploadProgress > 0 && (
              <div className="mt-4">
                <Progress value={uploadProgress} />
                <p className="text-sm text-muted-foreground mt-2 text-center">
                  {isProcessing ? t('scan.detecting') : t('common.loading')}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {step === 'adjust' && currentDocument && (
        <div className="space-y-4 lg:space-y-0 lg:grid lg:grid-cols-3 lg:gap-6">
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between p-4 sm:p-6">
                <CardTitle className="text-base sm:text-lg">{t('scan.adjust')}</CardTitle>
                <div className="flex items-center gap-2">
                  {documents.length > 1 && (
                    <>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        onClick={handlePrevious}
                        disabled={currentIndex === 0}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-xs sm:text-sm text-muted-foreground">
                        {currentIndex + 1} / {documents.length}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        onClick={handleNext}
                        disabled={currentIndex === documents.length - 1}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8 lg:hidden"
                    onClick={() => setShowFilters(!showFilters)}
                  >
                    <Settings2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex justify-center p-2 sm:p-6">
                {isLoadingImage || !imageUrls.original || !corners ? (
                  <Skeleton className="w-full max-w-lg h-[50vh] rounded-lg" />
                ) : (
                  <CornerAdjust
                    imageSrc={imageUrls.original}
                    corners={corners}
                    onCornersChange={(newCorners: CornerPoints) => setCorners(newCorners)}
                    disabled={isProcessing}
                    settings={settings}
                  />
                )}
              </CardContent>
            </Card>
          </div>
          
          <div className={`space-y-4 ${showFilters ? 'block' : 'hidden lg:block'}`}>
            <FilterControls
              settings={settings}
              onSettingsChange={setSettings}
              disabled={isProcessing}
            />
            
            <div className="flex flex-col gap-2">
              <Button onClick={handleDetect} variant="outline" disabled={isProcessing}>
                {isProcessing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ScanLine className="mr-2 h-4 w-4" />
                )}
                {t('scan.detect')}
              </Button>
              
              <Button onClick={handleProcess} disabled={isProcessing}>
                {isProcessing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {isProcessing ? t('scan.processing') : t('scan.process')}
              </Button>
              
              {documents.length > 1 && (
                <div className="flex gap-2">
                  <Button 
                    onClick={handleProcessAll} 
                    disabled={isProcessing} 
                    variant="secondary"
                    className="flex-1"
                  >
                    {isProcessing && processProgress.total > 0 ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        {processProgress.current}/{processProgress.total}
                        {backgroundProcess.isProcessing && (
                          <span className="ml-1 text-xs">({backgroundProcess.progress.percentage}%)</span>
                        )}
                      </>
                    ) : (
                      `${t('scan.processAll')} (${documents.length})`
                    )}
                  </Button>
                  {backgroundProcess.isProcessing && (
                    <Button 
                      onClick={handleCancelBackgroundProcess} 
                      variant="destructive"
                      size="icon"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              )}
              
              <div className="flex gap-2 pt-2 border-t">
                <Button 
                  variant="outline" 
                  className="flex-1"
                  onClick={handleReplace}
                  disabled={isProcessing}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {t('scan.replace')}
                </Button>
                <Button 
                  variant="destructive" 
                  size="icon"
                  onClick={() => setCancelDialogOpen(true)}
                  disabled={isProcessing}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
          
          <div className="lg:hidden flex flex-col gap-2">
            {!showFilters && (
              <>
                <div className="flex gap-2">
                  <Button onClick={handleDetect} variant="outline" disabled={isProcessing} className="flex-1">
                    {isProcessing ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <ScanLine className="mr-2 h-4 w-4" />
                    )}
                    {t('scan.detect')}
                  </Button>
                  <Button onClick={handleProcess} disabled={isProcessing} className="flex-1">
                    {isProcessing ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {isProcessing ? t('scan.processing') : t('scan.process')}
                  </Button>
                </div>
                {documents.length > 1 && (
                  <div className="flex gap-2">
                    <Button 
                      onClick={handleProcessAll} 
                      disabled={isProcessing} 
                      variant="secondary"
                      className="flex-1"
                    >
                      {isProcessing && processProgress.total > 0 ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {processProgress.current}/{processProgress.total}
                          {backgroundProcess.isProcessing && (
                            <span className="ml-1 text-xs">({backgroundProcess.progress.percentage}%)</span>
                          )}
                        </>
                      ) : (
                        `${t('scan.processAll')} (${documents.length})`
                      )}
                    </Button>
                    {backgroundProcess.isProcessing && (
                      <Button 
                        onClick={handleCancelBackgroundProcess} 
                        variant="destructive"
                        size="icon"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                )}
                <div className="flex gap-2">
                  <Button 
                    variant="outline" 
                    className="flex-1"
                    onClick={handleReplace}
                    disabled={isProcessing}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    {t('scan.replace')}
                  </Button>
                  <Button 
                    variant="destructive" 
                    size="icon"
                    onClick={() => setCancelDialogOpen(true)}
                    disabled={isProcessing}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {step === 'result' && currentDocument && (
        <div className="space-y-4 lg:space-y-0 lg:grid lg:grid-cols-3 lg:gap-6">
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between p-4 sm:p-6">
                <CardTitle className="text-base sm:text-lg">{t('scan.preview')}</CardTitle>
                {documents.length > 1 && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={handlePrevious}
                      disabled={currentIndex === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="text-xs sm:text-sm text-muted-foreground">
                      {currentIndex + 1} / {documents.length}
                    </span>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={handleNext}
                      disabled={currentIndex === documents.length - 1}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent className="flex flex-col items-center p-2 sm:p-6">
                {isLoadingImage || !imageUrls.processed ? (
                  <Skeleton className="w-full max-w-lg h-[50vh] rounded-lg" />
                ) : (
                  <img
                    src={imageUrls.processed}
                    alt="Processed document"
                    className="max-w-full max-h-[50vh] sm:max-h-[60vh] object-contain rounded-lg shadow-lg"
                  />
                )}
                
                {/* Thumbnail navigation */}
                {documents.length > 1 && (
                  <div className="w-full mt-4 border-t pt-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-muted-foreground">
                        {multiSelectMode 
                          ? `${selectedUuids.length} ${t('common.selected')}`
                          : t('documents.count', { count: documents.length })
                        }
                      </span>
                      <div className="flex items-center gap-1">
                        {multiSelectMode && (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={handleSelectAll}
                            >
                              {selectedUuids.length === documents.length ? t('common.deselectAll') : t('common.selectAll')}
                            </Button>
                            {selectedUuids.length > 0 && (
                              <Button
                                variant="destructive"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={() => setBatchDeleteDialogOpen(true)}
                                disabled={isProcessing}
                              >
                                <Trash2 className="h-3 w-3 mr-1" />
                                {t('common.delete')} ({selectedUuids.length})
                              </Button>
                            )}
                          </>
                        )}
                        <Button
                          variant={multiSelectMode ? "default" : "outline"}
                          size="sm"
                          className="h-7 text-xs"
                          onClick={handleToggleMultiSelect}
                        >
                          {multiSelectMode ? (
                            <CheckSquare className="h-3 w-3 mr-1" />
                          ) : (
                            <Square className="h-3 w-3 mr-1" />
                          )}
                          {multiSelectMode ? t('common.done') : t('scan.select')}
                        </Button>
                      </div>
                    </div>
                    <ThumbnailGrid
                      documents={documents}
                      currentUuid={currentDocument?.uuid}
                      selectedUuids={selectedUuids}
                      onSelect={setCurrentDocument}
                      onMultiSelect={handleMultiSelect}
                      onReorder={reorderDocuments}
                      multiSelectMode={multiSelectMode}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
          
          <div className="space-y-4">
            <Card>
              <CardHeader className="p-4 sm:p-6">
                <CardTitle className="text-base sm:text-lg">{t('scan.export')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 p-4 sm:p-6 pt-0 sm:pt-0">
                {/* Export Settings */}
                <div className="space-y-3 pb-3 border-b">
                  <div className="space-y-2">
                    <Label className="text-xs">{t('scan.pageSize')}</Label>
                    <Select value={exportPageSize} onValueChange={(v) => setExportPageSize(v as PdfPageSize)}>
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">{t('scan.pageSizeAuto')}</SelectItem>
                        <SelectItem value="a4">{t('scan.pageSizeA4')}</SelectItem>
                        <SelectItem value="letter">{t('scan.pageSizeLetter')}</SelectItem>
                        <SelectItem value="legal">{t('scan.pageSizeLegal')}</SelectItem>
                        <SelectItem value="folio">{t('scan.pageSizeFolio')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <Label className="text-xs">{t('scan.quality')}</Label>
                      <span className="text-xs text-muted-foreground">{exportQuality}%</span>
                    </div>
                    <Slider
                      value={[exportQuality]}
                      onValueChange={([v]) => setExportQuality(v)}
                      min={10}
                      max={100}
                      step={5}
                      className="w-full"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label className="text-xs">{t('scan.searchablePdf')}</Label>
                      <p className="text-[10px] text-muted-foreground">{t('scan.searchablePdfHint')}</p>
                    </div>
                    <Switch
                      checked={exportSearchable}
                      onCheckedChange={setExportSearchable}
                    />
                  </div>
                </div>

                <Button 
                  className="w-full" 
                  onClick={() => handleExport('pdf')}
                  disabled={isProcessing}
                >
                  <Download className="mr-2 h-4 w-4" />
                  {t('scan.exportPDF')}
                </Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button 
                    variant="outline" 
                    onClick={() => handleExport('png')}
                    disabled={isProcessing}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    PNG
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={() => handleExport('jpg')}
                    disabled={isProcessing}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    JPG
                  </Button>
                </div>
                
                {documents.filter(d => d.status === 'completed').length > 1 && (
                  <>
                    <div className="border-t pt-2 mt-2">
                      <p className="text-xs text-muted-foreground mb-2">
                        {t('scan.exportAll')} ({documents.filter(d => d.status === 'completed').length})
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        <Button 
                          variant="secondary" 
                          onClick={() => handleExport('pdf', true)}
                          disabled={isProcessing}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          PDF
                        </Button>
                        <Button 
                          variant="secondary" 
                          onClick={handleExportZip}
                          disabled={isProcessing}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          ZIP
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="p-4 sm:p-6">
                <CardTitle className="text-base sm:text-lg">{t('scan.ocr')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 p-4 sm:p-6 pt-0 sm:pt-0">
                <Button 
                  className="w-full" 
                  variant="secondary"
                  onClick={handleOCR}
                  disabled={isOcrLoading}
                >
                  {isOcrLoading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileText className="mr-2 h-4 w-4" />
                  )}
                  {isOcrLoading ? t('scan.ocrProcessing') : t('scan.ocr')}
                </Button>
                
                {ocrText && (
                  <Tabs defaultValue="text">
                    <TabsList className="w-full">
                      <TabsTrigger value="text" className="flex-1">
                        {t('scan.ocrResult')}
                      </TabsTrigger>
                    </TabsList>
                    <TabsContent value="text">
                      <div className="relative">
                        <div className="bg-muted p-3 rounded-md max-h-48 overflow-y-auto">
                          <pre className="text-xs sm:text-sm whitespace-pre-wrap pr-8">{ocrText}</pre>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="absolute top-2 right-2 h-7 w-7"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(ocrText);
                              toast.success(t('common.success'), {
                                description: t('scan.ocrCopied'),
                              });
                            } catch {
                              toast.error(t('common.error'));
                            }
                          }}
                          title={t('scan.ocrCopy')}
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                      </div>
                    </TabsContent>
                  </Tabs>
                )}
              </CardContent>
            </Card>

            <div className="flex gap-2">
              <Button 
                variant="outline" 
                className="flex-1"
                onClick={async () => {
                  // Re-detect edges when going back to adjust step
                  if (currentDocument && !corners) {
                    setIsProcessing(true);
                    try {
                      const detection = await scanService.detectEdges(currentDocument.uuid);
                      setCorners(detection.corners);
                    } catch {
                      // Fallback to full image if detection fails
                    } finally {
                      setIsProcessing(false);
                    }
                  }
                  setStep('adjust');
                }}
              >
                {t('common.back')}
              </Button>
              <Button 
                variant="destructive" 
                size="icon"
                onClick={() => setDeleteDialogOpen(true)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            
            <Button 
              variant="outline" 
              className="w-full"
              onClick={() => {
                setStep('upload');
                setOcrText('');
              }}
            >
              {t('scan.addMore')}
            </Button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog - Single Document (Result Step) */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('common.confirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('documents.deleteConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleDelete} 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Cancel/Delete Confirmation Dialog - Adjust Step */}
      <AlertDialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('common.confirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('documents.deleteConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleCancel} 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Batch Delete Confirmation Dialog */}
      <AlertDialog open={batchDeleteDialogOpen} onOpenChange={setBatchDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('common.confirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('documents.batchDeleteConfirm', { count: selectedUuids.length })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleBatchDelete} 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
