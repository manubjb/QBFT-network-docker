# Demonstração: verificação de certificado

Demonstração da cadeia **check-in → certificado → ancoragem → verificação**
sobre a rede QBFT deste repositório.

**Fora do escopo do artigo.** Nada nesta pasta faz parte dos experimentos,
dos resultados ou da versão citada (`main` / tag `latinoware2026`). A
demonstração não altera `caliper-workspace/resultados/`, os scripts de
benchmark nem a configuração usada pelo Caliper.

## Instância persistente

`rede/` sobe uma rede QBFT separada da do benchmark: projeto `qbft-demo`,
containers `qbft-demo-*`, sub-rede `172.31.0.0/24`, chainId 1338 e estado em
`rede/nodes/` (não versionado; o `prep.sh` não alcança). Sem reinício
automático. Pare a instância antes de rodar o benchmark.

    docker compose -f demo-verificacao/rede/docker-compose.yml up -d
    docker compose -f demo-verificacao/rede/docker-compose.yml stop

O contrato `RegistroDeBatches` foi implantado por `deploy.js`; endereço,
chainId, bloco e commit estão em `deployment.json`.

A conta do deploy (`0x627306…`) usa a chave pública de desenvolvimento
(Truffle/Ganache), conhecida por qualquer pessoa; por isso o RPC fica
restrito ao localhost (`127.0.0.1:9545` HTTP, `127.0.0.1:9546` WS).

## Dados

`dados/` guarda os dados reais usados na demonstração. A pasta está no
`.gitignore` e nada dentro dela deve ser versionado.
