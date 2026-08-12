# QBFT Network Docker

Rede local QBFT usando Hyperledger Besu e Docker Compose.

## Objetivo

Este repositorio faz parte de uma prova de conceito desenvolvida para o meu Trabalho de Conclusao de Curso.

O objetivo e demonstrar a criacao e execucao de uma rede blockchain permissionada local, utilizando o mecanismo de consenso QBFT do Hyperledger Besu. A estrutura foi pensada para fins academicos, testes controlados e experimentacao em ambiente local.

Este projeto nao representa uma rede de producao. Chaves privadas, dados gerados pelos nos e arquivos de ambiente devem permanecer fora do Git.

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

O script gera os artefatos em `nodes/networkFiles/`. Esses arquivos incluem chaves privadas e nao devem ser publicados.

## Subir os Nos

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

Para remover tambem dados locais gerados, apague os diretorios dentro de `nodes/*/data` conforme necessario.

## Seguranca

Este repositorio foi preparado para publicar apenas a configuracao e os scripts necessarios para reproduzir a prova de conceito.

Nao publique chaves privadas, estado local dos nos ou arquivos de ambiente. Esses arquivos sao gerados localmente durante a execucao da rede e estao listados no `.gitignore`:

```text
.env
.env.*
nodes/**/data/key
nodes/**/data/key.pub
nodes/networkFiles/
nodes/**/data/database/
nodes/**/data/caches/
nodes/**/data/besu.*
nodes/**/data/*METADATA.json
```

Arquivos `key` sao chaves privadas dos nos Besu. Se forem publicados, qualquer pessoa pode usar essas chaves.
