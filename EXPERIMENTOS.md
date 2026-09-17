# Experimentos de capacidade — branch `exp/capacidade`

Esta branch reúne testes **exploratórios** de desempenho da função `registrarBatch` do contrato
`RegistroDeBatches` na rede Hyperledger Besu/QBFT conteinerizada deste repositório.

> **Relação com o artigo.** Os resultados publicados no artigo (LAATIN Science) correspondem ao
> **cenário A** e estão na branch `main`. Os cenários desta branch não fizeram parte do artigo
> revisado e servem principalmente ao Trabalho de Conclusão de Curso. Eles investigam uma questão
> apontada na revisão: qual é a capacidade da rede quando o limite do txpool deixa de ser o
> primeiro gargalo.

## Pergunta de pesquisa

Na configuração padrão, a partir de cerca de 20 TPS a rede deixa de acompanhar a taxa de envio e,
em 40 TPS, o txpool do Besu rejeita a maioria das transações. A pergunta desta branch é:

**Ao ampliar o txpool, a capacidade de ancoragem aumenta ou o limite passa para outro ponto da rede?**

## Cenários

Cada cenário muda **uma única variável** em relação ao anterior.

| Cenário | txpool | Genesis (`gasLimit` / período de bloco) | Rounds (TPS) | Onde está | Situação |
|---|---|---|---|---|---|
| A | padrão do Besu | 4.700.000 / 2 s | 10, 20, 40 | `main` (tag `exp-txpool-padrao`) | concluído (artigo) |
| B | `--tx-pool-max-future-by-sender=10000` e `--tx-pool-max-prioritized=10000` | 4.700.000 / 2 s | 10, 20, 40, 60, 80 | esta branch | concluído (3 repetições) |
| C | igual ao B | `gasLimit` ampliado / 2 s | a definir | esta branch | planejado |

### O que se mantém constante em todos os cenários

- Imagem `hyperledger/besu:26.6.0`, consenso QBFT, 4 validadores e 1 `rpcnode` não validador.
- Hyperledger Caliper `0.6.0` (última versão com suporte a Ethereum/Besu), Node 20 via `.nvmrc`.
- 1 worker do Caliper, com uma única conta remetente.
- Rounds de 30 s com taxa fixa (`fixed-rate`), alvo `ws://localhost:8556` (`rpcnode`).
- Workload `workload/registrarBatch.js`: `batchId` e `fingerprint` aleatórios de 32 bytes e
  `tamanho` aleatório. O teste usa o formato real da transação sem nenhum dado pessoal.
- 300.000 de gas por transação.
- `--rpc-http-host=0.0.0.0` nos nós (interface de escuta do RPC; não altera consenso nem txpool).

## Protocolo de execução

1. Rede reiniciada do zero antes de **cada** repetição, mantendo as chaves dos nós:
   `docker compose down`, remoção de `nodes/*/data/database` e `nodes/*/data/caches`,
   `docker compose up -d`.
2. Conferência de produção de blocos com `eth_blockNumber` antes de iniciar.
3. Execução do Caliper e registro da configuração junto do resultado.
4. Após a execução, conferência do número de transações incluídas com `eth_getTransactionCount`
   da conta remetente.
5. Três repetições por cenário.

### Estrutura dos resultados

```text
caliper-workspace/
├── analise/
│   └── consolidar_cenario.py    # consolida as repetições de um cenário
└── resultados/
    └── B-txpool-ajustado/
        ├── resumo.csv           # valores por repetição, média e desvio padrão (gerado)
        ├── rep1/
        │   ├── config.yaml      # configuração do Caliper usada
        │   ├── besu_args.txt    # argumentos dos containers rpcnode e node1
        │   ├── commit.txt       # commit do repositório no momento da execução
        │   ├── report.html      # relatório do Caliper
        │   └── caliper.log      # saída completa da execução
        ├── rep2/
        └── rep3/
```

Para regenerar o resumo, dentro de `caliper-workspace/`:

```bash
python3 analise/consolidar_cenario.py resultados/B-txpool-ajustado
```

O script usa só a biblioteca padrão do Python e não altera as pastas `rep*`. Primeiro ele confere
se `config.yaml`, `besu_args.txt` e `commit.txt` são idênticos entre as repetições, se cada
`caliper.log` termina com `Benchmark successfully finished` e se o número de falhas do relatório
bate com o do log. Se algo divergir, ele para sem gerar o resumo. Em seguida grava `resumo.csv` e
imprime no terminal as tabelas usadas na seção de resultados.

O `resumo.csv` tem uma linha por round e métrica, com as colunas
`round, metrica, detalhe, rep1, rep2, rep3, n, media, desvio_padrao`, sem arredondamento. A métrica
`falhas_por_tipo` traz a mensagem de erro na coluna `detalhe`. No documento, latências, TPS e
durações aparecem com 2 casas decimais.

### Como reproduzir uma repetição

Na raiz do repositório:

```bash
docker compose down
rm -rf nodes/*/data/database nodes/*/data/caches
docker compose up -d
```

Dentro de `caliper-workspace/`:

```bash
nvm use
CEN=B-txpool-ajustado; REP=1
D=resultados/$CEN/rep$REP; mkdir -p $D
cp benchmarks/config.yaml $D/
docker inspect qbft-rpcnode qbft-node1 --format '{{.Name}} {{.Args}}' > $D/besu_args.txt
git rev-parse HEAD > $D/commit.txt
npx caliper launch manager \
  --caliper-workspace ./ \
  --caliper-networkconfig networks/besuDocker.json \
  --caliper-benchconfig benchmarks/config.yaml \
  --caliper-report-path $D/report.html \
  2>&1 | tee $D/caliper.log
```

O arquivo `networks/besuDocker.json` não é versionado, pois contém caminhos locais e a chave
privada de uma conta de teste. Veja o `README.md` para criar uma configuração equivalente.

## Como ler as métricas do Caliper

- **Throughput inclui falhas.** O Caliper calcula o throughput sobre todas as transações
  finalizadas no round, com sucesso ou com falha. Quando há falhas, o valor informado superestima
  a capacidade real. Nesses casos, a capacidade é estimada como `Succ ÷ duração do round`.
- **Falha não é necessariamente rejeição.** Há dois tipos de falha nestes testes:
  - `Transaction nonce is too distant from current sender nonce`: rejeição pelo txpool do Besu;
  - `Transaction was not mined within 50 blocks`: limite de espera do cliente web3.js
    (50 blocos ≈ 100 s com bloco de 2 s). A transação pode ser incluída depois.
- **Inclusão na cadeia.** Para distinguir os dois casos, compara-se o `eth_getTransactionCount`
  da conta remetente com o número de transações enviadas mais o deploy do contrato.
- **Duração do round.** Quando a fila cresce, o round dura mais que os 30 s configurados, porque o
  Caliper espera a finalização das transações pendentes.
- **Latência considera só sucessos.** No Caliper 0.6.0, as latências mínima, média e máxima são
  calculadas apenas sobre as transações com sucesso (`caliper-core`, `lib/manager/report/report.js`).
  Quando há falhas por tempo de espera, as transações mais lentas ficam fora da conta e a latência
  informada subestima a espera real.
- **Resolução do relatório.** O Caliper informa throughput e send rate com uma casa decimal e
  latências com duas. Diferenças menores que essa resolução não aparecem, nem no desvio padrão
  entre repetições.

## Resultados

### Cenário A — txpool padrão (referência, branch `main`)

Reexecução de 16/09/2026, que reproduz a rodada registrada no caderno de laboratório.

| Round | Succ | Fail | Latência média (s) | Throughput informado (TPS) | Observação |
|---|---:|---:|---:|---:|---|
| tps-10 | 301 | 0 | 1,12 | 9,5 | |
| tps-20 | 601 | 0 | 4,70 | 15,4 | início da saturação |
| tps-40 | 328 | 873 | 6,18 | 40,0* | 73% rejeitadas pelo txpool (`nonce too distant`) |

\* valor inflado pelas falhas; não representa capacidade.

### Cenário B — txpool ampliado

Três repetições em 16/09/2026, com início às 21:41 (rep1), 21:55 (rep2) e 22:06 (rep3), todas no
commit `8cc89b1` e com a rede reiniciada do zero antes de cada uma.

**Comparabilidade.** Antes da consolidação, conferiu-se que `config.yaml`, `besu_args.txt`
(inclusive as opções de txpool) e `commit.txt` são idênticos nas três pastas e que os três
`caliper.log` terminam com `Benchmark successfully finished` e 5 de 5 rounds concluídos. O script
`analise/consolidar_cenario.py` repete essa conferência sempre que é executado.

> **Sobre n = 3.** Três repetições formam uma amostra pequena. Os desvios padrão (amostrais,
> n − 1) servem para mostrar quanto os resultados variaram entre as execuções. Não foi aplicado
> teste estatístico, e média ± desvio não deve ser lido como intervalo de confiança.

#### Resultado consolidado

Média ± desvio padrão amostral das três repetições. Os valores sem arredondamento estão em
`resultados/B-txpool-ajustado/resumo.csv`.

| Round | Succ | Fail | Latência média (s) | Latência máx. (s) | Throughput informado (TPS) | Capacidade estimada (TPS) | Duração do round (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| tps-10 | 301 ± 0 | 0 ± 0 | 1,24 ± 0,01 | 2,52 ± 0,11 | 9,50 ± 0,00 | 9,50 ± 0,02 | 31,69 ± 0,06 |
| tps-20 | 601 ± 0 | 0 ± 0 | 4,84 ± 0,15 | 9,33 ± 0,14 | 15,50 ± 0,00 | 15,45 ± 0,00 | 38,89 ± 0,00 |
| tps-40 | 1.201 ± 0 | 0 ± 0 | 22,66 ± 0,20 | 45,36 ± 0,11 | 16,00 ± 0,00 | 16,02 ± 0,01 | 74,97 ± 0,07 |
| tps-60 | 1.801 ± 0 | 0 ± 0 | 41,26 ± 0,03 | 83,01 ± 0,02 | 16,00 ± 0,00 | 15,95 ± 0,01 | 112,93 ± 0,05 |
| tps-80 | 2.048 ± 0 | 353 ± 0 | 51,19 ± 0,04 | 101,81 ± 0,07 | 18,30 ± 0,00 | 15,63 ± 0,00 | 131,05 ± 0,01 |

- **Capacidade estimada** é `Succ ÷ duração do round`, calculada em cada repetição e depois
  resumida. Ela existe porque o throughput do Caliper é
  `(Succ + Fail) ÷ (última finalização − primeira criação)`: as falhas entram na conta como se
  fossem transações processadas. Em tps-80, o throughput informado (18,30 TPS) superestima a
  capacidade; contando só as transações com sucesso, ela fica em 15,63 TPS. Nos rounds sem falha,
  as duas medidas diferem em menos de 0,1 TPS, por causa da janela de tempo um pouco diferente e do
  arredondamento do Caliper.
- **Duração do round** é o valor da linha `Finished round N (tps-X) in Y seconds` do
  `caliper.log`. Ela mede a fase de teste do round, sem a pausa de 5 s entre rounds.
- O desvio 0,00 do throughput informado reflete a resolução de uma casa decimal do Caliper. Em
  tps-80, as latências não incluem as 353 transações com falha (ver "Como ler as métricas do
  Caliper").

#### Falhas por tipo de erro

Contagem das linhas `Error:` de cada `caliper.log`, agrupadas pela mensagem. As linhas
`Failed tx on registroDeBatches` são o cabeçalho de cada falha e não entram na contagem.

| Round | Mensagem após `Error:` | rep1 | rep2 | rep3 |
|---|---|---:|---:|---:|
| tps-10 | nenhuma falha | 0 | 0 | 0 |
| tps-20 | nenhuma falha | 0 | 0 | 0 |
| tps-40 | nenhuma falha | 0 | 0 | 0 |
| tps-60 | nenhuma falha | 0 | 0 | 0 |
| tps-80 | `Transaction was not mined within 50 blocks, please make sure your transaction was properly sent. Be aware that it might still be mined!` | 353 | 353 | 353 |

As 353 falhas são as mesmas transações nas três repetições: em todas, os nonces com falha vão de
`0x1741` (5.953) a `0x18a1` (6.305), sem lacunas, ou seja, são as últimas 353 transações enviadas.
Nenhuma falha foi rejeição do txpool (`nonce too distant`). A latência máxima das transações com
sucesso em tps-80 (101,81 ± 0,07 s) fica próxima do limite de 50 blocos (≈ 100 s com bloco de 2 s).

#### Verificação na cadeia

`eth_getTransactionCount` da conta remetente, consultado após cada repetição. A consulta foi feita
manualmente e o resultado não está gravado nas pastas `rep*`.

| Repetição | `eth_getTransactionCount` | Decimal | Esperado |
|---|---|---:|---:|
| rep1 | `0x18a2` | 6.306 | 6.306 |
| rep2 | `0x18a2` | 6.306 | 6.306 |
| rep3 | `0x18a2` | 6.306 | 6.306 |

Valor esperado: deploy do contrato + 301 + 601 + 1.201 + 1.801 + 2.401 transações enviadas = 6.306.
Nas três repetições, todas as transações foram incluídas, inclusive as 353 marcadas como falha: o
maior nonce com falha (`0x18a1`) é o último nonce contado. A contagem de nonce confirma inclusão,
não sucesso de execução; reversão é improvável, pois o `batchId` é aleatório e a conta remetente é
a mesma que implantou o contrato.

#### Dados por repetição

Tabela do `report.html` de cada repetição, com a duração do round extraída do `caliper.log`. No
relatório original, send rate e throughput têm uma casa decimal.

##### rep1

| Round | Succ | Fail | Send rate (TPS) | Latência máx. (s) | Latência mín. (s) | Latência média (s) | Throughput informado (TPS) | Duração do round (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tps-10 | 301 | 0 | 10,00 | 2,65 | 0,14 | 1,24 | 9,50 | 31,72 |
| tps-20 | 601 | 0 | 20,00 | 9,49 | 0,33 | 5,01 | 15,50 | 38,89 |
| tps-40 | 1.201 | 0 | 40,00 | 45,29 | 0,25 | 22,52 | 16,00 | 74,94 |
| tps-60 | 1.801 | 0 | 60,00 | 83,01 | 0,40 | 41,29 | 16,00 | 112,90 |
| tps-80 | 2.048 | 353 | 80,00 | 101,77 | 0,63 | 51,23 | 18,30 | 131,05 |

##### rep2

| Round | Succ | Fail | Send rate (TPS) | Latência máx. (s) | Latência mín. (s) | Latência média (s) | Throughput informado (TPS) | Duração do round (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tps-10 | 301 | 0 | 10,00 | 2,46 | 0,16 | 1,23 | 9,50 | 31,72 |
| tps-20 | 601 | 0 | 20,00 | 9,26 | 0,14 | 4,78 | 15,50 | 38,89 |
| tps-40 | 1.201 | 0 | 40,00 | 45,31 | 0,19 | 22,56 | 16,00 | 74,93 |
| tps-60 | 1.801 | 0 | 60,00 | 83,03 | 0,46 | 41,27 | 16,00 | 112,98 |
| tps-80 | 2.048 | 353 | 80,00 | 101,89 | 0,53 | 51,15 | 18,30 | 131,04 |

##### rep3

| Round | Succ | Fail | Send rate (TPS) | Latência máx. (s) | Latência mín. (s) | Latência média (s) | Throughput informado (TPS) | Duração do round (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tps-10 | 301 | 0 | 10,00 | 2,45 | 0,22 | 1,24 | 9,50 | 31,62 |
| tps-20 | 601 | 0 | 20,00 | 9,23 | 0,14 | 4,72 | 15,50 | 38,89 |
| tps-40 | 1.201 | 0 | 40,00 | 45,49 | 0,47 | 22,89 | 16,00 | 75,05 |
| tps-60 | 1.801 | 0 | 60,00 | 83,00 | 0,40 | 41,23 | 16,00 | 112,90 |
| tps-80 | 2.048 | 353 | 80,00 | 101,76 | 0,61 | 51,20 | 18,30 | 131,04 |

### Leitura dos resultados

A leitura abaixo vale para as três repetições do cenário B. Como n = 3, os desvios padrão indicam
apenas quanto as execuções variaram.

**O txpool ampliado eliminou as rejeições.** Nenhum round das três repetições teve falha
`nonce too distant`, que no cenário A atingiu 73% das transações em 40 TPS. As únicas falhas foram
as 353 por tempo de espera do cliente em 80 TPS, e essas transações foram incluídas na cadeia.

**A capacidade não aumentou.** A partir de 20 TPS, a capacidade estimada ficou entre 15,45 e
16,02 TPS, com desvio padrão de no máximo 0,01 TPS nesses rounds. Dobrar a taxa de envio de 40 para
80 TPS não elevou a capacidade, que passou de 16,02 para 15,63 TPS.

**O excedente virou fila e latência.** A duração do round passou de 31,69 s em 10 TPS para
131,05 s em 80 TPS, e a latência média, de 1,24 s para 51,19 s. Transações de uma mesma conta só
entram em bloco na ordem do nonce, então as últimas enviadas são as que mais esperam. Em 80 TPS,
essa espera passou do limite de 50 blocos do cliente, e por isso as falhas são sempre as 353
últimas transações.

**As repetições foram muito parecidas.** Succ e Fail foram idênticos nas três execuções, em todos
os rounds. Os maiores desvios padrão foram de 0,20 s na latência média (tps-40), 0,14 s na latência
máxima (tps-20) e 0,07 s na duração do round (tps-40). Isso sugere que, nesta máquina, o resultado
depende principalmente da configuração da rede e pouco de variações entre execuções.

Em resposta à pergunta de pesquisa: ampliar o txpool tirou o txpool da posição de primeiro
gargalo, mas a capacidade continuou em cerca de **16 TPS**. O limite passou para outro ponto, que o
cenário B, sozinho, não identifica.

**Hipótese para o cenário C.** O teto de cerca de 16 TPS é compatível com a capacidade de cada bloco. Em medição local com Hardhat, cada chamada de 
`registrarBatch` consumiu cerca de 141.853 de gas. 
Ao montar um bloco, o Besu só inclui uma transação se o gas que ela declara (300.000, configurado no Caliper) couber no espaço restante do bloco. Com `gasLimit` de 4.700.000, isso permite 32 chamadas por bloco: depois da 32ª, restam 160.704 de gas, menos que os 300.000 declarados. Com bloco a cada 2 s, o teto é de 16 TPS, compatível com o incremento de 64 ou 96 transações por intervalo de 5 s observado nos logs. Previsão: com `gasLimit` de 9.400.000, cabem 65 chamadas por bloco, cerca de 32,5 TPS. Se a capacidade medida se aproximar desse valor, o limite do bloco fica confirmado como o segundo gargalo, depois do txpool.


Os logs trazem um indício na mesma direção. O observador do Caliper registra o total de transações
com sucesso a cada 5 s, intervalo que cobre 2 ou 3 blocos de 2 s. Nos rounds de 20 a 80 TPS, 190
dos 198 incrementos positivos entre esses registros foram de exatamente 64 ou 96 transações, isto
é, 2 ou 3 blocos de 32. Em 10 TPS, abaixo da capacidade, os incrementos ficaram entre 39 e 61,
perto de 40 e 60, o que corresponde a cerca de 20 transações por bloco. Esse indício é indireto: o
número de transações por bloco não foi consultado na cadeia (por exemplo, com
`eth_getBlockByNumber`), e essa conferência fica sugerida para o cenário C. Se a capacidade crescer
de forma proporcional ao aumentar o `gasLimit`, o limite do bloco fica confirmado como o segundo
gargalo, depois do txpool.

## Limitações

- Todos os testes rodam em uma única máquina (MacBook Air), com os cinco nós e o Caliper
  disputando os mesmos recursos.
- Os rounds são executados em sequência; a fila acumulada em um round pode afetar a latência do
  seguinte.
- Uma única conta remetente e um único worker; cenários com várias contas não foram avaliados.
- A carga é sintética. A tradução para check-ins por segundo é feita na análise, multiplicando o
  TPS confirmado pelo tamanho do lote (N).
- Não há instrumentação de infraestrutura (CPU, memória, tamanho do txpool por nó).
- O Caliper 0.6.0 é a última versão com suporte a Besu; versões posteriores removeram esse suporte.
- As três repetições do cenário B rodaram em sequência, na mesma máquina e na mesma noite. A baixa
  variação entre elas mostra repetibilidade nesse ambiente, não em outras máquinas ou condições.
- Em 80 TPS, a latência informada exclui as 353 transações que passaram do limite de 50 blocos do
  cliente; a espera real dessas transações não foi medida.
- O número de transações por bloco não foi consultado na cadeia; a relação com o `gasLimit` se
  apoia em estimativa de gas e em indício indireto do log.
- O resultado de `eth_getTransactionCount` foi conferido manualmente e não está gravado nas pastas
  das repetições.

## Segurança

As chaves dos nós e a chave da conta de teste servem apenas a esta rede local e não protegem
ativos reais. Não reutilize nenhuma delas em redes públicas, institucionais ou com valor real.
Chaves, estado dos nós e `networks/besuDocker.json` ficam fora do Git.
