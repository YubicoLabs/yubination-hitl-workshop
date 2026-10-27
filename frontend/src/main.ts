import './shoelace-assets';
import '@shoelace-style/shoelace/dist/themes/light.css';
import '@shoelace-style/shoelace/dist/themes/dark.css';
import '@shoelace-style/shoelace/dist/shoelace.js';
import * as Sentry from '@sentry/browser';

const getEnvironment = () => {
  const hostname = window.location.hostname;
  if (hostname === 'staging.example.invalid') {
    return 'staging';
  }
  if (hostname === 'preloop.ai') {
    return 'production';
  }
  // Fallback to development for unknown domains
  return 'development';
};

export const env = getEnvironment();

Sentry.init({
  dsn: '',
  tracesSampleRate: 0.01,
  environment: env,
});

import './components/lit-app.ts';
import { Theme, DEFAULT_THEME } from './theme';
import { unifiedWebSocketManager } from './services/unified-websocket-manager';
import { activityTracker } from './services/activity-tracker';
import { router } from './router';

function applyTheme(theme: Theme) {
  const darkTheme = 'sl-theme-dark';
  const lightTheme = 'sl-theme-light';

  if (theme === 'system') {
    const prefersDark = window.matchMedia(
      '(prefers-color-scheme: dark)'
    ).matches;
    document.documentElement.classList.toggle(darkTheme, prefersDark);
    document.documentElement.classList.toggle(lightTheme, !prefersDark);
  } else {
    document.documentElement.classList.toggle(darkTheme, theme === 'dark');
    document.documentElement.classList.toggle(lightTheme, theme === 'light');
  }
}

// Apply theme on initial load
const storedTheme = (localStorage.getItem('theme') as Theme) || DEFAULT_THEME;
applyTheme(storedTheme);

// Listen for theme changes from the settings view
window.addEventListener('theme-change', (e: any) => {
  applyTheme(e.detail.theme);
});

// Listen for system theme changes
window
  .matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change', () => {
    const currentTheme =
      (localStorage.getItem('theme') as Theme) || DEFAULT_THEME;
    if (currentTheme === 'system') {
      applyTheme('system');
    }
  });

// Initialize unified WebSocket connection
// This establishes a persistent connection that survives page navigation
unifiedWebSocketManager.connect();

// Initialize activity tracking
activityTracker.initializeAutoTracking();

// Track page views on route changes
// Vaadin Router fires 'vaadin-router-location-changed' event on navigation
let lastTrackedPath: string | null = null;

function trackCurrentPage() {
  const currentPath = window.location.pathname;

  // Only track if path actually changed
  if (currentPath !== lastTrackedPath) {
    lastTrackedPath = currentPath;
    activityTracker.trackPageView(currentPath);
    console.debug('Tracked page view:', currentPath);
  }
}

// Track initial page
trackCurrentPage();

// Listen for route changes
window.addEventListener('vaadin-router-location-changed', () => {
  trackCurrentPage();
});

// Also track on popstate (browser back/forward buttons)
window.addEventListener('popstate', () => {
  trackCurrentPage();
});

// Log connection state changes (for debugging)
if (env === 'development') {
  unifiedWebSocketManager.onStateChange((state) => {
    console.log(`WebSocket state: ${state}`);
  });
}
