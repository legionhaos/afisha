import React from 'react';
import { createRoot } from 'react-dom/client';
import MiniAppPage from '../frontend/src/app/miniapp/page';
import '../frontend/src/app/globals.css';

const root = document.getElementById('root');
if (!root) throw new Error('Mini App root element is missing');
createRoot(root).render(<MiniAppPage />);
