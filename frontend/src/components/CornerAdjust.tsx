import { useRef, useEffect, useState, useCallback, useMemo, type MouseEvent, type TouchEvent } from 'react';
import type { CornerPoints, ScanSettings } from '@/types';

interface CornerAdjustProps {
  imageSrc: string;
  corners: CornerPoints;
  onCornersChange: (corners: CornerPoints) => void;
  disabled?: boolean;
  settings?: ScanSettings;
}

type CornerKey = keyof CornerPoints;

export function CornerAdjust({ 
  imageSrc, 
  corners, 
  onCornersChange,
  disabled = false,
  settings
}: CornerAdjustProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [displaySize, setDisplaySize] = useState({ width: 0, height: 0 });
  const [dragging, setDragging] = useState<CornerKey | null>(null);

  // Compute CSS filters based on settings
  const imageStyle = useMemo(() => {
    if (!settings) return {};

    const filters: string[] = [];
    
    // Brightness: CSS uses 1 as default, so map -100..100 to 0..2
    if (settings.brightness !== 0) {
      const brightness = 1 + (settings.brightness / 100);
      filters.push(`brightness(${brightness})`);
    }
    
    // Contrast: CSS uses 1 as default, so map -100..100 to 0..2
    if (settings.contrast !== 0) {
      const contrast = 1 + (settings.contrast / 100);
      filters.push(`contrast(${contrast})`);
    }
    
    // Filter mode
    if (settings.filter_mode === 'grayscale') {
      filters.push('grayscale(1)');
    } else if (settings.filter_mode === 'bw') {
      filters.push('grayscale(1) contrast(2)');
    }

    return {
      filter: filters.length > 0 ? filters.join(' ') : undefined,
      transform: settings.rotation ? `rotate(${settings.rotation}deg)` : undefined,
    };
  }, [settings]);

  const updateDisplaySize = useCallback(() => {
    if (imageRef.current) {
      const rect = imageRef.current.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setDisplaySize({ width: rect.width, height: rect.height });
      }
    }
  }, []);

  const handleImageLoad = useCallback(() => {
    if (imageRef.current) {
      setImageSize({ 
        width: imageRef.current.naturalWidth, 
        height: imageRef.current.naturalHeight 
      });
      // Update display size after image loads
      updateDisplaySize();
    }
  }, [updateDisplaySize]);

  useEffect(() => {
    updateDisplaySize();
    window.addEventListener('resize', updateDisplaySize);
    return () => window.removeEventListener('resize', updateDisplaySize);
  }, [updateDisplaySize]);

  const toDisplayCoords = useCallback((point: [number, number]): [number, number] => {
    if (imageSize.width === 0 || imageSize.height === 0) return [0, 0];
    const scaleX = displaySize.width / imageSize.width;
    const scaleY = displaySize.height / imageSize.height;
    return [point[0] * scaleX, point[1] * scaleY];
  }, [imageSize, displaySize]);

  const toImageCoords = useCallback((x: number, y: number): [number, number] => {
    if (displaySize.width === 0 || displaySize.height === 0) return [0, 0];
    const scaleX = imageSize.width / displaySize.width;
    const scaleY = imageSize.height / displaySize.height;
    return [x * scaleX, y * scaleY];
  }, [imageSize, displaySize]);

  const handleMouseDown = (corner: CornerKey) => (e: MouseEvent) => {
    if (disabled) return;
    e.preventDefault();
    setDragging(corner);
  };

  const handleTouchStart = (corner: CornerKey) => (e: TouchEvent) => {
    if (disabled) return;
    e.preventDefault();
    setDragging(corner);
  };

  const handleMove = useCallback((clientX: number, clientY: number) => {
    if (!dragging || !containerRef.current || disabled) return;

    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(clientX - rect.left, displaySize.width));
    const y = Math.max(0, Math.min(clientY - rect.top, displaySize.height));
    
    const [imgX, imgY] = toImageCoords(x, y);
    
    onCornersChange({
      ...corners,
      [dragging]: [imgX, imgY],
    });
  }, [dragging, displaySize, toImageCoords, corners, onCornersChange, disabled]);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: globalThis.MouseEvent) => {
      handleMove(e.clientX, e.clientY);
    };

    const handleTouchMove = (e: globalThis.TouchEvent) => {
      if (e.touches.length > 0) {
        handleMove(e.touches[0].clientX, e.touches[0].clientY);
      }
    };

    const handleEnd = () => {
      setDragging(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleEnd);
    window.addEventListener('touchmove', handleTouchMove);
    window.addEventListener('touchend', handleEnd);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleEnd);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleEnd);
    };
  }, [dragging, handleMove]);

  const cornerKeys: CornerKey[] = ['top_left', 'top_right', 'bottom_right', 'bottom_left'];
  const displayCorners = cornerKeys.map(key => toDisplayCoords(corners[key]));

  const pathD = displayCorners.length === 4
    ? `M ${displayCorners[0][0]} ${displayCorners[0][1]} 
       L ${displayCorners[1][0]} ${displayCorners[1][1]} 
       L ${displayCorners[2][0]} ${displayCorners[2][1]} 
       L ${displayCorners[3][0]} ${displayCorners[3][1]} Z`
    : '';

  return (
    <div 
      ref={containerRef}
      className="relative inline-block select-none overflow-hidden"
    >
      <img
        ref={imageRef}
        src={imageSrc}
        alt="Document"
        className="max-w-full max-h-[70vh] object-contain transition-all duration-200"
        style={imageStyle}
        draggable={false}
        onLoad={handleImageLoad}
      />
      
      <svg
        className="absolute top-0 left-0 w-full h-full pointer-events-none"
        style={{ width: displaySize.width, height: displaySize.height }}
      >
        <path
          d={pathD}
          fill="rgba(59, 130, 246, 0.2)"
          stroke="rgb(59, 130, 246)"
          strokeWidth="2"
        />
        
        {cornerKeys.map((key, index) => {
          const [x, y] = displayCorners[index];
          return (
            <g key={key} className="pointer-events-auto cursor-move">
              <circle
                cx={x}
                cy={y}
                r={20}
                fill="transparent"
                onMouseDown={handleMouseDown(key)}
                onTouchStart={handleTouchStart(key)}
              />
              <circle
                cx={x}
                cy={y}
                r={10}
                fill={dragging === key ? 'rgb(239, 68, 68)' : 'rgb(59, 130, 246)'}
                stroke="white"
                strokeWidth="2"
                className="transition-colors"
                onMouseDown={handleMouseDown(key)}
                onTouchStart={handleTouchStart(key)}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
