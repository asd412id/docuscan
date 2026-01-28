import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileImage } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

interface FileUploadProps {
  onFilesSelected: (files: File[]) => void;
  multiple?: boolean;
  disabled?: boolean;
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
  className 
}: FileUploadProps) {
  const { t } = useTranslation();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      onFilesSelected(acceptedFiles);
    }
  }, [onFilesSelected]);

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    multiple,
    disabled,
    maxSize: 20 * 1024 * 1024, // 20MB
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        'relative flex flex-col items-center justify-center w-full min-h-[300px] p-8',
        'border-2 border-dashed rounded-lg cursor-pointer transition-colors',
        'hover:border-primary/50 hover:bg-primary/5',
        isDragActive && 'border-primary bg-primary/10',
        isDragReject && 'border-destructive bg-destructive/10',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      <input {...getInputProps()} />
      
      <div className="flex flex-col items-center text-center space-y-4">
        {isDragActive ? (
          <FileImage className="w-16 h-16 text-primary animate-pulse" />
        ) : (
          <Upload className="w-16 h-16 text-muted-foreground" />
        )}
        
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">
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
    </div>
  );
}
