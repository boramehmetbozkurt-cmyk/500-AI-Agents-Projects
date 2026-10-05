import{defineConfig}from"vite";import react from"@vitejs/plugin-react";import fs from"fs";
const KEY=fs.readFileSync("/home/ubuntu/demo_run/.key","utf8").trim();
export default defineConfig({plugins:[react()],server:{host:"0.0.0.0",port:3000,allowedHosts:true,proxy:{"/api":{target:"http://127.0.0.1:8000",changeOrigin:true,rewrite:p=>p.replace(/^\/api/,""),configure:(proxy)=>{proxy.on("proxyReq",(req)=>{if(!req.getHeader("x-api-key"))req.setHeader("X-API-Key",KEY)})}}}}});
