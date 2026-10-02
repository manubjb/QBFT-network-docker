#!/bin/zsh
# Etapa 2, passos 1 a 3 (sem o Caliper): reinício do zero, checagem da rede e metadados.
# uso: prep.sh <REP>
set -eu
REP=$1
ROOT=/Users/manubjb/Desktop/QBFT-network-docker
R=${0:A:h}/rpc.sh
D=resultados/A-txpool-padrao/rep$REP
cd $ROOT
[ -e caliper-workspace/$D ] && { echo "ERRO: caliper-workspace/$D já existe"; exit 1; }

date "+%Y-%m-%d %H:%M:%S" > ${0:A:h}/prep_inicio_rep$REP.txt
echo "--- 1. down / limpeza / up ($(date +%T)) ---"
docker compose down 2>&1 | grep -cE 'Removed|Stopped' | sed 's/^/containers removidos+parados: /'
ls -d nodes/*/data/database nodes/*/data/caches | tr '\n' ' '; echo "<- removendo"
rm -rf nodes/*/data/database nodes/*/data/caches
docker compose up -d 2>&1 | grep -c Started | sed 's/^/containers iniciados: /'

echo "--- 2. blocos e validadores ---"
num() { $R eth_blockNumber | python3 -c 'import sys,json;print(int(json.load(sys.stdin)["result"],16))'; }
for i in {1..60}; do num >/dev/null 2>&1 && break; sleep 1; done
echo "RPC 8555 respondendo após ~${i} s ($(date +%T))"
b1=$(num); t1=$(date +%T); sleep 10; b2=$(num); t2=$(date +%T)
echo "eth_blockNumber $t1: $b1 | $t2: $b2 -> subiu: $([ $b2 -gt $b1 ] && echo sim || echo NAO)"
[ $b2 -gt $b1 ] || { echo "ERRO: a rede não está produzindo blocos"; exit 1; }
nv=$($R qbft_getValidatorsByBlockNumber '["latest"]' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["result"]))')
echo "validadores em latest: $nv"
[ $nv -eq 4 ] || { echo "ERRO: esperados 4 validadores"; exit 1; }

echo "--- 3. metadados em caliper-workspace/$D ---"
cd caliper-workspace
mkdir -p $D
cp benchmarks/config.yaml $D/
docker inspect qbft-rpcnode qbft-node1 --format '{{.Name}} {{.Args}}' > $D/besu_args.txt
git rev-parse HEAD > $D/commit.txt
ref=resultados/A-txpool-padrao/excluidas/rep1-transitorio-node1
echo "commit: $(cat $D/commit.txt) | branch: $(git branch --show-current)"
echo "tx-pool em besu_args.txt: $(grep -ci tx-pool $D/besu_args.txt || true) ocorrências"
for f in config.yaml besu_args.txt commit.txt; do
  echo "$f idêntico ao da rep1 original: $(cmp -s $D/$f $ref/$f && echo sim || echo NAO)"
done
