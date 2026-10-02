#!/bin/zsh
# Move uma execução inválida para excluidas/, com o diagnóstico e os logs brutos, conferindo SHA-256.
# uso: excluir.sh <REP> <EXEC> <motivo-curto>
set -eu
REP=$1; EXEC=$2; MOT=$3
cd /Users/manubjb/Desktop/QBFT-network-docker/caliper-workspace/resultados/A-txpool-padrao
NOME=rep$REP-exec$EXEC-$MOT
for alvo in excluidas/$NOME diagnostico/$NOME.txt diagnostico/logs/$NOME; do
  [ ! -e $alvo ] || { echo "ERRO: $alvo já existe"; exit 1; }
done
SH=$(mktemp)
(cd rep$REP && shasum -a 256 *) > $SH
mv rep$REP excluidas/$NOME
(cd excluidas/$NOME && shasum -a 256 -c $SH | tr '\n' ' '); echo
mv diagnostico/rep$REP.txt diagnostico/$NOME.txt
sed -i '' "1s|.*|Diagnóstico de blocos: rep$REP (execução $EXEC; excluída, movida para excluidas/$NOME)|" diagnostico/$NOME.txt
mv diagnostico/logs/rep$REP diagnostico/logs/$NOME
rm -f $SH
echo "excluidas/$NOME | diagnostico/$NOME.txt | diagnostico/logs/$NOME"
