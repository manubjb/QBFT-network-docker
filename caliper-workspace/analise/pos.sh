#!/bin/zsh
# Etapa 2, passos 4 e 5, sinais de parada, sono do Mac, diagnóstico de validade e logs brutos.
# uso: pos.sh <REP> <EXEC>
set -u
REP=$1
EXEC=$2
S=${0:A:h}
cd /Users/manubjb/Desktop/QBFT-network-docker/caliper-workspace
A=resultados/A-txpool-padrao
D=$A/rep$REP
ADDR=0x627306090abaB3A6e1400e9345bC60c78a8BEf57

ts=$(date -Iseconds)
h=$($S/rpc.sh eth_getTransactionCount "[\"$ADDR\",\"latest\"]" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"])')
echo "$ts eth_getTransactionCount($ADDR, latest) = $h ($((h)))" > $D/tx_count.txt
echo "tx_count.txt: $(cat $D/tx_count.txt)"

python3 $S/checks.py "$D" "$((h))"

ini=$(cat $S/prep_inicio_rep$REP.txt)
sono=$(pmset -g log | awk -v ini="$ini" '($1" "$2) >= ini && $4 == "Sleep"')
echo "SONO DO MAC desde $ini: ${sono:-nenhum}"

echo "--- diagnóstico de validade (execução $EXEC) ---"
python3 $S/diag.py $D "rep$REP (execução $EXEC)" $A/diagnostico/rep$REP.txt | sed -n '/^(i)/,$p' | grep -vE '^- (tps|fora)' 
st=${pipestatus[1]}
echo "(diag exit $st: 0 = válida, 3 = inválida)"

L=$A/diagnostico/logs/rep$REP
mkdir -p $L
for c in qbft-node1 qbft-node2 qbft-node3 qbft-node4 qbft-rpcnode; do docker logs $c > $L/${c#qbft-}.log 2>&1; done
echo "logs brutos: $(ls $L | tr '\n' ' ')($(cat $L/*.log | wc -l | tr -d ' ') linhas)"
