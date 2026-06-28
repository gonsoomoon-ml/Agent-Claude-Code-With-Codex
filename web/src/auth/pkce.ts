// PKCE 생성기 (Proof Key for Public Client Extension)
// Web Crypto를 이용해 S256 challenge를 생성합니다.

function b64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')
}

export function generateVerifier(): string {
  const a = new Uint8Array(48); crypto.getRandomValues(a)
  return b64url(a.buffer)
}

export async function generateChallenge(verifier: string): Promise<string> {
  return b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)))
}

export function generateState(): string {
  const a = new Uint8Array(16); crypto.getRandomValues(a)
  return b64url(a.buffer)
}
