/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  sassOptions: { silenceDeprecations: ["legacy-js-api", "import", "global-builtin"], quietDeps: true },
};
export default nextConfig;

