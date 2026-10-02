import sys
sys.path.insert(0, "analise")
from pathlib import Path
import consolidar_cenario as c
d, nonce = Path(sys.argv[1]), int(sys.argv[2])
rep, log = c.ler_report(d / "report.html"), c.ler_log(d / "caliper.log")
linhas = [c.RE_ANSI.sub("", l) for l in (d / "caliper.log").read_text(encoding="utf-8").splitlines()]
i = max(i for i, l in enumerate(linhas) if "Benchmark successfully finished" in l)
print(f"caliper.log: 'Benchmark successfully finished' na linha {i + 1} de {len(linhas)}; depois dela: "
      + (" / ".join(l[24:].strip() for l in linhas[i + 1:]) or "nada"))
print(f"Total rounds: {log['total']}; report.html == tabela final do log: {rep == log['tabela_final']}")
for k, v in rep.items():
    print(f"{k}: Succ {v['Succ']} | Fail {v['Fail']} | Avg Latency {v['Avg Latency (s)']} s | "
          f"Throughput {v['Throughput (TPS)']} TPS")
alertas = []
ok_tipos = ("Transaction nonce is too distant from current sender nonce", "Transaction was not mined within 50 blocks")
for k, r in log["rounds"].items():
    fail = int(rep[k]["Fail"]) if k in rep else None
    if r["erros"]:
        print(f"  {k} falhas por tipo: " + "; ".join(f"{n} x {m}" for m, n in r["erros"].items()))
    if fail is not None and (len(r["nonces"]) != fail or sum(r["erros"].values()) != fail):
        alertas.append(f"{k}: Fail={fail}, cabeçalhos={len(r['nonces'])}, linhas Error={sum(r['erros'].values())}")
    for m in r["erros"]:
        if not any(t in m for t in ok_tipos):
            alertas.append(f"{k}: tipo de falha inesperado: {m}")
    if "not mined" in " ".join(r["erros"]):
        ns = sorted(r["nonces"])
        print(f"  {k}: falhas 'not mined' presentes (não interrompem, decisão A); nonces com falha {ns[0]}..{ns[-1]}")
if int(rep["tps-20"]["Fail"]) > 0:
    alertas.append("tps-20 com falhas")
if int(rep["tps-40"]["Fail"]) == 0:
    alertas.append("tps-40 com 0 falhas")
tp20 = float(rep["tps-20"]["Throughput (TPS)"])
if not 14 <= tp20 <= 17:
    alertas.append(f"throughput do tps-20 fora de 14-17: {tp20}")
esperado = 1 + 301 + 601 + int(rep["tps-40"]["Succ"])
print(f"nonce: {nonce}; esperado 1 + 301 + 601 + {rep['tps-40']['Succ']} = {esperado} -> "
      f"{'confere' if nonce == esperado else 'NÃO CONFERE'}")
if nonce != esperado:
    alertas.append("eth_getTransactionCount diferente do esperado")
print("SINAIS DE PARADA: " + (" | ".join(alertas) if alertas else "nenhum"))
