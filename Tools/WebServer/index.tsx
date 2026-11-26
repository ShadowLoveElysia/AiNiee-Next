import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { installAuthenticatedApiFetch } from './services/DataService';

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Failed to find the root element');

installAuthenticatedApiFetch();

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
