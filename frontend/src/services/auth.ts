import api, { setAccessToken, clearAccessToken, hasAccessToken } from './api';
import type { AuthTokens, User } from '@/types';

export const authService = {
  async login(username: string, password: string): Promise<AuthTokens> {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    const response = await api.post<AuthTokens>('/auth/token', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    
    // Store access token securely (in memory + localStorage for persistence)
    setAccessToken(response.data.access_token);
    
    // Refresh token is stored in httpOnly cookie by the server automatically
    // It's not accessible via JavaScript (XSS protection)
    
    return response.data;
  },
  
  async register(email: string, username: string, password: string, fullName?: string): Promise<User> {
    const response = await api.post<User>('/auth/register', {
      email,
      username,
      password,
      full_name: fullName,
    });
    return response.data;
  },
  
  async getCurrentUser(): Promise<User> {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },
  
  async logout(): Promise<void> {
    try {
      await api.post('/auth/logout');
    } finally {
      this.clearTokens();
    }
  },
  
  clearTokens(): void {
    clearAccessToken();
  },
  
  isAuthenticated(): boolean {
    return hasAccessToken();
  },
};
