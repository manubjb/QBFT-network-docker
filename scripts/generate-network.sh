#!/bin/bash
set -e

echo "🔧 Gerando a rede QBFT (chaves + genesis)..."

# Limpa geração anterior, se existir (deixa idempotente: dá pra rodar de novo sem lixo)
rm -rf nodes/networkFiles

# Roda o gerador dentro do Docker, montando config/ e nodes/ como volumes
docker run --rm \
  -v "$(pwd)/config:/config" \
  -v "$(pwd)/nodes:/nodes" \
  hyperledger/besu:26.6.0 \
  operator generate-blockchain-config \
    --config-file=/config/qbftConfigFile.json \
    --to=/nodes/networkFiles \
    --private-key-file-name=key

echo "✅ Pronto. Artefatos gerados em nodes/networkFiles/"