#!/bin/zsh
# Etapa 2, passo 3 (Caliper), com caffeinate -is e a regra dos 60 s para o worker.
# uso: run.sh <REP> <EXEC>
set -u
REP=$1
EXEC=$2
cd /Users/manubjb/Desktop/QBFT-network-docker/caliper-workspace
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null; nvm use >/dev/null
D=resultados/A-txpool-padrao/rep$REP
NOTAS=resultados/A-txpool-padrao/notas.txt
[ -e $D/caliper.log ] && { echo "ERRO: $D/caliper.log já existe"; exit 1; }
echo "node $(node --version)"

date -Iseconds > $D/inicio.txt
echo "inicio: $(cat $D/inicio.txt)"
( caffeinate -is npx caliper launch manager --caliper-workspace ./ \
    --caliper-networkconfig networks/besuDocker.json \
    --caliper-benchconfig benchmarks/config.yaml \
    --caliper-report-path $D/report.html 2>&1 | tee $D/caliper.log > /dev/null ) &
PIPE=$!

limpo() { sed $'s/\x1b\\[[0-9;]*m//g' $D/caliper.log 2>/dev/null }
while kill -0 $PIPE 2>/dev/null && ! limpo | grep -q "Benchmark successfully finished"; do sleep 2; done
if ! limpo | grep -q "Benchmark successfully finished"; then
  wait $PIPE; echo "ATENÇÃO: pipeline terminou (status $?) sem 'Benchmark successfully finished'"; exit 2
fi
H_OK=$(limpo | grep "Benchmark successfully finished" | head -1 | cut -c12-23)
echo "'Benchmark successfully finished' no log às $H_OK; aguardando até 60 s pelo encerramento"

for i in {1..30}; do kill -0 $PIPE 2>/dev/null || break; sleep 2; done
if kill -0 $PIPE 2>/dev/null; then
  W=$(pgrep -f "caliper launch worker" | tr '\n' ' ')
  M=$(pgrep -f "caliper launch manager" | tr '\n' ' ')
  echo "processo do Caliper ativo 60 s depois; worker: ${W:-nenhum} | manager: ${M:-nenhum}"
  if [ -n "$W" ]; then
    kill -TERM ${=W}
    H_KILL=$(date -Iseconds)
    echo "SIGTERM no worker às $H_KILL"
    printf '%s\n' "" "execução $EXEC (pasta rep$REP): 'Benchmark successfully finished' às $H_OK (hora do caliper.log); processo do Caliper" \
      "ainda ativo 60 s depois. Worker (PID $W) encerrado com SIGTERM às $H_KILL." >> $NOTAS
  fi
  for i in {1..15}; do kill -0 $PIPE 2>/dev/null || break; sleep 2; done
  kill -0 $PIPE 2>/dev/null && { echo "ATENÇÃO: pipeline ainda ativo após o SIGTERM; nada mais foi encerrado"; exit 3; }
else
  echo "processo do Caliper encerrou sozinho em até 60 s"
fi
wait $PIPE; echo "status do pipeline: $?"
echo "fim do comando: $(date -Iseconds)"
echo "processos caliper restantes: $(pgrep -f 'caliper launch' | tr '\n' ' ' | grep . || echo nenhum)"
