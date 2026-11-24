import type { Metadata } from 'next';
import { Toaster } from 'sonner';
import { AuthProvider } from '@/lib/auth-context';
import './globals.css';

export const metadata: Metadata = {
  title: 'CLEAR - Clay-Court AI Referee Studio',
  description: 'AI-powered tennis officiating system',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
        {/* App-wide notifications: call toast() from 'sonner' anywhere. */}
        <Toaster position="top-center" richColors closeButton toastOptions={{ className: 'clear-toast' }} />
      </body>
    </html>
  );
}
