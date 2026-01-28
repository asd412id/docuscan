import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { FileQuestion, Home, ArrowLeft } from 'lucide-react';

export function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="text-center max-w-md">
        <FileQuestion className="w-24 h-24 text-muted-foreground mx-auto mb-6" />
        <h1 className="text-4xl font-bold mb-2">404</h1>
        <h2 className="text-xl text-muted-foreground mb-6">
          {t('errors.pageNotFound', 'Page not found')}
        </h2>
        <p className="text-muted-foreground mb-8">
          {t('errors.pageNotFoundHint', "The page you're looking for doesn't exist or has been moved.")}
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button variant="outline" onClick={() => navigate(-1)}>
            <ArrowLeft className="mr-2 w-4 h-4" />
            {t('common.back')}
          </Button>
          <Button onClick={() => navigate('/')}>
            <Home className="mr-2 w-4 h-4" />
            {t('common.home', 'Home')}
          </Button>
        </div>
      </div>
    </div>
  );
}
