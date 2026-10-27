import type { Route } from '@vaadin/router';
import './workshop-lab-view';

/** Shared by the console router and direct-navigation browser checks. */
export const workshopLabRoutes: Route[] = [
  'agent-setup',
  'receipt-verification',
  'previewsign',
  'python-fido2-ml-dsa',
  'pq-authentication',
].map((lab) => ({
  path: `/console/workshop/yubination/${lab}`,
  action: (_context, commands) => {
    const page = commands.component('workshop-lab-view');
    page.setAttribute('lab', lab);
    return page;
  },
}));
