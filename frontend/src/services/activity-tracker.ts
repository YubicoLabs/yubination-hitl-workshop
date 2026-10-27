/**
 * Activity Tracker
 *
 * Tracks user activity and sends it through the unified WebSocket connection:
 * - Page views
 * - User actions (clicks, form submits)
 * - Conversion events
 */

import {
  unifiedWebSocketManager,
  ConnectionState,
} from './unified-websocket-manager';

export class ActivityTracker {
  private enabled = true;
  private messageQueue: any[] = [];
  private isProcessingQueue = false;

  constructor() {
    // When WebSocket connects, flush queued messages
    unifiedWebSocketManager.onStateChange((state) => {
      if (state === ConnectionState.CONNECTED) {
        this.flushQueue();
      }
    });
  }

  /**
   * Send a message, queuing it if WebSocket isn't connected yet.
   */
  private sendOrQueue(message: any): void {
    const sent = unifiedWebSocketManager.send(message);

    if (!sent) {
      // Queue the message if it couldn't be sent
      this.messageQueue.push(message);
      console.debug('Queued activity message:', message.event);
    }
  }

  /**
   * Flush queued messages when WebSocket connects.
   */
  private flushQueue(): void {
    if (this.isProcessingQueue || this.messageQueue.length === 0) return;

    this.isProcessingQueue = true;
    console.debug(
      `Flushing ${this.messageQueue.length} queued activity messages`
    );

    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      if (message) {
        unifiedWebSocketManager.send(message);
      }
    }

    this.isProcessingQueue = false;
  }

  /**
   * Track a page view.
   *
   * @param path - URL path being viewed
   * @param metadata - Optional additional metadata
   */
  trackPageView(path: string, metadata?: Record<string, any>): void {
    if (!this.enabled) return;

    this.sendOrQueue({
      type: 'activity',
      event: 'page_view',
      path: path,
      referrer: document.referrer,
      metadata: metadata || {},
      timestamp: Date.now(),
    });
  }

  /**
   * Track a user action.
   *
   * @param action - Name of the action (e.g., 'click_signup_button')
   * @param metadata - Optional additional metadata
   */
  trackAction(action: string, metadata?: Record<string, any>): void {
    if (!this.enabled) return;

    this.sendOrQueue({
      type: 'activity',
      event: 'action',
      action: action,
      metadata: metadata || {},
      timestamp: Date.now(),
    });
  }

  /**
   * Track a conversion event.
   *
   * @param event - Conversion event name (e.g., 'signup_completed', 'subscription_started')
   * @param value - Optional monetary value
   */
  trackConversion(event: string, value?: number): void {
    if (!this.enabled) return;

    this.sendOrQueue({
      type: 'activity',
      event: 'conversion',
      conversion_event: event,
      value: value,
      timestamp: Date.now(),
    });
  }

  /**
   * Enable activity tracking.
   */
  enable(): void {
    this.enabled = true;
  }

  /**
   * Disable activity tracking.
   */
  disable(): void {
    this.enabled = false;
  }

  /**
   * Check if tracking is enabled.
   */
  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Initialize automatic tracking of clicks on elements with data-track attribute.
   */
  initializeAutoTracking(): void {
    // Track clicks on elements with data-track attribute
    document.addEventListener('click', (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const trackElement = target.closest('[data-track]') as HTMLElement;

      if (trackElement) {
        const action = trackElement.getAttribute('data-track');
        if (action) {
          this.trackAction(action, {
            element: trackElement.tagName.toLowerCase(),
            text: trackElement.textContent?.trim().substring(0, 100),
            href: trackElement.getAttribute('href'),
          });
        }
      }
    });

    // Track form submissions with data-track-form
    document.addEventListener('submit', (e: SubmitEvent) => {
      const form = e.target as HTMLFormElement;
      const action = form.getAttribute('data-track-form');

      if (action) {
        this.trackAction(action, {
          element: 'form',
          action: form.action,
          method: form.method,
        });
      }
    });
  }
}

// Global singleton instance
export const activityTracker = new ActivityTracker();
