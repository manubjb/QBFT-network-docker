#!/bin/zsh
# uso: rpc.sh <método> [params-json]   (rpcnode, HTTP na porta 8555 do host)
curl -s --retry 30 --retry-connrefused --retry-delay 2 --max-time 10 \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" \
  http://localhost:8555
