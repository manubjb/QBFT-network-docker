"""Diagnóstico de blocos de uma repetição e veredito do critério de validade.

uso: python3 diag.py <pasta com caliper.log> <rótulo> <arquivo de saída>

Lê blocos via rpcnode (8555) e os logs dos validadores (docker logs). Não altera nada.
Critério: nos blocos entre o deploy e o último bloco do tps-40, (i) nenhum bloco fechado em
rodada > 0 e (ii) nenhum validador importou blocos por sincronização (PersistBlockTask).
"""
import json
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "http://localhost:8555"
TZ = timezone(timedelta(hours=-3))
REMETENTE = "0x627306090abab3a6e1400e9345bc60c78a8bef57"
VALIDADORES = ["qbft-node1", "qbft-node2", "qbft-node3", "qbft-node4"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
CRITERIO = ("Uma repetição é válida se, nos blocos entre o deploy e o último bloco do tps-40, "
            "(i) nenhum bloco foi fechado em rodada maior que 0 e (ii) nenhum validador importou "
            "blocos por sincronização (PersistBlockTask).")


def rpc(metodo, params):
    corpo = json.dumps({"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params}).encode()
    req = urllib.request.Request(URL, corpo, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))["result"]


def rlp(dados, i=0):
    """Decodifica um item RLP a partir de i; devolve (item, próximo índice)."""
    b = dados[i]
    if b < 0x80:
        return dados[i:i + 1], i + 1
    if b < 0xb8:
        n = b - 0x80
        return dados[i + 1:i + 1 + n], i + 1 + n
    if b < 0xc0:
        nn = b - 0xb7
        n = int.from_bytes(dados[i + 1:i + 1 + nn], "big")
        return dados[i + 1 + nn:i + 1 + nn + n], i + 1 + nn + n
    if b < 0xf8:
        n, ini = b - 0xc0, i + 1
    else:
        nn = b - 0xf7
        n, ini = int.from_bytes(dados[i + 1:i + 1 + nn], "big"), i + 1 + nn
    itens, j = [], ini
    while j < ini + n:
        item, j = rlp(dados, j)
        itens.append(item)
    return itens, ini + n


def rodada_qbft(extra_data):
    """extraData QBFT = RLP[vanity, validadores, voto, rodada, selos]; rodada como inteiro."""
    itens, _ = rlp(bytes.fromhex(extra_data[2:]))
    return int.from_bytes(itens[3], "big") if itens[3] else 0


def hora_log(linha):
    m = re.match(r"(\d{4}\.\d{2}\.\d{2}-\d{2}:\d{2}:\d{2}\.\d{3})", linha)
    return datetime.strptime(m.group(1), "%Y.%m.%d-%H:%M:%S.%f").replace(tzinfo=TZ) if m else None


def main():
    pasta, rotulo, saida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    log = [ANSI.sub("", l) for l in (pasta / "caliper.log").read_text(encoding="utf-8").splitlines()]
    rounds, deploy_log = {}, None
    for l in log:
        if "Deployed contract" in l and deploy_log is None:
            deploy_log = hora_log(l)
        if m := re.search(r"Started round \d+ \((.+?)\)", l):
            rounds.setdefault(m.group(1), {})["ini"] = hora_log(l)
        if m := re.search(r"Finished round \d+ \((.+?)\) in ([\d.]+) seconds", l):
            rounds[m.group(1)]["fim"] = hora_log(l)

    # endereço de cada validador, pelo log de inicialização
    logs, nome_de = {}, {}
    for c in VALIDADORES + ["qbft-rpcnode"]:
        texto = subprocess.run(["docker", "logs", c], capture_output=True, text=True)
        logs[c] = [ANSI.sub("", l) for l in (texto.stdout + texto.stderr).splitlines()]
        for l in logs[c]:
            if m := re.search(r"Node address (0x[0-9a-fA-F]{40})", l):
                nome_de[m.group(1).lower()] = c.replace("qbft-", "")
                break

    log_rpc = logs.pop("qbft-rpcnode")

    ultimo = int(rpc("eth_blockNumber", []), 16)
    blocos = []
    for n in range(0, ultimo + 1):
        b = rpc("eth_getBlockByNumber", [hex(n), True])
        blocos.append({
            "n": n, "ts": datetime.fromtimestamp(int(b["timestamp"], 16), TZ),
            "ntx": len(b["transactions"]), "gas": int(b["gasUsed"], 16), "lim": int(b["gasLimit"], 16),
            "rodada": rodada_qbft(b["extraData"]),
            "proposer": nome_de.get(b["miner"].lower(), b["miner"]),
            "nonces": [int(t["nonce"], 16) for t in b["transactions"] if t["from"].lower() == REMETENTE],
        })

    b_deploy = next(b for b in blocos if 0 in b["nonces"])["n"]
    fim40 = rounds["tps-40"]["fim"]
    b_fim = max(b["n"] for b in blocos if b["ts"] <= fim40)
    b_ultima_tx = max(b["n"] for b in blocos if b["nonces"])
    janela = [b for b in blocos if b_deploy <= b["n"] <= b_fim]

    def round_de(b):
        for label, r in rounds.items():
            if r["ini"] - timedelta(seconds=1) <= b["ts"] <= r["fim"] + timedelta(seconds=1):
                return label
        return "fora de round"

    # (i) rodada > 0 pelo extraData, e conferência pelos logs
    rodada_pos = [b for b in janela if b["rodada"] > 0]
    rodada_logs = {}
    for c, linhas in logs.items():
        for l in linhas:
            if m := re.search(r"Sequence=(\d+), Round=(\d+)", l):
                s, r = int(m.group(1)), int(m.group(2))
                if r > 0 and b_deploy <= s <= b_fim:
                    rodada_logs.setdefault(s, set()).add(c.replace("qbft-", ""))
    # (ii) importações por sincronização na janela, por validador
    persist, ja_importado = {}, {}
    for c, linhas in logs.items():
        nome = c.replace("qbft-", "")
        persist[nome], ja_importado[nome] = [], 0
        for l in linhas:
            if "PersistBlockTask" not in l:
                continue
            if m := re.search(r"Imported (?:empty )?block #(\d+).*?(?:Peers: (\d+))?$", l):
                n = int(m.group(1))
                if b_deploy <= n <= b_fim:
                    persist[nome].append((n, l[11:23], m.group(2)))
            elif m := re.search(r"Block (\d+) \(.*\) is already imported", l):
                if b_deploy <= int(m.group(1)) <= b_fim:
                    ja_importado[nome] += 1

    # (ii) assinatura de sincronização sem PersistBlockTask, localizada por horário (UTC no docker logs);
    # o rpcnode não é validador: entra só como informação, fora do veredito
    t_ini = blocos[b_deploy - 1]["ts"]
    sinc_janela, sinc_fora = {}, {}
    for c, linhas in [*logs.items(), ("qbft-rpcnode", log_rpc)]:
        nome = c.replace("qbft-", "")
        sinc_janela[nome], sinc_fora[nome] = [], []
        for l in linhas:
            if "while we are syncing" not in l and "following sync" not in l:
                continue
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\+0000", l)
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            evento = "parou (while we are syncing)" if "while we are syncing" in l else "voltou (following sync)"
            item = f"{t.astimezone(TZ):%H:%M:%S.%f}"[:-3] + f" {evento}"
            (sinc_janela if t_ini <= t <= fim40 else sinc_fora)[nome].append((evento, item))

    sinc_rpc, fora_rpc = sinc_janela.pop("rpcnode"), sinc_fora.pop("rpcnode")
    valida_i = not rodada_pos
    valida_ii = not any(persist.values()) and not any(
        e.startswith("parou") for lst in sinc_janela.values() for e, _ in lst)
    out = []
    p = out.append
    p(f"Diagnóstico de blocos: {rotulo}")
    p(f"gerado em {datetime.now(TZ).isoformat(timespec='seconds')} a partir de eth_getBlockByNumber (rpcnode, "
      f"porta 8555), docker logs dos validadores e {pasta}/caliper.log")
    p("")
    p(f"Critério: {CRITERIO}")
    p("")
    p("Janela avaliada")
    p(f"- deploy (nonce 0 do remetente): bloco {b_deploy} ({blocos[b_deploy]['ts']:%H:%M:%S}); "
      f"'Deployed contract' no log às {deploy_log:%H:%M:%S.%f}"[:-3])
    p(f"- último bloco do tps-40: bloco {b_fim} ({blocos[b_fim]['ts']:%H:%M:%S}), último com timestamp <= "
      f"'Finished round (tps-40)' às {fim40:%H:%M:%S.%f}"[:-3])
    p(f"- último bloco com transação do remetente: {b_ultima_tx}; altura atual da cadeia: {ultimo}")
    for label, r in rounds.items():
        p(f"- {label}: {r['ini']:%H:%M:%S.%f}"[:-3] + f" a {r['fim']:%H:%M:%S.%f}"[:-3])
    p("")
    p("(i) Blocos fechados em rodada > 0 (rodada lida do extraData de cada bloco)")
    if rodada_pos:
        for b in rodada_pos:
            p(f"- bloco {b['n']} ({b['ts']:%H:%M:%S}, {round_de(b)}): rodada {b['rodada']}, proposer {b['proposer']}")
    else:
        p("- nenhum")
    p("  conferência nos logs (linhas 'Sequence=N, Round=R' com R > 0 na janela): " +
      (", ".join(f"altura {s} em {', '.join(sorted(v))}" for s, v in sorted(rodada_logs.items())) or "nenhuma"))
    p("")
    p("(ii) Importações por sincronização (PersistBlockTask 'Imported ... block #N') na janela, por validador")
    for nome, lst in persist.items():
        if lst:
            p(f"- {nome}: {len(lst)} blocos: " + "; ".join(f"#{n} às {h} UTC, peers={pe}" for n, h, pe in lst))
        else:
            p(f"- {nome}: nenhuma")
    p("  informativo, não é importação: linhas 'Block N is already imported' na janela: " +
      ", ".join(f"{k}={v}" for k, v in ja_importado.items()))
    p(f"(ii, detecção reforçada a partir da execução 4) linhas 'Stopping BFT mining coordinator while we are "
      f"syncing' / 'following sync' entre {t_ini:%H:%M:%S} (bloco {b_deploy - 1}) e {fim40:%H:%M:%S}, por validador")
    for nome, lst in sinc_janela.items():
        p(f"- {nome}: " + ("; ".join(i for _, i in lst) if lst else "nenhuma"))
    fora = [f"{k}: " + "; ".join(i for _, i in v) for k, v in sinc_fora.items() if v]
    p("  informativo, fora da janela: " + (" | ".join(fora) if fora else "nenhuma"))
    p("  informativo, fora do critério (o rpcnode não é validador), rpcnode na janela: " +
      ("; ".join(i for _, i in sinc_rpc) if sinc_rpc else "nenhuma"))
    p("")
    p("Intervalos entre blocos na janela (Δ até o bloco anterior)")
    for label in [*rounds, "fora de round"]:
        sel = [b for b in janela if round_de(b) == label]
        if not sel:
            continue
        d = [(b["ts"] - blocos[b["n"] - 1]["ts"]).total_seconds() for b in sel]
        c = Counter(d)
        contiguos = [b["n"] for b in sel] == list(range(sel[0]["n"], sel[-1]["n"] + 1))
        faixa = (f"blocos {sel[0]['n']} a {sel[-1]['n']}" if contiguos
                 else "blocos " + ", ".join(str(b["n"]) for b in sel))
        p(f"- {label}: {faixa}, {len(d)} intervalos; = 2 s: {c[2.0]}; "
          f"> 2 s: {sum(v for k, v in c.items() if k > 2)}; < 2 s: {sum(v for k, v in c.items() if k < 2)}; "
          f"maior: {max(d):.0f} s")
    d_all = [(b, (b["ts"] - blocos[b["n"] - 1]["ts"]).total_seconds()) for b in janela]
    diferentes = [f"bloco {b['n']} ({b['ts']:%H:%M:%S}): {x:.0f} s" for b, x in d_all if x != 2]
    p(f"- janela inteira: {len(d_all)} intervalos; diferentes de 2 s: " + ("; ".join(diferentes) or "nenhum"))
    p("")
    motivos = []
    if not valida_i:
        motivos.append("(i) blocos em rodada > 0: " + ", ".join(str(b["n"]) for b in rodada_pos))
    if any(persist.values()):
        motivos.append("(ii) importação por sincronização: " +
                       "; ".join(f"{k} #{lst[0][0]} a #{lst[-1][0]} ({len(lst)})" for k, lst in persist.items() if lst))
    parou = {k: [i for e, i in v if e.startswith("parou")] for k, v in sinc_janela.items()}
    if any(parou.values()):
        motivos.append("(ii) 'while we are syncing': " + "; ".join(f"{k} às {', '.join(v)}" for k, v in parou.items() if v))
    p(f"VEREDITO: {'VÁLIDA' if valida_i and valida_ii else 'INVÁLIDA'}" + (" | " + " | ".join(motivos) if motivos else ""))
    p("")
    p("Blocos da janela")
    p("bloco | hora     | round         | Δ (s) | txs | gás (% do limite) | rodada | proposer")
    for b, x in d_all:
        p(f"{b['n']:5d} | {b['ts']:%H:%M:%S} | {round_de(b):13s} | {x:5.0f} | {b['ntx']:3d} | "
          f"{100 * b['gas'] / b['lim']:16.1f}% | {b['rodada']:6d} | {b['proposer']}")

    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:out.index("Blocos da janela")]))
    sys.exit(0 if valida_i and valida_ii else 3)


if __name__ == "__main__":
    main()
