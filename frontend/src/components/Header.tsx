import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/authStore';
import { useTheme } from '@/components/ThemeProvider';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { 
  ScanLine, 
  LogOut, 
  User, 
  Languages, 
  Moon, 
  Sun, 
  FileText,
  History,
} from 'lucide-react';
import i18n from '@/i18n';

export function Header() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, isAuthenticated } = useAuthStore();
  const { theme, setTheme } = useTheme();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'id' : 'en';
    i18n.changeLanguage(newLang);
    localStorage.setItem('language', newLang);
  };

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  const getInitials = (name?: string) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div 
            className="flex items-center gap-2 cursor-pointer"
            onClick={() => navigate('/')}
          >
            <ScanLine className="h-6 w-6 text-primary" />
            <span className="text-xl font-bold hidden sm:inline">{t('common.appName')}</span>
          </div>

          {isAuthenticated && (
            <nav className="hidden md:flex items-center gap-1">
              <Button 
                variant={isActive('/') ? 'secondary' : 'ghost'} 
                size="sm"
                onClick={() => navigate('/')}
              >
                <FileText className="h-4 w-4 mr-2" />
                {t('scan.title')}
              </Button>
              <Button 
                variant={isActive('/history') ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => navigate('/history')}
              >
                <History className="h-4 w-4 mr-2" />
                {t('documents.title')}
              </Button>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <Button variant="ghost" size="icon" onClick={toggleTheme} title={t('common.toggleTheme', 'Toggle theme')}>
            {theme === 'dark' ? (
              <Sun className="h-5 w-5" />
            ) : (
              <Moon className="h-5 w-5" />
            )}
          </Button>

          <Button variant="ghost" size="icon" onClick={toggleLanguage} title={i18n.language === 'en' ? 'Bahasa Indonesia' : 'English'}>
            <Languages className="h-5 w-5" />
          </Button>

          {isAuthenticated && user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-9 w-9 rounded-full">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback>{getInitials(user.full_name || user.username)}</AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="flex items-center justify-start gap-2 p-2">
                  <div className="flex flex-col space-y-1 leading-none">
                    <p className="font-medium">{user.full_name || user.username}</p>
                    <p className="text-sm text-muted-foreground">{user.email}</p>
                  </div>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate('/')} className="md:hidden">
                  <FileText className="mr-2 h-4 w-4" />
                  {t('scan.title')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate('/history')} className="md:hidden">
                  <History className="mr-2 h-4 w-4" />
                  {t('documents.title')}
                </DropdownMenuItem>
                <DropdownMenuSeparator className="md:hidden" />
                <DropdownMenuItem onClick={() => navigate('/profile')}>
                  <User className="mr-2 h-4 w-4" />
                  Profile
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  {t('auth.logout')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button onClick={() => navigate('/login')}>
              {t('auth.login')}
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
