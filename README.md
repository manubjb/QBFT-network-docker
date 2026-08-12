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

## O Que Pode Ser Comitado

Arquivos recomendados para publicar:

```text
.gitignore
README.md
config/qbftConfigFile.json
docker-compose.yml
genesis.json
scripts/generate-network.sh
```

## O Que Nao Deve Ser Comitado

Nao publique chaves privadas, estado local dos nos ou arquivos de ambiente:

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

## Publicacao no GitHub

Antes de publicar, confira o que sera enviado:

```bash
git status --short
git add .gitignore README.md config docker-compose.yml genesis.json scripts
git status --short
git commit -m "Initial QBFT network setup"
```

Se alguma chave ou arquivo dentro de `nodes/networkFiles/` aparecer no `git status`, nao faca commit ate corrigir o `.gitignore`.
