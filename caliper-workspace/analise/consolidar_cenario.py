#!/usr/bin/env python3
"""Consolida as repetições de um cenário de capacidade medido com o Caliper.

Uso, dentro de caliper-workspace/:

    python3 analise/consolidar_cenario.py resultados/B-txpool-ajustado

Lê <cenário>/rep*/report.html e <cenário>/rep*/caliper.log sem alterá-los,
confere se as repetições são comparáveis, grava <cenário>/resumo.csv e imprime
as tabelas em Markdown usadas no EXPERIMENTOS.md. Usa só a biblioteca padrão.

Capacidade estimada = Succ / duração real do round ("Finished round N ... in Y
seconds"). O throughput do Caliper conta sucessos e falhas e, quando há falhas,
superestima a capacidade.
"""

import argparse
import csv
import re
import statistics
import sys
from collections import Counter
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

COLUNAS_CALIPER = ["Name", "Succ", "Fail", "Send Rate (TPS)", "Max Latency (s)",
                   "Min Latency (s)", "Avg Latency (s)", "Throughput (TPS)"]

# métrica no CSV -> coluna da tabela do Caliper
METRICAS_CALIPER = {
    "succ": "Succ",
    "fail": "Fail",
    "send_rate_tps": "Send Rate (TPS)",
    "max_latency_s": "Max Latency (s)",
    "min_latency_s": "Min Latency (s)",
    "avg_latency_s": "Avg Latency (s)",
    "throughput_tps": "Throughput (TPS)",
}

# arquivos que precisam ser idênticos entre as repetições
ARQUIVOS_CONFIG = ["config.yaml", "besu_args.txt", "commit.txt"]

RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")
RE_INICIO = re.compile(r"Started round \d+ \((.+?)\)")
RE_FIM = re.compile(r"Finished round \d+ \((.+?)\) in ([\d.]+) seconds")
RE_CABECALHO_FALHA = re.compile(r"Failed tx on .*?nonce: (0x[0-9a-fA-F]+)")
RE_ERRO = re.compile(r"\bError: (.*)$")
RE_OBSERVADOR = re.compile(r"Round \d+ Transaction Info\] - Submitted: \d+ Succ: (\d+)")
RE_TOTAL = re.compile(r"Total rounds: (\d+)\. Successful rounds: (\d+)\. Failed rounds: (\d+)\.")
RE_LINHA_TABELA = re.compile(r"^\|(.+)\|\s*$")


def ler_report(caminho):
    """Tabela 'Summary of performance metrics' do report.html, por round."""
    html = caminho.read_text(encoding="utf-8")
    inicio = html.index('id="benchmarksummary"')
    bloco = html[inicio:html.index("</table>", inicio)]
    tabela = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", bloco, flags=re.S):
        celulas = [c.strip() for c in re.findall(r"<td>(.*?)</td>", tr)]
        if celulas:
            tabela[celulas[0]] = dict(zip(COLUNAS_CALIPER, celulas))
    return tabela


def novo_round():
    return {"duracao": None, "erros": {}, "nonces": [], "succ_observador": []}


def ler_log(caminho):
    """Duração, falhas por tipo, nonces com falha e Succ do observador por round, mais a tabela final."""
    rounds = {}
    tabela_final = {}
    total = None
    finalizado = False
    na_tabela_final = False
    atual = rounds.setdefault("(fora de round)", novo_round())

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = RE_ANSI.sub("", linha)
        if m := RE_INICIO.search(linha):
            atual = rounds.setdefault(m.group(1), novo_round())
        elif m := RE_FIM.search(linha):
            rounds[m.group(1)]["duracao"] = float(m.group(2))
        elif m := RE_OBSERVADOR.search(linha):
            # relatório periódico do observador (a cada 5 s), com o Succ acumulado
            atual["succ_observador"].append(int(m.group(1)))
        elif m := RE_CABECALHO_FALHA.search(linha):
            # cabeçalho de cada falha: não entra na contagem por tipo
            atual["nonces"].append(int(m.group(1), 16))
        elif m := RE_ERRO.search(linha):
            mensagem = m.group(1).strip()
            atual["erros"][mensagem] = atual["erros"].get(mensagem, 0) + 1
        elif "### All test results ###" in linha:
            na_tabela_final = True
        elif na_tabela_final and (m := RE_LINHA_TABELA.match(linha)):
            celulas = [c.strip() for c in m.group(1).split("|")]
            if celulas[0] != "Name" and set(celulas[0]) != {"-"}:
                tabela_final[celulas[0]] = dict(zip(COLUNAS_CALIPER, celulas))
        elif m := RE_TOTAL.search(linha):
            total = tuple(int(g) for g in m.groups())
        if "Benchmark successfully finished" in linha:
            finalizado = True

    fora = rounds.pop("(fora de round)")
    if fora["erros"] or fora["nonces"]:
        rounds["(fora de round)"] = fora
    return {"rounds": rounds, "tabela_final": tabela_final, "total": total, "finalizado": finalizado}


def conferir(reps, dados):
    """Lista de problemas que impedem comparar as repetições."""
    problemas = []
    base = reps[0]
    for nome in ARQUIVOS_CONFIG:
        for rep in reps[1:]:
            if (rep / nome).read_bytes() != (base / nome).read_bytes():
                problemas.append(f"{rep.name}/{nome} difere de {base.name}/{nome}")

    rounds_base = list(dados[base.name]["report"])
    for rep in reps:
        report, log = dados[rep.name]["report"], dados[rep.name]["log"]
        if not log["finalizado"]:
            problemas.append(f"{rep.name}: caliper.log sem 'Benchmark successfully finished'")
        if log["total"] is None:
            problemas.append(f"{rep.name}: caliper.log sem a linha 'Total rounds'")
        elif log["total"][1] != len(report) or log["total"][2] != 0:
            problemas.append(f"{rep.name}: rounds (total, sucesso, falha) = {log['total']}, "
                             f"report.html tem {len(report)}")
        if list(report) != rounds_base:
            problemas.append(f"{rep.name}: rounds {list(report)} diferentes de {rounds_base}")
        if report != log["tabela_final"]:
            problemas.append(f"{rep.name}: report.html e tabela final do caliper.log divergem")
        if "(fora de round)" in log["rounds"]:
            problemas.append(f"{rep.name}: falhas registradas fora de um round")
        for label, linha in report.items():
            r = log["rounds"].get(label)
            if r is None or r["duracao"] is None:
                problemas.append(f"{rep.name}/{label}: duração do round não encontrada no log")
                continue
            fail = int(linha["Fail"])
            if len(r["nonces"]) != fail or sum(r["erros"].values()) != fail:
                problemas.append(f"{rep.name}/{label}: Fail={fail}, cabeçalhos de falha="
                                 f"{len(r['nonces'])}, linhas 'Error:'={sum(r['erros'].values())}")
    return problemas


def numero(texto):
    return int(texto) if re.fullmatch(r"-?\d+", texto) else float(texto)


def media_desvio(valores):
    """Média e desvio padrão amostral (n - 1); desvio None quando n < 2."""
    media = statistics.mean(valores)
    desvio = statistics.stdev(valores) if len(valores) > 1 else None
    return media, desvio


def consolidar(nomes, dados):
    """Linhas (round, métrica, detalhe, valores por repetição) na ordem dos rounds."""
    linhas = []
    for label in dados[nomes[0]]["report"]:
        metricas = {chave: [numero(dados[r]["report"][label][coluna]) for r in nomes]
                    for chave, coluna in METRICAS_CALIPER.items()}
        metricas["duracao_round_s"] = [dados[r]["log"]["rounds"][label]["duracao"] for r in nomes]
        metricas["capacidade_estimada_tps"] = [
            s / d for s, d in zip(metricas["succ"], metricas["duracao_round_s"])]
        linhas += [(label, chave, "", valores) for chave, valores in metricas.items()]

        mensagens = sorted({msg for r in nomes for msg in dados[r]["log"]["rounds"][label]["erros"]})
        for msg in mensagens:
            linhas.append((label, "falhas_por_tipo", msg,
                           [dados[r]["log"]["rounds"][label]["erros"].get(msg, 0) for r in nomes]))
    return linhas


def gravar_csv(caminho, nomes, linhas):
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["round", "metrica", "detalhe", *nomes, "n", "media", "desvio_padrao"])
        for label, metrica, detalhe, valores in linhas:
            media, desvio = media_desvio(valores)
            w.writerow([label, metrica, detalhe, *valores, len(valores), media,
                        "" if desvio is None else desvio])


def br(valor, casas=2):
    """Número no formato do documento (1.234,56), arredondado metade para o par (NBR 5891)."""
    exato = Decimal(repr(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_EVEN)
    texto = f"{exato:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def br_contagem(valor):
    return br(valor, 0 if float(valor).is_integer() else 2)


def mais_menos(valores, fmt=br):
    media, desvio = media_desvio(valores)
    return fmt(media) if desvio is None else f"{fmt(media)} ± {fmt(desvio)}"


def tabela_md(cabecalho, alinhamento, linhas):
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join(alinhamento) + "|"]
    saida += ["| " + " | ".join(linha) + " |" for linha in linhas]
    return "\n".join(saida)


def imprimir_markdown(nomes, dados, linhas):
    valores = {(label, metrica): v for label, metrica, detalhe, v in linhas if not detalhe}
    rounds = list(dados[nomes[0]]["report"])

    print(f"## Consolidado (n = {len(nomes)}; média ± desvio padrão amostral)\n")
    colunas = [("succ", br_contagem), ("fail", br_contagem), ("avg_latency_s", br),
               ("max_latency_s", br), ("throughput_tps", br), ("capacidade_estimada_tps", br),
               ("duracao_round_s", br)]
    print(tabela_md(
        ["Round", "Succ", "Fail", "Latência média (s)", "Latência máx. (s)",
         "Throughput informado (TPS)", "Capacidade estimada (TPS)", "Duração do round (s)"],
        ["---"] + ["---:"] * len(colunas),
        [[label] + [mais_menos(valores[(label, m)], fmt) for m, fmt in colunas] for label in rounds]))

    print("\n## Falhas por tipo de erro\n")
    linhas_falhas = []
    for label in rounds:
        por_tipo = [(d, v) for lb, m, d, v in linhas if lb == label and m == "falhas_por_tipo"]
        if not por_tipo:
            linhas_falhas.append([label, "nenhuma falha"] + ["0"] * len(nomes))
        for msg, v in por_tipo:
            linhas_falhas.append([label, f"`{msg}`"] + [br_contagem(x) for x in v])
    print(tabela_md(["Round", "Mensagem após `Error:`", *nomes],
                    ["---", "---"] + ["---:"] * len(nomes), linhas_falhas))

    print("\n## Nonces das transações com falha\n")
    for r in nomes:
        for label in rounds:
            nonces = sorted(dados[r]["log"]["rounds"][label]["nonces"])
            if nonces:
                contiguos = nonces == list(range(nonces[0], nonces[-1] + 1))
                print(f"- {r} / {label}: {len(nonces)} falhas, nonces {hex(nonces[0])} "
                      f"({nonces[0]}) a {hex(nonces[-1])} ({nonces[-1]}), "
                      f"contíguos: {'sim' if contiguos else 'não'}")

    print("\n## Incrementos positivos de Succ entre relatórios do observador (a cada 5 s)\n")
    print("Formato: incremento×ocorrências.\n")
    for label in rounds:
        partes = []
        for r in nomes:
            serie = dados[r]["log"]["rounds"][label]["succ_observador"]
            contagem = Counter(b - a for a, b in zip(serie, serie[1:]) if b > a)
            partes.append(f"{r}: " + ", ".join(f"{k}×{v}" for k, v in sorted(contagem.items())))
        print(f"- {label} — " + "; ".join(partes))

    print("\n## Dados por repetição\n")
    for r in nomes:
        print(f"### {r}\n")
        linhas_rep = []
        for label in rounds:
            c = dados[r]["report"][label]
            linhas_rep.append(
                [label, br_contagem(int(c["Succ"])), br_contagem(int(c["Fail"]))]
                + [br(float(c[k])) for k in COLUNAS_CALIPER[3:]]
                + [br(dados[r]["log"]["rounds"][label]["duracao"])])
        print(tabela_md(
            ["Round", "Succ", "Fail", "Send rate (TPS)", "Latência máx. (s)", "Latência mín. (s)",
             "Latência média (s)", "Throughput informado (TPS)", "Duração do round (s)"],
            ["---"] + ["---:"] * 8, linhas_rep))
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cenario", type=Path, help="pasta do cenário, com subpastas rep1, rep2, ...")
    args = parser.parse_args()

    reps = sorted((p for p in args.cenario.iterdir() if p.is_dir() and re.fullmatch(r"rep\d+", p.name)),
                  key=lambda p: int(p.name[3:]))
    if not reps:
        sys.exit(f"nenhuma pasta rep* em {args.cenario}")

    dados = {rep.name: {"report": ler_report(rep / "report.html"), "log": ler_log(rep / "caliper.log")}
             for rep in reps}

    problemas = conferir(reps, dados)
    if problemas:
        print("Repetições não comparáveis; resumo não gerado:", file=sys.stderr)
        for p in problemas:
            print(f"- {p}", file=sys.stderr)
        sys.exit(2)

    nomes = [rep.name for rep in reps]
    linhas = consolidar(nomes, dados)
    destino = args.cenario / "resumo.csv"
    gravar_csv(destino, nomes, linhas)

    print(f"<!-- gerado por analise/consolidar_cenario.py a partir de {args.cenario} -->\n")
    print(f"Conferência: {', '.join(ARQUIVOS_CONFIG)} idênticos em {', '.join(nomes)}; "
          f"todos os logs com 'Benchmark successfully finished' e todos os rounds concluídos.\n")
    imprimir_markdown(nomes, dados, linhas)
    print(f"Resumo gravado em {destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
