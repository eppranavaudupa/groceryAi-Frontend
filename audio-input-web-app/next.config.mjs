/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
    experimental: {
      allowedDevOrigins: ["172.27.45.188"],
    }
}

export default nextConfig
