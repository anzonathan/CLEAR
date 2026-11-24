/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Django URLs end in '/'; stop Next from 308-redirecting them to the slashless form.
  skipTrailingSlashRedirect: true,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*.googleusercontent.com',
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*/',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*/`,
      },
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
