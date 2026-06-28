// Cognito 설정 상수

export const AUTH = {
  hostedUI: 'https://briefing-users-gonsoo-057716757052.auth.us-east-1.amazoncognito.com',
  clientId: '29ghm34nr4m2enqa6sbeua6fgn',
  scope: 'openid email',
  redirectUri: () => `${location.origin}/`,
}
