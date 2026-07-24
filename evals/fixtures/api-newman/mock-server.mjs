import { createServer } from "node:http";

createServer((request, response) => {
  if (request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end('{"status":"ok"}');
    return;
  }
  response.writeHead(404).end();
}).listen(18080, "127.0.0.1");
