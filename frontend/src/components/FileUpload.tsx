import { useCallback, useEffect, useRef, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Camera, X, Plus, Check, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';

interface FileUploadProps {
  onFilesSelected: (files: File[]) => void;
  multiple?: boolean;
  disabled?: boolean;
  isUploading?: boolean;
  uploadProgress?: number;
  className?: string;
}

const ACCEPTED_TYPES = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
  'image/tiff': ['.tiff', '.tif'],
  'image/bmp': ['.bmp'],
};

export function FileUpload({ 
  onFilesSelected, 
  multiple = true, 
  disabled = false,
  isUploading = false,
  uploadProgress = 0,
  className 
}: FileUploadProps) {
  const { t } = useTranslation();
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const previewsRef = useRef<string[]>([]);
  const [capturedFiles, setCapturedFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    previewsRef.current = previews;
  }, [previews]);

  useEffect(() => {
    return () => {
      previewsRef.current.forEach((url) => URL.revokeObjectURL(url));
      previewsRef.current = [];
    };
  }, []);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;

    if (multiple) {
      const newPreviews = acceptedFiles.map((file) => URL.createObjectURL(file));
      setCapturedFiles((prev) => [...prev, ...acceptedFiles]);
      setPreviews((prev) => [...prev, ...newPreviews]);
    } else {
      onFilesSelected(acceptedFiles);
    }
  }, [multiple, onFilesSelected]);

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    multiple,
    disabled: disabled || isUploading,
    maxSize: 20 * 1024 * 1024, // 20MB
  });

  const handleCameraCapture = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) {
      if (cameraInputRef.current) {
        cameraInputRef.current.value = '';
      }
      return;
    }

    const fileArray = Array.from(files);
    if (multiple) {
      const newPreviews = fileArray.map((file) => URL.createObjectURL(file));
      setCapturedFiles((prev) => [...prev, ...fileArray]);
      setPreviews((prev) => [...prev, ...newPreviews]);
    } else {
      onFilesSelected(fileArray);
    }

    if (cameraInputRef.current) {
      cameraInputRef.current.value = '';
    }
  }, [multiple, onFilesSelected]);

  const openCamera = useCallback(() => {
    cameraInputRef.current?.click();
  }, []);

  const removeFile = useCallback((index: number) => {
    setCapturedFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => {
      const url = prev[index];
      if (url) {
        URL.revokeObjectURL(url);
      }
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const submitFiles = useCallback(() => {
    if (capturedFiles.length === 0) return;

    onFilesSelected(capturedFiles);
    setCapturedFiles([]);
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return [];
    });
  }, [capturedFiles, onFilesSelected]);

  const clearAll = useCallback(() => {
    setCapturedFiles([]);
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return [];
    });
  }, []);

  // Show preview grid if we have captured files
  if (capturedFiles.length > 0 && multiple) {
    return (
      <div className={cn('space-y-4', className)}>
        {/* Preview Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {previews.map((preview, index) => (
            <div key={index} className="relative aspect-[3/4] group">
              <img
                src={preview}
                alt={`Capture ${index + 1}`}
                className="w-full h-full object-cover rounded-lg border"
              />
              <button
                type="button"
                onClick={() => removeFile(index)}
                className="absolute top-1 right-1 p-1 bg-destructive text-destructive-foreground rounded-full opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"
              >
                <X className="w-4 h-4" />
              </button>
              <div className="absolute bottom-1 left-1 px-2 py-0.5 bg-black/50 text-white text-xs rounded">
                {index + 1}
              </div>
            </div>
          ))}
          
          {/* Add More Button */}
          <div
            {...getRootProps()}
            className={cn(
              'aspect-[3/4] flex flex-col items-center justify-center',
              'border-2 border-dashed rounded-lg cursor-pointer transition-colors',
              'hover:border-primary/50 hover:bg-primary/5',
              isDragActive && 'border-primary bg-primary/10'
            )}
          >
            <input {...getInputProps()} />
            <Plus className="w-8 h-8 text-muted-foreground mb-2" />
            <span className="text-xs text-muted-foreground text-center px-2">
              {t('scan.addMore')}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-2">
          {/* Camera Button for Mobile */}
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleCameraCapture}
            className="hidden"
          />
          <Button
            type="button"
            variant="outline"
            onClick={openCamera}
            className="flex-1 sm:flex-none"
          >
            <Camera className="w-4 h-4 mr-2" />
            {t('scan.takePhoto')}
          </Button>

          <div className="flex-1" />

          <Button
            type="button"
            variant="ghost"
            onClick={clearAll}
          >
            {t('common.cancel')}
          </Button>
          
          <Button
            type="button"
            onClick={submitFiles}
          >
            <Check className="w-4 h-4 mr-2" />
            {t('scan.usePhotos', { count: capturedFiles.length })}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Hidden camera input */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleCameraCapture}
        className="hidden"
      />

      {/* Main Upload Area */}
      <div
        {...getRootProps()}
        className={cn(
          'relative flex flex-col items-center justify-center w-full min-h-[250px] p-6',
          'border-2 border-dashed rounded-lg cursor-pointer transition-colors',
          'hover:border-primary/50 hover:bg-primary/5',
          isDragActive && 'border-primary bg-primary/10',
          isDragReject && 'border-destructive bg-destructive/10',
          (disabled || isUploading) && 'opacity-50 cursor-not-allowed'
        )}
      >
        <input {...getInputProps()} />
        
        {isUploading ? (
          <div className="flex flex-col items-center text-center space-y-4 w-full max-w-xs">
            <Loader2 className="w-12 h-12 text-primary animate-spin" />
            <div className="space-y-2 w-full">
              <h3 className="text-base font-semibold">{t('scan.uploading')}</h3>
              <Progress value={uploadProgress} className="w-full" />
              <p className="text-sm text-muted-foreground">{uploadProgress}%</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center text-center space-y-3">
            <Upload className="w-12 h-12 text-muted-foreground" />
            
            <div className="space-y-1">
              <h3 className="text-base font-semibold">
                {isDragActive 
                  ? t('scan.uploadSubtitle') 
                  : t('scan.uploadTitle')
                }
              </h3>
              <p className="text-sm text-muted-foreground">
                {t('scan.uploadSubtitle')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t('scan.uploadHint')}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Camera Button - More prominent on mobile */}
      <div className="flex justify-center">
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={openCamera}
          disabled={disabled || isUploading}
          className="w-full sm:w-auto"
        >
          <Camera className="w-5 h-5 mr-2" />
          {t('scan.takePhoto')}
        </Button>
      </div>

      {/* Hint for mobile */}
      <p className="text-xs text-muted-foreground text-center sm:hidden">
        {t('scan.cameraHint')}
      </p>
    </div>
  );
}
