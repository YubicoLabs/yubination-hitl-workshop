import { Plugin } from 'vite';

export default function landingPagePlugin(): Plugin {
  return {
    name: 'vite-plugin-landing',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/') {
          req.url = '/landing.html';
        }
        next();
      });
    },
  };
}
