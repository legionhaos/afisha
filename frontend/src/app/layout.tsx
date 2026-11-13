import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Афиша культуры Башкортостана',
  description: 'Культурные события Башкортостана в одном месте',
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
