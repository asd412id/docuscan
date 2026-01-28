import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

// Token storage keys
const ACCESS_TOKEN_KEY = 'access_token';

// CSRF configuration
const CSRF_COOKIE_NAME = 'csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

// In-memory storage for access token (more secure than localStorage for short-lived tokens)
let accessTokenInMemory: string | null = null;

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // Enable sending cookies for refresh token and CSRF
  withCredentials: true,
});

// CSRF token management
function getCsrfToken(): string | null {
  // Read CSRF token from cookie
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === CSRF_COOKIE_NAME) {
      return decodeURIComponent(value);
    }
  }
  return null;
}

// Token management functions
export function getAccessToken(): string | null {
  // First check memory, then localStorage for backward compatibility
  return accessTokenInMemory || localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  accessTokenInMemory = token;
  // Also store in localStorage for page refresh persistence
  // Note: For maximum security, you could skip localStorage entirely
  // and require re-login on page refresh
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  accessTokenInMemory = null;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  // Also clear legacy refresh token from localStorage if present
  localStorage.removeItem('refresh_token');
}

export function hasAccessToken(): boolean {
  return !!getAccessToken();
}

// Token refresh state to prevent multiple concurrent refresh requests
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];
let refreshFailedCallbacks: (() => void)[] = [];

function subscribeTokenRefresh(
  onSuccess: (token: string) => void,
  onFailure: () => void
) {
  refreshSubscribers.push(onSuccess);
  refreshFailedCallbacks.push(onFailure);
}

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach((callback) => callback(token));
  refreshSubscribers = [];
  refreshFailedCallbacks = [];
}

function onRefreshFailed() {
  refreshFailedCallbacks.forEach((callback) => callback());
  refreshSubscribers = [];
  refreshFailedCallbacks = [];
}

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Add CSRF token for state-changing requests
    const method = config.method?.toUpperCase();
    if (method && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        config.headers[CSRF_HEADER_NAME] = csrfToken;
      }
    }
    
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    
    // Handle 401 errors (unauthorized)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      // Check if we have an access token (indicating we were logged in)
      if (!hasAccessToken()) {
        // No token at all, redirect to login
        window.location.href = '/login';
        return Promise.reject(error);
      }

      // If already refreshing, queue this request
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh(
            (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(api(originalRequest));
            },
            () => reject(error)
          );
        });
      }

      // Start refresh process
      isRefreshing = true;
      
      try {
        // Refresh using httpOnly cookie - no body needed
        // The refresh token is sent automatically via the cookie
        const response = await axios.post(
          `${API_BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true } // Send httpOnly cookie
        );
        
        const { access_token } = response.data;
        
        // Store new access token
        setAccessToken(access_token);
        
        // New refresh token is automatically set in httpOnly cookie by server
        
        // Notify all queued requests
        onTokenRefreshed(access_token);
        
        // Retry original request
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch {
        // Refresh failed, clear tokens and redirect
        onRefreshFailed();
        clearAccessToken();
        window.location.href = '/login';
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }
    
    return Promise.reject(error);
  }
);

export default api;
