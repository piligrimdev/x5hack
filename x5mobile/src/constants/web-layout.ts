export type WebLayout = 'phone' | 'fullscreen';

declare global {
  interface Window {
    __X5_WEB_LAYOUT__?: string;
  }
}

function normalize(value: string | undefined | null): WebLayout {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'fullscreen' || raw === 'full' || raw === '1' || raw === 'true') {
    return 'fullscreen';
  }
  return 'phone';
}

/** Docker: window.__X5_WEB_LAYOUT__ from /layout.js. Local: EXPO_PUBLIC_WEB_LAYOUT. */
export function getWebLayout(): WebLayout {
  if (typeof window !== 'undefined' && window.__X5_WEB_LAYOUT__) {
    return normalize(window.__X5_WEB_LAYOUT__);
  }
  return normalize(process.env.EXPO_PUBLIC_WEB_LAYOUT);
}

export function isPhoneWebLayout(): boolean {
  return getWebLayout() === 'phone';
}
