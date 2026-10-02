#!/usr/bin/env python3
"""Gera o painel do cenário A em resultados/A-txpool-padrao/painel.html.

Uso, de qualquer pasta:

    python3 caliper-workspace/analise/gerar_painel.py

Lê execucoes.csv, resumo.csv, notas.txt, diagnostico/*.txt e os report.html e
caliper.log de cada execução (rep1/, rep2/ e excluidas/*/), sem alterá-los.
Grava um único HTML autossuficiente: CSS e gráficos SVG embutidos, sem
JavaScript e sem recursos externos. Dado ausente aparece como "sem dado", com o
arquivo que faltou. Usa só a biblioteca padrão.
"""

import csv
import html
import math
import re
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import consolidar_cenario as c  # noqa: E402

WS = AQUI.parent
RAIZ = WS.parent
A = WS / "resultados" / "A-txpool-padrao"
SAIDA = A / "painel.html"
COMMIT_DADOS = "30d086e"
ROUNDS = ["tps-10", "tps-20", "tps-40"]
SEM_DADO = "sem dado"
RE_HORA_LOG = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})-(\d{2}):(\d{2}):(\d{2})\.(\d{3})")

faltas = []  # (execução ou seção, caminho)


def rel(p):
    return str(Path(p).resolve().relative_to(RAIZ))


def e(texto):
    return html.escape(str(texto), quote=True)


def ler(p, leitor, dono):
    if not p.exists():
        faltas.append((dono, rel(p)))
        return None
    return leitor(p)


def sem_dado(p):
    return f'<span class="sem-dado">{SEM_DADO} (faltou: {e(rel(p))})</span>'


def num(texto):
    """Número do Caliper ('15.4') no formato do documento ('15,4'), sem mudar a precisão."""
    return str(texto).replace(".", ",")


# ---------------------------------------------------------------- leitura

def ler_csv(p):
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ler_tempos_log(p):
    """Início e fim de cada round, pelos carimbos de hora do caliper.log."""
    inicios, fins = {}, {}
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = c.RE_ANSI.sub("", linha)
        m = RE_HORA_LOG.match(linha)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        t = datetime(*g[:6], g[6] * 1000)
        if r := c.RE_INICIO.search(linha):
            inicios.setdefault(r.group(1), t)
        elif r := c.RE_FIM.search(linha):
            fins.setdefault(r.group(1), t)
    return {"inicios": inicios, "fins": fins}


def ler_diag(p):
    """Tabela 'Blocos da janela' e veredito de um diagnostico/*.txt."""
    texto = p.read_text(encoding="utf-8")
    blocos, na_tabela = [], False
    for linha in texto.splitlines():
        if linha.startswith("bloco | hora"):
            na_tabela = True
            continue
        partes = [x.strip() for x in linha.split("|")]
        if na_tabela and len(partes) == 8 and partes[0].isdigit():
            n, hora, rnd, delta, txs, gas, rodada, proposer = partes
            blocos.append({"n": int(n), "hora": hora, "round": rnd, "delta": float(delta),
                           "txs": int(txs), "gas": gas, "rodada": int(rodada), "proposer": proposer})
    m = re.search(r"^VEREDITO: (.*)$", texto, re.M)
    return {"blocos": blocos, "veredito": m.group(1) if m else None}


def ler_config(p):
    texto = p.read_text(encoding="utf-8")
    workers = re.search(r"number:\s*(\d+)", texto)
    rounds = re.findall(r"label:\s*(\S+)\s+txDuration:\s*(\d+).*?tps:\s*(\d+)", texto, re.S)
    return {"workers": workers.group(1) if workers else None, "rounds": rounds}


def carregar():
    p_exec = A / "execucoes.csv"
    if not p_exec.exists():
        sys.exit(f"faltou {rel(p_exec)}: sem ele não há como mapear as execuções")
    execucoes = []
    for linha in ler_csv(p_exec):
        n = int(linha["execucao"])
        pasta = A / linha["pasta"]
        dono = f"execução {n}"
        execucoes.append({
            "n": n, "csv": linha, "pasta": pasta,
            "valida": linha["valida"] == "sim",
            "report": ler(pasta / "report.html", c.ler_report, dono),
            "tempos": ler(pasta / "caliper.log", ler_tempos_log, dono),
            "p_diag": A / linha["diagnostico"],
            "diag": ler(A / linha["diagnostico"], ler_diag, dono),
        })
    resumo_l = ler(A / "resumo.csv", ler_csv, "resumo")
    resumo = {(l["round"], l["metrica"], l["detalhe"]): l for l in resumo_l} if resumo_l else None
    notas = ler(A / "notas.txt", lambda p: p.read_text(encoding="utf-8"), "notas")
    validas = [x for x in execucoes if x["valida"]]
    config = ler(validas[0]["pasta"] / "config.yaml", ler_config, "config") if validas else None
    commit_bench = ler(validas[0]["pasta"] / "commit.txt", lambda p: p.read_text().strip(), "commit") \
        if validas else None
    return execucoes, resumo, notas, config, commit_bench


# ---------------------------------------------------------------- textos derivados

def criterio(notas):
    if not notas:
        return None
    m = re.search(r"Critério de validade.*?\n\s*\"(.*?)\"", notas, re.S)
    return " ".join(m.group(1).split()) if m else None


def causas(motivo):
    """Veredito do diagnóstico em linguagem corrente; parte não reconhecida sai como está."""
    itens = []
    for parte in filter(None, motivo.split(" | ")):
        if m := re.match(r"\(i\) blocos em rodada > 0: (.*)", parte):
            ns = m.group(1)
            plural = "," in ns
            itens.append(f"Troca de rodada: {'os blocos' if plural else 'o bloco'} {ns} só "
                         f"{'foram fechados' if plural else 'foi fechado'} depois que o proponente da vez falhou")
        elif m := re.match(r"\(ii\) importação por sincronização: (.*)", parte):
            trechos = []
            for nome, a, b, qtd in re.findall(r"(node\d) #(\d+) a #(\d+) \((\d+)\)", m.group(1)):
                trechos.append(f"{nome}, bloco {a}" if a == b else f"{nome}, blocos {a} a {b} ({qtd})")
            itens.append("Validador recebeu blocos por sincronização em vez de pelo consenso: "
                         + ("; ".join(trechos) or m.group(1)))
        elif m := re.match(r"\(ii\) 'while we are syncing': (.*)", parte):
            txt = m.group(1).replace(" parou (while we are syncing)", "")
            itens.append(f"Validador ficou para trás e entrou em sincronização: {txt}")
        else:
            itens.append(parte)
    return itens


def blocos_vazios_no_meio(diag, rnd):
    """Blocos sem transação entre o primeiro e o último bloco com transação de um round."""
    sel = [b for b in diag["blocos"] if b["round"] == rnd]
    cheios = [i for i, b in enumerate(sel) if b["txs"] > 0]
    if not cheios:
        return []
    return [b["n"] for b in sel[cheios[0]:cheios[-1] + 1] if b["txs"] == 0]


# ---------------------------------------------------------------- SVG

def passos(vmax, alvo=5):
    bruto = vmax / alvo
    mag = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        passo = m * mag
        if vmax / passo <= alvo:
            break
    topo = math.ceil(vmax / passo - 1e-9) * passo
    return [round(i * passo, 6) for i in range(int(round(topo / passo)) + 1)]


def fmt_tick(v):
    return str(int(v)) if float(v).is_integer() else c.br(v, 1)


def coluna(x, y, w, h, r=4):
    """Coluna com topo arredondado (4 px) e base reta."""
    r = min(r, w / 2, h)
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} A{r},{r} 0 0 1 {x + r:.1f},{y:.1f} "
            f"H{x + w - r:.1f} A{r},{r} 0 0 1 {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")


def grafico_colunas(execucoes, rnd, coluna_csv, unidade, titulo_eixo, rotular):
    """Uma coluna por execução; válidas em verde, excluídas em cinza."""
    W, H, ml, mr, mt, mb = 720, 300, 52, 16, 28, 58
    pw, ph = W - ml - mr, H - mt - mb
    dados = []
    for x in execucoes:
        v = x["report"][rnd][coluna_csv] if x["report"] and rnd in x["report"] else None
        dados.append((x, float(v) if v is not None else None, v))
    validos = [v for _, v, _ in dados if v is not None]
    ticks = passos(max(validos)) if validos else [0, 1]
    topo = ticks[-1]
    banda = pw / len(dados)
    bw = min(24, banda * 0.5)
    sy = lambda v: mt + ph - v / topo * ph  # noqa: E731
    out = [f'<svg class="colunas" viewBox="0 0 {W} {H}" role="img" aria-label="{e(titulo_eixo)} por execução">']
    for t in ticks:
        y = sy(t)
        out.append(f'<line class="grade" x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt_tick(t)}</text>')
    out.append(f'<line class="eixo" x1="{ml}" x2="{W - mr}" y1="{mt + ph}" y2="{mt + ph}"/>')
    out.append(f'<text class="rotulo-eixo" x="{ml - 40}" y="{mt - 12}">{e(titulo_eixo)}</text>')
    for i, (x, v, bruto) in enumerate(dados):
        cx = ml + banda * i + banda / 2
        sub = x["pasta"].name if x["valida"] else ""
        out.append(f'<text class="tick" x="{cx:.1f}" y="{mt + ph + 18}" text-anchor="middle">{x["n"]}</text>')
        if sub:
            out.append(f'<text class="sub-tick" x="{cx:.1f}" y="{mt + ph + 33}" text-anchor="middle">{e(sub)}</text>')
        if v is None:
            out.append(f'<text class="sem-dado-svg" x="{cx:.1f}" y="{mt + ph - 6}" text-anchor="middle">{SEM_DADO}</text>')
            continue
        y = sy(v)
        classe = "m-valida" if x["valida"] else "m-excluida"
        situacao = "válida" if x["valida"] else "excluída"
        out.append(f'<g><title>Execução {x["n"]} ({situacao}): {num(bruto)} {unidade}</title>'
                   f'<rect class="alvo" x="{cx - banda / 2 + 2:.1f}" y="{mt}" width="{banda - 4:.1f}" height="{ph}"/>'
                   f'<path class="{classe}" d="{coluna(cx - bw / 2, y, bw, mt + ph - y)}"/></g>')
        if rotular(x, v, validos):
            out.append(f'<text class="valor" x="{cx:.1f}" y="{y - 7:.1f}" text-anchor="middle">{num(bruto)}</text>')
    out.append(f'<text class="rotulo-eixo" x="{ml + pw / 2:.1f}" y="{H - 6}" text-anchor="middle">execução</text>')
    out.append("</svg>")
    return "\n".join(out), [(x, v) for x, v, _ in dados]


def faixas(execucoes):
    """Uma faixa por execução: blocos no tempo (altura = transações), intervalos > 2 s e rodada > 0."""
    linhas = []
    for x in execucoes:
        d, t = x["diag"], x["tempos"]
        if not d or not t or "tps-10" not in t["inicios"] or not d["blocos"]:
            linhas.append((x, None))
            continue
        dia = x["csv"]["inicio"][:10]
        t0 = t["inicios"]["tps-10"]
        blocos = []
        for b in d["blocos"]:
            tb = datetime.fromisoformat(f"{dia}T{b['hora']}")
            blocos.append({**b, "t": (tb - t0).total_seconds()})
        rounds = {r: ((t["inicios"][r] - t0).total_seconds(), (t["fins"][r] - t0).total_seconds())
                  for r in ROUNDS if r in t["inicios"] and r in t["fins"]}
        linhas.append((x, {"blocos": blocos, "rounds": rounds}))
    com_dado = [v for _, v in linhas if v]
    if not com_dado:
        return "<p>" + SEM_DADO + "</p>"
    tmin = min(b["t"] - b["delta"] for v in com_dado for b in v["blocos"])
    tmax = max(max(b["t"] for b in v["blocos"]) for v in com_dado)
    x0, x1 = math.floor(tmin / 10) * 10, math.ceil(tmax / 20) * 20
    txmax = max(b["txs"] for v in com_dado for b in v["blocos"]) or 1
    W, L, R, RH, top = 1000, 168, 16, 88, 8
    pw = W - L - R
    sx = lambda s: L + (s - x0) / (x1 - x0) * pw  # noqa: E731
    H = top + RH * len(linhas) + 44
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Intervalos entre blocos por execução">']
    tick_passo = 20
    for s in range(int(x0) - int(x0) % tick_passo, int(x1) + 1, tick_passo):
        if s < x0:
            continue
        out.append(f'<line class="grade" x1="{sx(s):.1f}" x2="{sx(s):.1f}" y1="{top}" y2="{top + RH * len(linhas)}"/>')
        out.append(f'<text class="tick" x="{sx(s):.1f}" y="{top + RH * len(linhas) + 16}" text-anchor="middle">{s}</text>')
    out.append(f'<text class="rotulo-eixo" x="{L + pw / 2:.1f}" y="{H - 6}" text-anchor="middle">'
               f'segundos desde o início do round tps-10</text>')
    for i, (x, v) in enumerate(linhas):
        y0 = top + RH * i
        base = y0 + RH - 16
        alto = RH - 48
        y_round, y_rodada = y0 + 12, y0 + 25
        situacao = f"válida · {x['pasta'].name}" if x["valida"] else "excluída"
        marca = "m-valida" if x["valida"] else "m-excluida"
        out.append(f'<rect class="{marca}" x="0" y="{y0 + 12}" width="8" height="8" rx="2"/>')
        out.append(f'<text class="rotulo-linha" x="14" y="{y0 + 21}">Execução {x["n"]}</text>')
        out.append(f'<text class="sub-linha" x="14" y="{y0 + 37}">{e(situacao)}</text>')
        out.append(f'<line class="eixo" x1="{L}" x2="{W - R}" y1="{base}" y2="{base}"/>')
        if not v:
            p = x["p_diag"] if not x["diag"] else x["pasta"] / "caliper.log"
            out.append(f'<text class="sem-dado-svg" x="{L + 8}" y="{base - 10}">{SEM_DADO} (faltou: {e(rel(p))})</text>')
            continue
        for r, (ini, fim) in v["rounds"].items():
            out.append(f'<rect class="lavagem-round" x="{sx(ini):.1f}" y="{y_round + 4}" '
                       f'width="{sx(fim) - sx(ini):.1f}" height="{base - y_round - 4}"/>')
            out.append(f'<line class="inicio-round" x1="{sx(ini):.1f}" x2="{sx(ini):.1f}" y1="{y_round - 8}" y2="{base}"/>')
            out.append(f'<text class="rotulo-round" x="{sx(ini) + 3:.1f}" y="{y_round}">{r}</text>')
        for b in v["blocos"]:
            if b["delta"] > 2:
                xa, xb = sx(b["t"] - b["delta"]), sx(b["t"])
                out.append(f'<rect class="m-intervalo" x="{xa:.1f}" y="{base - alto}" width="{xb - xa:.1f}" height="{alto}"/>')
                out.append(f'<text class="valor-pequeno" x="{(xa + xb) / 2:.1f}" y="{base + 11}" '
                           f'text-anchor="middle">{b["delta"]:.0f} s</text>')
        for b in v["blocos"]:
            xb = sx(b["t"])
            h = b["txs"] / txmax * alto
            dica = (f"Bloco {b['n']} · {b['hora']} · {b['round']} · {b['delta']:.0f} s após o anterior · "
                    f"{b['txs']} transações · rodada {b['rodada']} · proposto por {b['proposer']}")
            partes = [f'<g><title>{e(dica)}</title>',
                      f'<rect class="alvo" x="{xb - 3:.1f}" y="{y_rodada - 8}" width="6" height="{base - y_rodada + 8}"/>']
            if b["txs"] > 0:
                partes.append(f'<rect class="m-txs" x="{xb - 1.25:.1f}" y="{base - h:.1f}" width="2.5" height="{h:.1f}"/>')
            else:
                partes.append(f'<rect class="m-vazio" x="{xb - 1.25:.1f}" y="{base - 2.5:.1f}" width="2.5" height="2.5"/>')
            if b["rodada"] > 0:
                yy = y_rodada
                partes.append(f'<path class="m-rodada" d="M{xb:.1f},{yy - 6:.1f} L{xb + 6:.1f},{yy:.1f} '
                              f'L{xb:.1f},{yy + 6:.1f} L{xb - 6:.1f},{yy:.1f} Z"/>')
            partes.append("</g>")
            out.append("".join(partes))
            if b["rodada"] > 0:
                out.append(f'<text class="valor-pequeno" x="{xb + 8:.1f}" y="{y_rodada + 4:.1f}">R{b["rodada"]}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- HTML

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --wash: #f0efec;
  --valida: #0ca30c; --valida-texto: #006300; --excluida: #898781;
  --txs: #2a78d6; --intervalo: #ec835a; --rodada: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: #242422;
    --valida-texto: #0ca30c; --excluida: #77766f; --txs: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: #242422;
  --valida-texto: #0ca30c; --excluida: #77766f; --txs: #3987e5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 26px; line-height: 1.25; margin: 0 0 6px; font-weight: 650; }
h2 { font-size: 19px; margin: 0 0 4px; font-weight: 620; }
h3 { font-size: 15px; margin: 18px 0 6px; font-weight: 620; }
p { margin: 6px 0; }
.lead { color: var(--ink-2); margin: 0 0 24px; max-width: 72ch; }
.cartao { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 22px; margin: 0 0 20px; }
.nota { color: var(--ink-2); font-size: 13.5px; max-width: 80ch; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 14px 0 16px; }
.kpi { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.kpi .rotulo { color: var(--ink-2); font-size: 13px; }
.kpi .valor { font-size: 30px; font-weight: 650; line-height: 1.2; }
.criterio { border-left: 3px solid var(--axis); padding: 4px 0 4px 12px; margin: 10px 0; max-width: 80ch; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; font-size: 13px; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tbody tr.inicio-exec td { border-top: 1px solid var(--axis); }
.rolagem { overflow-x: auto; }
.rolagem > svg { min-width: 640px; }
.rolagem > svg.colunas { max-width: 760px; }
.rolagem.largo > svg { min-width: 820px; }
svg { display: block; width: 100%; height: auto; }
.grade { stroke: var(--grid); stroke-width: 1; }
.eixo { stroke: var(--axis); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.sub-tick { fill: var(--ink-2); font-size: 11.5px; font-weight: 600; }
.rotulo-eixo { fill: var(--ink-2); font-size: 12.5px; }
.valor { fill: var(--ink); font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
.valor-pequeno { fill: var(--ink-2); font-size: 11px; }
.rotulo-linha { fill: var(--ink); font-size: 13px; font-weight: 600; }
.sub-linha { fill: var(--ink-2); font-size: 12px; }
.rotulo-round { fill: var(--ink-2); font-size: 10.5px; }
.sem-dado-svg { fill: var(--ink-2); font-size: 12px; font-style: italic; }
.alvo { fill: transparent; }
.m-valida { fill: var(--valida); }
.m-excluida { fill: var(--excluida); }
.m-txs { fill: var(--txs); }
.m-vazio { fill: var(--muted); }
.m-intervalo { fill: var(--intervalo); opacity: 0.35; }
.m-rodada { fill: var(--rodada); stroke: var(--surface); stroke-width: 2; }
.lavagem-round { fill: var(--wash); }
.inicio-round { stroke: var(--axis); stroke-width: 1; }
.legenda { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 10px 0 4px; font-size: 13px; color: var(--ink-2); }
.legenda span { display: inline-flex; align-items: center; gap: 6px; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.sw.valida { background: var(--valida); } .sw.excluida { background: var(--excluida); }
.sw.txs { background: var(--txs); width: 3px; height: 14px; border-radius: 1px; }
.sw.intervalo { background: var(--intervalo); opacity: 0.35; width: 18px; }
.sw.rodada { background: var(--rodada); width: 10px; height: 10px; transform: rotate(45deg); border-radius: 1px; }
.sw.vazio { background: var(--muted); width: 4px; height: 4px; border-radius: 0; }
.linha-tempo { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-top: 12px; }
.exec { border: 1px solid var(--border); border-left: 4px solid var(--excluida); border-radius: 10px;
  padding: 10px 12px; font-size: 13.5px; }
.exec.valida { border-left-color: var(--valida); }
.exec .cab { display: flex; flex-direction: column; gap: 0; }
.exec .num { font-weight: 650; }
.exec .hora { color: var(--ink-2); font-variant-numeric: tabular-nums; font-size: 12.5px; }
.exec .situacao { font-weight: 600; margin: 4px 0; }
.exec.valida .situacao { color: var(--valida-texto); }
.exec.excluida .situacao { color: var(--ink-2); }
.exec ul { margin: 4px 0 0; padding-left: 16px; color: var(--ink-2); }
.exec li { margin: 2px 0; }
.sem-dado { color: var(--ink-2); font-style: italic; }
footer { color: var(--ink-2); font-size: 13px; }
footer code { font-size: 12.5px; }
footer li { margin: 3px 0; }
"""


def bloco_resumo(execucoes, resumo, notas, config):
    total = len(execucoes)
    validas = [x for x in execucoes if x["valida"]]
    crit = criterio(notas)
    validadores = sorted({b["proposer"] for x in execucoes if x["diag"] for b in x["diag"]["blocos"]})
    partes = ['<section class="cartao" id="resumo"><h2>1. Resumo</h2>']
    contexto = []
    if config:
        rounds = ", ".join(f"{lb} ({tps} TPS por {dur} s)" for lb, dur, tps in config["rounds"])
        contexto.append(f"{config['workers']} worker do Caliper; rounds {rounds}, em taxa fixa")
    if validadores:
        contexto.append(f"{len(validadores)} validadores QBFT ({', '.join(validadores)}) e 1 rpcnode, que recebe as transações")
    partes.append("<p>Cada execução reinicia a rede do zero e roda o mesmo benchmark: "
                  + e("; ".join(contexto)) + ".</p>")
    partes.append('<div class="kpis">'
                  f'<div class="kpi"><div class="rotulo">Execuções</div><div class="valor">{total}</div></div>'
                  f'<div class="kpi"><div class="rotulo">Válidas (entram na Tabela II)</div><div class="valor">{len(validas)}</div></div>'
                  f'<div class="kpi"><div class="rotulo">Excluídas</div><div class="valor">{total - len(validas)}</div></div>'
                  "</div>")
    partes.append("<p><strong>Critério de validade</strong>, definido antes das novas repetições e "
                  "aplicado a todas as execuções:</p>")
    partes.append(f'<p class="criterio">{e(crit) if crit else sem_dado(A / "notas.txt")}</p>')
    antigas = [x["n"] for x in execucoes if x["csv"].get("deteccao_item_ii", "").startswith("só PersistBlockTask")]
    if antigas:
        partes.append('<p class="nota">Detecção do item (ii): além de PersistBlockTask, conta também a linha '
                      '"Stopping BFT mining coordinator while we are syncing" no log do validador, uma melhoria na '
                      "detecção do mesmo item, sem mudar o critério. As execuções "
                      + e(", ".join(map(str, antigas))) + " foram verificadas antes dessa melhoria "
                      "(coluna deteccao_item_ii de execucoes.csv).</p>")
    partes.append('<p class="nota">Em linguagem corrente: a medição só vale se o consenso funcionou normalmente '
                  "do começo ao fim. <em>Rodada maior que 0</em> significa que o validador da vez não conseguiu "
                  "fechar o bloco no prazo e o consenso passou a vez a outro; <em>sincronização</em> significa que "
                  "um validador ficou para trás e precisou baixar blocos em vez de participar do consenso.</p>")
    if not resumo:
        partes.append(f"<p>Tabela II: {sem_dado(A / 'resumo.csv')}</p></section>")
        return "\n".join(partes)
    n = resumo[("tps-10", "succ", "")]["n"]
    nomes = [k for k in resumo[("tps-10", "succ", "")] if re.fullmatch(r"rep\d+", k)]
    partes.append(f'<h3>Tabela II, cenário A: n = {e(n)} ({", ".join(nomes)}), média ± desvio padrão amostral</h3>')
    cols = [("succ", "Succ", True), ("fail", "Fail", True), ("avg_latency_s", "Latência média (s)", False),
            ("throughput_tps", "Throughput (TPS)", False), ("capacidade_estimada_tps", "Capacidade estimada (TPS)", False)]
    partes.append('<div class="rolagem"><table><thead><tr><th>Round</th>'
                  + "".join(f'<th class="n">{e(t)}</th>' for _, t, _ in cols) + "</tr></thead><tbody>")
    for rnd in ROUNDS:
        celulas = []
        for chave, _, contagem in cols:
            l = resumo.get((rnd, chave, ""))
            if not l:
                celulas.append(f'<td class="n">{SEM_DADO}</td>')
                continue
            fmt = c.br_contagem if contagem else c.br
            media = fmt(float(l["media"]))
            desvio = fmt(float(l["desvio_padrao"])) if l["desvio_padrao"] else None
            celulas.append(f'<td class="n">{media}{" ± " + desvio if desvio else ""}</td>')
        partes.append(f"<tr><td>{rnd}</td>{''.join(celulas)}</tr>")
    partes.append("</tbody></table></div>")
    # notas derivadas dos próprios arquivos
    rej = []
    for r in nomes:
        s, f = int(resumo[("tps-40", "succ", "")][r]), int(resumo[("tps-40", "fail", "")][r])
        rej.append(f"{c.br(100 * f / (s + f))}% na {r} ({f} de {s + f})")
    partes.append(f'<p class="nota">Rejeição no tps-40 (falhas ÷ transações enviadas): {"; ".join(rej)}.</p>')
    dur = resumo.get(("tps-40", "duracao_round_s", ""))
    nm = [l for k, l in resumo.items() if k[0] == "tps-40" and k[1] == "falhas_por_tipo" and "not mined" in k[2]]
    if dur:
        txt = "; ".join(f"{c.br(float(dur[r]))} s na {r}" for r in nomes)
        extra = ""
        if nm:
            extra = " A diferença vem das transações que o Caliper esperou por 50 blocos e não foram mineradas (" + \
                    "; ".join(f"{nm[0][r]} na {r}" for r in nomes) + ")."
        partes.append(f'<p class="nota">No tps-40, o throughput informado e a capacidade estimada dependem da duração '
                      f'do round: {txt}.{extra}</p>')
    lat = resumo.get(("tps-10", "avg_latency_s", ""))
    rpc = [x for x in validas if "parou" in x["csv"].get("rpcnode_sincronizou_na_janela", "")]
    if lat and rpc:
        x = rpc[0]
        vazios = blocos_vazios_no_meio(x["diag"], "tps-10") if x["diag"] else []
        hora = x["csv"]["rpcnode_sincronizou_na_janela"].split(" ")[0]
        partes.append(f'<p class="nota">O desvio da latência do tps-10 vem da {x["pasta"].name} '
                      f'({num(lat[x["pasta"].name])} s, contra '
                      + ", ".join(f"{num(lat[r])} s na {r}" for r in nomes if r != x["pasta"].name)
                      + f'): nela o rpcnode, que não é validador e por isso fica fora do critério, ficou para trás às '
                      f'{e(hora)}' + (f' e {len(vazios)} blocos saíram vazios ({", ".join(map(str, vazios))})'
                                      if vazios else "") + f' (execução {x["n"]}).</p>')
    partes.append("</section>")
    return "\n".join(partes)


def bloco_linha_tempo(execucoes):
    dias = sorted({x["csv"]["inicio"][:10] for x in execucoes})
    dias_txt = ", ".join(datetime.fromisoformat(d).strftime("%d/%m/%Y") for d in dias)
    out = ['<section class="cartao" id="linha-do-tempo"><h2>2. Linha do tempo das execuções</h2>',
           f'<p class="nota">Todas em {e(dias_txt)}. Horário de início (inicio.txt) e de fim do benchmark '
           "(\"Benchmark successfully finished\" no caliper.log).</p>",
           '<div class="legenda"><span><i class="sw valida"></i>✓ válida</span>'
           '<span><i class="sw excluida"></i>✕ excluída</span></div>',
           '<div class="linha-tempo">']
    for x in execucoes:
        l = x["csv"]
        ini, fim = l["inicio"][11:19], l["fim_benchmark"][11:19]
        classe = "valida" if x["valida"] else "excluida"
        situacao = f"✓ válida → {x['pasta'].name}" if x["valida"] else "✕ excluída"
        out.append(f'<div class="exec {classe}"><div class="cab"><span class="num">Execução {x["n"]}</span>'
                   f'<span class="hora">{e(ini)}–{e(fim)}</span></div>'
                   f'<div class="situacao">{e(situacao)}</div>')
        itens = causas(l["motivo_invalidez"]) if l["motivo_invalidez"] else []
        rpc = l.get("rpcnode_sincronizou_na_janela", "")
        if x["valida"] and "parou" in rpc:
            itens.append(f"Observação, fora do critério: o rpcnode ficou para trás às {rpc.split(' ')[0]}")
        if itens:
            out.append("<ul>" + "".join(f"<li>{e(i)}</li>" for i in itens) + "</ul>")
        out.append("</div>")
    out.append("</div></section>")
    return "\n".join(out)


def bloco_grafico(numero, titulo, svg, legenda_nota):
    return (f'<section class="cartao"><h2>{numero}. {e(titulo)}</h2>'
            '<div class="legenda"><span><i class="sw valida"></i>válida (entra na Tabela II)</span>'
            '<span><i class="sw excluida"></i>excluída</span></div>'
            f'<div class="rolagem">{svg}</div><p class="nota">{legenda_nota}</p></section>')


def nota_tps20(pares):
    vals = [(x, v) for x, v in pares if v is not None]
    if not vals:
        return SEM_DADO
    vmin, vmax = min(v for _, v in vals), max(v for _, v in vals)
    em = lambda alvo: ", ".join(str(x["n"]) for x, v in vals if v == alvo)  # noqa: E731
    faltam = [x["n"] for x, v in pares if v is None]
    txt = (f"As {len(vals)} execuções ficaram entre {num(vmin)} e {num(vmax)} TPS (mínimo na execução {em(vmin)}; "
           f"máximo na execução {em(vmax)}), inclusive as excluídas: a variação entre execuções é de "
           f"{c.br(vmax - vmin, 1)} TPS. O transitório do início da carga não alterou o tps-20.")
    if faltam:
        txt += f" Sem dado nas execuções {', '.join(map(str, faltam))}."
    return e(txt)


def nota_tps10(pares, execucoes):
    vals = [(x, v) for x, v in pares if v is not None]
    if not vals:
        return SEM_DADO
    vmin, vmax = min(v for _, v in vals), max(v for _, v in vals)
    xmax = next(x for x, v in vals if v == vmax)
    validas = "; ".join(f"{num(v)} s na {x['pasta'].name}" for x, v in vals if x["valida"])
    anomalos = [b for x in execucoes if x["diag"] for b in x["diag"]["blocos"] if b["rodada"] > 0 or b["delta"] > 2]
    rounds = sorted({b["round"] for b in anomalos})
    onde = (f"Nas {sum(1 for x in execucoes if x['diag'])} execuções com diagnóstico, todos os {len(anomalos)} blocos "
            f"com intervalo maior que 2 s ou em rodada maior que 0 caíram no {rounds[0]}." if len(rounds) == 1
            else f"Blocos com intervalo maior que 2 s ou em rodada maior que 0 aparecem em: {', '.join(rounds)}.")
    return e(f"A latência média do tps-10 vai de {num(vmin)} s a {num(vmax)} s (execução {xmax['n']}). {onde} "
             f"Válidas: {validas}.")


def bloco_faixas(execucoes):
    return ('<section class="cartao" id="faixas"><h2>5. Blocos durante os rounds, por execução</h2>'
            '<p class="nota">Cada marca vertical é um bloco, na hora em que foi produzido; a altura é o número de '
            "transações do bloco. O período esperado entre blocos é de 2 s. As áreas cinza-claras são os rounds; "
            "a linha no início de cada área marca o começo do round. Passe o mouse sobre um bloco para ver os "
            "detalhes. Fonte: tabela \"Blocos da janela\" de cada diagnostico/*.txt e horários de início e fim "
            "dos rounds no caliper.log.</p>"
            '<div class="legenda"><span><i class="sw txs"></i>bloco com transações</span>'
            '<span><i class="sw vazio"></i>bloco vazio</span>'
            '<span><i class="sw intervalo"></i>intervalo maior que 2 s (com a duração embaixo)</span>'
            '<span><i class="sw rodada"></i>bloco fechado em rodada maior que 0 (R1, R2 = número da rodada)</span></div>'
            f'<div class="rolagem largo">{faixas(execucoes)}</div></section>')


def bloco_tabela(execucoes):
    cab = ["Execução", "Situação", "Round", "Succ", "Fail", "Latência média (s)", "Latência máx. (s)", "Throughput (TPS)"]
    out = ['<section class="cartao" id="tabela"><h2>6. Tabela completa por execução e round</h2>',
           '<p class="nota">Valores da tabela "Summary of performance metrics" do report.html de cada execução, '
           "sem arredondamento adicional. O throughput é o informado pelo Caliper, que conta sucessos e falhas.</p>",
           '<div class="rolagem"><table><thead><tr>'
           + "".join(f'<th{" class=n" if i >= 3 else ""}>{e(t)}</th>' for i, t in enumerate(cab))
           + "</tr></thead><tbody>"]
    for x in execucoes:
        situacao = f"válida ({x['pasta'].name})" if x["valida"] else "excluída"
        rep = x["report"]
        for j, rnd in enumerate(ROUNDS):
            classe = ' class="inicio-exec"' if j == 0 else ""
            cel = [f'<td rowspan="3">{x["n"]}</td><td rowspan="3">{e(situacao)}</td>' if j == 0 else ""]
            cel.append(f"<td>{rnd}</td>")
            if rep is None or rnd not in rep:
                cel.append(f'<td colspan="5">{sem_dado(x["pasta"] / "report.html")}</td>')
            else:
                v = rep[rnd]
                for k in ("Succ", "Fail", "Avg Latency (s)", "Max Latency (s)", "Throughput (TPS)"):
                    cel.append(f'<td class="n">{e(num(v[k]))}</td>')
            out.append(f"<tr{classe}>{''.join(cel)}</tr>")
    out.append("</tbody></table></div></section>")
    return "\n".join(out)


def bloco_fontes(execucoes, commit_bench):
    base = rel(A)
    li = [
        f"<li>Resumo e Tabela II: <code>{base}/resumo.csv</code> (gerado por <code>caliper-workspace/analise/"
        "consolidar_cenario.py</code> a partir de rep1/ e rep2/); critério de validade: "
        f"<code>{base}/notas.txt</code>.</li>",
        f"<li>Linha do tempo (horários, situação e causa): <code>{base}/execucoes.csv</code>, que reúne "
        "inicio.txt, caliper.log e o veredito de cada diagnóstico.</li>",
        "<li>Gráficos 3 e 4 e tabela 6: report.html de cada execução: "
        + ", ".join(f"<code>{e(rel(x['pasta'] / 'report.html'))}</code>" for x in execucoes) + ".</li>",
        "<li>Faixas de blocos (5): " + ", ".join(f"<code>{e(rel(x['p_diag']))}</code>" for x in execucoes)
        + "; início e fim dos rounds no caliper.log de cada pasta acima.</li>",
    ]
    if faltas:
        li.append("<li>Arquivos ausentes: " + "; ".join(f"{e(d)}: <code>{e(p)}</code>" for d, p in faltas) + ".</li>")
    else:
        li.append("<li>Nenhum arquivo esperado estava ausente.</li>")
    gerado = datetime.now().astimezone().isoformat(timespec="seconds")
    return ('<footer class="cartao" id="fontes"><h2>7. De onde vêm os dados</h2><ul>' + "".join(li) + "</ul>"
            f"<p>Dados do commit <code>{COMMIT_DADOS}</code>. Benchmarks executados no commit "
            f"<code>{e(commit_bench) if commit_bench else SEM_DADO}</code> (commit.txt). "
            f"Painel gerado por <code>caliper-workspace/analise/gerar_painel.py</code> em {e(gerado)}.</p></footer>")


def main():
    execucoes, resumo, notas, config, commit_bench = carregar()
    svg20, pares20 = grafico_colunas(
        execucoes, "tps-20", "Throughput (TPS)", "TPS", "Throughput (TPS)",
        lambda x, v, todos: x["valida"] or v in (min(todos), max(todos)))
    svg10, pares10 = grafico_colunas(
        execucoes, "tps-10", "Avg Latency (s)", "s", "Latência média (s)",
        lambda x, v, todos: x["valida"] or v == max(todos))
    corpo = [
        "<header><h1>Cenário A (txpool padrão do Besu): repetições do benchmark</h1>",
        '<p class="lead">Painel das execuções que sustentam a Tabela II. Verde marca as execuções válidas, usadas na '
        "tabela; cinza marca as excluídas pelo critério de validade. Todos os números vêm dos arquivos listados no "
        "rodapé.</p></header>",
        bloco_resumo(execucoes, resumo, notas, config),
        bloco_linha_tempo(execucoes),
        bloco_grafico(3, "Throughput do tps-20 em cada execução", svg20, nota_tps20(pares20)),
        bloco_grafico(4, "Latência média do tps-10 em cada execução", svg10, nota_tps10(pares10, execucoes)),
        bloco_faixas(execucoes),
        bloco_tabela(execucoes),
        bloco_fontes(execucoes, commit_bench),
    ]
    pagina = ("<!doctype html>\n<html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
              "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
              "<title>Painel do cenário A</title>"
              f"<style>{CSS}</style></head><body><main>\n" + "\n".join(corpo) + "\n</main></body></html>\n")
    SAIDA.write_text(pagina, encoding="utf-8")
    print(f"painel gravado em {rel(SAIDA)} ({len(pagina.encode()) // 1024} KiB)")
    print("arquivos ausentes: " + ("; ".join(f"{d}: {p}" for d, p in faltas) if faltas else "nenhum"))


if __name__ == "__main__":
    main()
