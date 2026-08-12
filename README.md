# QBFT Network Docker

Rede local QBFT usando Hyperledger Besu e Docker Compose.

## Objetivo

Este repositório faz parte de uma prova de conceito desenvolvida para o meu Trabalho de Conclusao de Curso.

O objetivo é demonstrar a criação e execução de uma rede blockchain permissionada local, utilizando o mecanismo de consenso QBFT do Hyperledger Besu. A estrutura foi pensada para fins acadêmicos, testes controlados e experimentacao em ambiente local.

Este projeto não representa uma rede de producção. Chaves privadas, dados gerados pelos nós e arquivos de ambiente devem permanecer fora do Git.

## Requisitos

- Docker
- Docker Compose

## Estrutura

```text
config/qbftConfigFile.json   Configuracao usada para gerar a rede QBFT
docker-compose.yml           Servicos Besu da rede
genesis.json                 Genesis usado pelos nos
scripts/generate-network.sh  Script para gerar chaves e arquivos da rede
nodes/                       Dados locais gerados pelos nos
```

## Gerar a Rede

```bash
chmod +x scripts/generate-network.sh
./scripts/generate-network.sh
```

O script gera os artefatos em `nodes/networkFiles/`. Esses arquivos incluem chaves privadas e não devem ser publicados.

## Subir os Nós

```bash
docker compose up -d
```

RPC HTTP:

- `node1`: `http://localhost:8545`
- `rpcnode`: `http://localhost:8555`

## Parar a Rede

```bash
docker compose down
```

Para remover também dados locais gerados, apague os diretórios dentro de `nodes/*/data` conforme necessário.

## Seguranca

Este repositório foi preparado para publicar apenas a configuração e os scripts necessários para reproduzir a prova de conceito.

Não publique chaves privadas, estado local dos nós ou arquivos de ambiente. Esses arquivos são gerados localmente durante a execução da rede e estão listados no `.gitignore`:

