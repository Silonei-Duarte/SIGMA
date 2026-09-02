import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'br.com.indaialpapel.sigma',
  appName: 'SIGMA',
  webDir: 'www',
  loggingBehavior: 'none',
  server: {
    url: 'https://app.suaempresa.com.br',
    cleartext: false,
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['sound', 'alert'],
    },
  },
};

export default config;
