import { useState, useCallback, useRef, useEffect } from 'react';
import { taskService, type TaskStatusResponse } from '@/services/documents';
import type { CornerPoints, ScanSettings } from '@/types';

interface UseBackgroundTaskOptions {
  pollInterval?: number;
  onProgress?: (status: TaskStatusResponse) => void;
  onComplete?: (status: TaskStatusResponse) => void;
  onError?: (error: Error) => void;
}

interface UseBackgroundTaskReturn {
  taskId: string | null;
  status: TaskStatusResponse | null;
  isRunning: boolean;
  progress: number;
  message: string;
  startTask: (taskId: string) => void;
  cancelTask: () => Promise<void>;
  applyResults: () => Promise<{ status: string; documents_updated: number }>;
  reset: () => void;
}

/**
 * Hook for managing background task polling and status updates
 */
export function useBackgroundTask(options: UseBackgroundTaskOptions = {}): UseBackgroundTaskReturn {
  const { 
    pollInterval = 1000, 
    onProgress, 
    onComplete, 
    onError 
  } = options;

  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<TaskStatusResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const callbacksRef = useRef({ onProgress, onComplete, onError });
  
  // Keep callbacks ref up to date
  useEffect(() => {
    callbacksRef.current = { onProgress, onComplete, onError };
  }, [onProgress, onComplete, onError]);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollRef.current) {
        clearTimeout(pollRef.current);
      }
    };
  }, []);

  // Polling function using useEffect to handle the recursive nature
  const startPolling = useCallback((id: string) => {
    const poll = async () => {
      if (!mountedRef.current) return;

      try {
        const taskStatus = await taskService.getStatus(id);
        
        if (!mountedRef.current) return;
        
        setStatus(taskStatus);
        callbacksRef.current.onProgress?.(taskStatus);

        if (taskStatus.status === 'completed' || taskStatus.status === 'failed' || taskStatus.status === 'cancelled') {
          setIsRunning(false);
          if (taskStatus.status === 'completed') {
            callbacksRef.current.onComplete?.(taskStatus);
          } else if (taskStatus.status === 'failed') {
            callbacksRef.current.onError?.(new Error(taskStatus.message || 'Task failed'));
          }
        } else {
          // Continue polling
          pollRef.current = setTimeout(poll, pollInterval);
        }
      } catch (error) {
        if (!mountedRef.current) return;
        setIsRunning(false);
        callbacksRef.current.onError?.(error instanceof Error ? error : new Error('Failed to get task status'));
      }
    };
    
    poll();
  }, [pollInterval]);

  const startTask = useCallback((id: string) => {
    // Clear any existing poll
    if (pollRef.current) {
      clearTimeout(pollRef.current);
    }
    
    setTaskId(id);
    setIsRunning(true);
    setStatus({
      task_id: id,
      status: 'pending',
      current: 0,
      total: 0,
      percentage: 0,
      message: 'Starting...',
    });
    
    // Start polling
    startPolling(id);
  }, [startPolling]);

  const cancelTask = useCallback(async () => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
    }
    
    if (taskId) {
      try {
        await taskService.cancel(taskId);
        setIsRunning(false);
        setStatus(prev => prev ? { ...prev, status: 'cancelled', message: 'Task cancelled' } : null);
      } catch (error) {
        console.error('Failed to cancel task:', error);
      }
    }
  }, [taskId]);

  const applyResults = useCallback(async () => {
    if (!taskId) {
      throw new Error('No task ID');
    }
    return taskService.applyResults(taskId);
  }, [taskId]);

  const reset = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
    }
    setTaskId(null);
    setStatus(null);
    setIsRunning(false);
  }, []);

  return {
    taskId,
    status,
    isRunning,
    progress: status?.percentage ?? 0,
    message: status?.message ?? '',
    startTask,
    cancelTask,
    applyResults,
    reset,
  };
}

/**
 * Hook for managing bulk processing with background tasks
 */
export function useBulkBackgroundProcess() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0, percentage: 0 });
  const [error, setError] = useState<string | null>(null);
  
  const taskHook = useBackgroundTask({
    onProgress: (status) => {
      setProgress({
        current: status.current,
        total: status.total,
        percentage: status.percentage,
      });
    },
    onComplete: () => {
      setIsProcessing(false);
    },
    onError: (err) => {
      setIsProcessing(false);
      setError(err.message);
    },
  });

  const startBulkProcess = async (
    documents: Array<{
      document_uuid: string;
      corners?: CornerPoints;
      settings?: ScanSettings;
    }>,
    defaultSettings?: ScanSettings
  ) => {
    setIsProcessing(true);
    setError(null);
    setProgress({ current: 0, total: documents.length, percentage: 0 });
    
    try {
      const response = await taskService.startBulkProcess(documents, defaultSettings);
      taskHook.startTask(response.task_id);
    } catch (err) {
      setIsProcessing(false);
      setError(err instanceof Error ? err.message : 'Failed to start bulk processing');
      throw err;
    }
  };

  const resetAll = useCallback(() => {
    taskHook.reset();
    setIsProcessing(false);
    setProgress({ current: 0, total: 0, percentage: 0 });
    setError(null);
  }, [taskHook]);

  return {
    isProcessing,
    progress,
    error,
    taskId: taskHook.taskId,
    status: taskHook.status,
    startBulkProcess,
    cancelProcess: taskHook.cancelTask,
    applyResults: taskHook.applyResults,
    reset: resetAll,
  };
}
