import type { NextConfig } from 'next';
const config: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || '.next-production',
  // Office conversion is bounded at 180 seconds; allow its response/error to
  // reach the reader instead of the proxy cutting it off after 30 seconds.
  experimental: { proxyTimeout: 210000, proxyClientMaxBodySize: '105mb', ...(process.platform === 'win32' ? { cpus: 1, staticGenerationMaxConcurrency: 1, staticGenerationRetryCount: 3, webpackBuildWorker: false } : {}) },
  output: process.env.STANDALONE === 'true' ? 'standalone' : undefined,
  async rewrites() { return [{ source: '/api/:path*', destination: `${process.env.API_URL || 'http://127.0.0.1:8000'}/api/:path*` }]; },
  async headers() { return [{source:'/:path*',headers:[{key:'X-Content-Type-Options',value:'nosniff'},{key:'X-Frame-Options',value:'DENY'},{key:'Referrer-Policy',value:'same-origin'}]}, {source:'/api/v1/documents/:id/original',headers:[{key:'X-Frame-Options',value:'SAMEORIGIN'}]}, {source:'/api/v1/documents/:id/preview',headers:[{key:'X-Frame-Options',value:'SAMEORIGIN'}]}]; }
}; export default config;
