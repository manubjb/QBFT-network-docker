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

## Uso

> **Pare a instância `qbft-demo` antes de qualquer execução do benchmark**
> (`docker compose -f demo-verificacao/rede/docker-compose.yml stop`): as duas
> redes disputam CPU e a demonstração afetaria as medições.

Comandos a partir da raiz do repositório, com a instância no ar. Uma pasta de
entrada tem `certificado.json` e `checkins.json` (veja `exemplo/`, só com
dados fictícios).

1. Conferir a serialização canônica contra o vetor de referência:

       node demo-verificacao/testes/conferir-vetor.js

2. Ancorar o certificado e o lote de check-ins de uma pasta (`exemplo/` ou `dados/`):

       DEMO_DEPLOYER_KEY=0x... node demo-verificacao/ancorar.js demo-verificacao/exemplo

   Recusa se a regra das atividades não for cumprida (cada atividade do
   certificado com ao menos um check-in do titular), se chainId ou hash do
   bloco 0 não baterem com `deployment.json` ou se algum id já existir no
   contrato. Grava as evidências completas em
   `<pasta>/ancoragem-<certificado_id>.json` e só metadados sem dados pessoais
   em `ancoragens.json`.

3. Verificar por `certificado_id`:

       node demo-verificacao/verificar.js 0b9f6f2e-7d1a-4c3e-9a55-3f0c2d1e4b6a demo-verificacao/exemplo

   Os ids consultados vêm do `certificado_id` informado; hash e fingerprint
   são recalculados dos arquivos da pasta.

Vereditos, para o certificado e para os check-ins:

| Veredito | Significado |
|---|---|
| `VALIDO` | o valor recalculado é igual ao registrado no contrato |
| `ADULTERADO` | o id está registrado, mas o valor recalculado é diferente (ou o arquivo não passa na serialização canônica) |
| `NAO_ANCORADO` | não há registro para o id no contrato |

Código de saída do `verificar.js`: `0` se os dois vereditos forem `VALIDO` e a
regra das atividades for cumprida; `2` caso contrário; `1` em erro de
execução (rede diferente da do `deployment.json`, arquivo ausente, argumentos).

## Dados

`dados/` guarda os dados reais usados na demonstração. A pasta está no
`.gitignore` e nada dentro dela deve ser versionado.
