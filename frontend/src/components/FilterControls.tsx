import { useTranslation } from 'react-i18next';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RotateCw } from 'lucide-react';
import type { ScanSettings } from '@/types';

interface FilterControlsProps {
  settings: ScanSettings;
  onSettingsChange: (settings: Partial<ScanSettings>) => void;
  disabled?: boolean;
}

export function FilterControls({ 
  settings, 
  onSettingsChange,
  disabled = false 
}: FilterControlsProps) {
  const { t } = useTranslation();

  const handleRotate = () => {
    const newRotation = (settings.rotation + 90) % 360;
    onSettingsChange({ rotation: newRotation });
  };

  return (
    <div className="space-y-6 p-4 bg-card rounded-lg border">
      <div>
        <Label className="text-sm font-medium">{t('scan.filters')}</Label>
        <Tabs 
          value={settings.filter_mode} 
          onValueChange={(value) => onSettingsChange({ filter_mode: value as ScanSettings['filter_mode'] })}
          className="mt-2"
        >
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="color" disabled={disabled}>
              {t('scan.filterColor')}
            </TabsTrigger>
            <TabsTrigger value="grayscale" disabled={disabled}>
              {t('scan.filterGrayscale')}
            </TabsTrigger>
            <TabsTrigger value="bw" disabled={disabled}>
              {t('scan.filterBW')}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between">
            <Label className="text-sm">{t('scan.brightness')}</Label>
            <span className="text-sm text-muted-foreground">{settings.brightness}</span>
          </div>
          <Slider
            value={[settings.brightness]}
            onValueChange={([value]) => onSettingsChange({ brightness: value })}
            min={-100}
            max={100}
            step={1}
            disabled={disabled}
          />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between">
            <Label className="text-sm">{t('scan.contrast')}</Label>
            <span className="text-sm text-muted-foreground">{settings.contrast}</span>
          </div>
          <Slider
            value={[settings.contrast]}
            onValueChange={([value]) => onSettingsChange({ contrast: value })}
            min={-100}
            max={100}
            step={1}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Label className="text-sm">{t('scan.rotation')}</Label>
          <p className="text-xs text-muted-foreground">{settings.rotation}°</p>
        </div>
        <Button 
          variant="outline" 
          size="icon" 
          onClick={handleRotate}
          disabled={disabled}
        >
          <RotateCw className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <Label className="text-sm">{t('scan.autoEnhance')}</Label>
        <Switch
          checked={settings.auto_enhance}
          onCheckedChange={(checked) => onSettingsChange({ auto_enhance: checked })}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
