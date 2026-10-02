"""Gera resultados/A-txpool-padrao/execucoes.csv a partir dos arquivos de cada execução (só leitura)."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, "analise")
import consolidar_cenario as c

A = Path("resultados/A-txpool-padrao")
# execução -> (pasta, diagnóstico, detecção usada no item (ii))
EXECUCOES = [
    (1, "excluidas/rep1-transitorio-node1", "rep1-transitorio-node1", "só PersistBlockTask"),
    (2, "rep1", "rep1", "só PersistBlockTask (verificada antes da melhoria)"),
    (3, "excluidas/rep2-rodada1-bloco10", "rep2-rodada1-bloco10", "reforçada (diagnóstico regenerado)"),
    (4, "rep2", "rep2", "reforçada"),
    (5, "excluidas/rep3-exec5-rodada1-bloco11", "rep3-exec5-rodada1-bloco11", "reforçada"),
    (6, "excluidas/rep3-exec6-rodada2-bloco11", "rep3-exec6-rodada2-bloco11", "reforçada"),
    (7, "excluidas/rep3-exec7-rodada1-bloco11", "rep3-exec7-rodada1-bloco11", "reforçada"),
    (8, "excluidas/rep3-exec8-rodada1-bloco11", "rep3-exec8-rodada1-bloco11", "reforçada"),
    (9, "excluidas/rep3-exec9-sinc-node3", "rep3-exec9-sinc-node3", "reforçada"),
    (10, "excluidas/rep3-exec10-rodada2-bloco12", "rep3-exec10-rodada2-bloco12", "reforçada"),
]

linhas = []
for n, pasta, diag, deteccao in EXECUCOES:
    d = A / pasta
    rep, log = c.ler_report(d / "report.html"), c.ler_log(d / "caliper.log")
    texto_log = [c.RE_ANSI.sub("", l) for l in (d / "caliper.log").read_text(encoding="utf-8").splitlines()]
    fim = next(l[:23] for l in texto_log if "Benchmark successfully finished" in l)
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})-(\d{2}:\d{2}:\d{2}\.\d{3})", fim)
    fim_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}-03:00"
    texto_diag = (A / "diagnostico" / f"{diag}.txt").read_text(encoding="utf-8")
    veredito = re.search(r"^VEREDITO: (.*)$", texto_diag, re.M).group(1)
    rpc = re.search(r"rpcnode na janela: (.*)$", texto_diag, re.M)
    erros40 = log["rounds"]["tps-40"]["erros"]
    linhas.append({
        "execucao": n,
        "pasta": pasta,
        "inicio": (d / "inicio.txt").read_text().strip(),
        "fim_benchmark": fim_iso,
        "valida": "sim" if veredito.startswith("VÁLIDA") else "não",
        "motivo_invalidez": veredito.partition(" | ")[2],
        "deteccao_item_ii": deteccao,
        "tps10_latencia_media_s": rep["tps-10"]["Avg Latency (s)"],
        "tps20_throughput_tps": rep["tps-20"]["Throughput (TPS)"],
        "tps40_succ": rep["tps-40"]["Succ"],
        "tps40_fail": rep["tps-40"]["Fail"],
        "tps40_fail_nonce_too_distant": sum(v for k, v in erros40.items() if "nonce is too distant" in k),
        "tps40_fail_not_mined": sum(v for k, v in erros40.items() if "not mined" in k),
        "rpcnode_sincronizou_na_janela": rpc.group(1) if rpc else "não verificado",
        "diagnostico": f"diagnostico/{diag}.txt",
    })

with (A / "execucoes.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(linhas[0]))
    w.writeheader()
    w.writerows(linhas)
for l in linhas:
    print(f"{l['execucao']:>2} | {l['inicio'][11:19]} a {l['fim_benchmark'][11:19]} | {l['valida']:3} | "
          f"tps-10 {l['tps10_latencia_media_s']} s | {l['motivo_invalidez'] or '-'}")
