import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Афиша культуры Башкортостана',
  description: 'Культурные события Башкортостана в одном месте',
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <head>
        <script src="https://telegram.org/js/telegram-web-app.js" async />
      </head>
      <body>{children}</body>
    </html>
  );
}
