'use strict';
// Ancora um certificado e o lote de check-ins do titular no RegistroDeBatches.
//
// uso (na raiz do repositório):
//   DEMO_DEPLOYER_KEY=0x... node demo-verificacao/ancorar.js <pasta>
//
// <pasta> contém certificado.json e checkins.json (demo-verificacao/exemplo ou demo-verificacao/dados).
// Grava as evidências completas em <pasta>/ancoragem-<certificado_id>.json e só os
// metadados sem dados pessoais em demo-verificacao/ancoragens.json.

const fs = require('fs');
const path = require('path');
const d = require('./lib/demo');

const REGISTRO = path.join(d.DEMO, 'ancoragens.json');

async function main() {
    const pasta = process.argv[2];
    if (!pasta) throw new Error('uso: node demo-verificacao/ancorar.js <pasta>');
    const chave = process.env.DEMO_DEPLOYER_KEY;
    if (!chave) throw new Error('defina DEMO_DEPLOYER_KEY');

    // 1. dados e regra (antes de tocar na rede)
    const entrada = d.lerPasta(pasta);
    const cert = d.calcularCertificado(entrada.certificadoEntrada);
    const c = cert.certificado;
    const lote = d.fingerprintLote(entrada.checkinsEntrada);
    if (lote.tamanho === 0) throw new Error('checkins.json vazio');
    const alheios = lote.itens.filter(({ registro: r }) => r.participante !== c.participante || r.evento_id !== c.evento_id);
    if (alheios.length) throw new Error(`${alheios.length} check-in(s) de outro participante ou evento; o lote deve ter só os do titular neste evento`);
    const regra = d.regraAtividades(c, lote.itens);
    console.log(d.formatarRegra(regra));
    if (!regra.ok) throw new Error('regra das atividades não cumprida; nada foi ancorado');

    const evidencia = path.join(pasta, `ancoragem-${c.certificado_id}.json`);
    if (fs.existsSync(evidencia)) throw new Error(`${evidencia} já existe`);

    // 2. rede conferida e ids livres
    const { web3, dep, contrato } = await d.conectar();
    const ids = d.idsNoContrato(web3, c.certificado_id);
    for (const tipo of ['certificado', 'checkins']) {
        if ((await d.consultar(contrato, ids[tipo])).existe) throw new Error(`id de ${tipo} ${ids[tipo]} já existe no contrato; abortado`);
    }
    const conta = web3.eth.accounts.privateKeyToAccount(chave);

    console.log(`rede: chainId ${dep.chainId}, bloco 0 ${dep.hashBloco0}, contrato ${dep.endereco}`);
    console.log(`certificado ${c.certificado_id}: sha256 ${cert.hash}`);
    console.log(`check-ins: ${lote.tamanho}, fingerprint ${lote.fingerprint}`);

    // 3. transações, uma por vez, conferindo receipt.status
    const envios = [
        { tipo: 'certificado', id: ids.certificado, fingerprint: d.bytes32(cert.hash), tamanho: 1 },
        { tipo: 'checkins', id: ids.checkins, fingerprint: d.bytes32(lote.fingerprint), tamanho: lote.tamanho },
    ];
    const resultados = {};
    let falha = null;
    for (const e of envios) {
        try {
            const data = contrato.methods.registrarBatch(e.id, e.fingerprint, e.tamanho).encodeABI();
            const gas = await web3.eth.estimateGas({ from: conta.address, to: dep.endereco, data });
            const tx = await conta.signTransaction({
                to: dep.endereco, data, gas: Math.ceil(gas * 1.2), gasPrice: await web3.eth.getGasPrice(),
                nonce: await web3.eth.getTransactionCount(conta.address, 'pending'), chainId: dep.chainId,
            });
            const r = await web3.eth.sendSignedTransaction(tx.rawTransaction);
            resultados[e.tipo] = { tx: r.transactionHash, bloco: r.blockNumber, hashBloco: r.blockHash, status: r.status, gasUsed: r.gasUsed };
            if (!r.status) throw new Error(`receipt.status = false (tx ${r.transactionHash})`);
            const lido = await d.consultar(contrato, e.id);
            if (!lido.existe || lido.fingerprint !== e.fingerprint || lido.tamanho !== e.tamanho) {
                throw new Error(`leitura após registro não confere: ${JSON.stringify(lido)}`);
            }
            resultados[e.tipo].onchain = lido;
            console.log(`${e.tipo}: tx ${r.transactionHash}, bloco ${r.blockNumber}, status ${r.status}`);
        } catch (err) {
            // web3 1.x rejeita em revert e anexa o receipt ao erro
            if (err.receipt && !resultados[e.tipo]) {
                const r = err.receipt;
                resultados[e.tipo] = { tx: r.transactionHash, bloco: r.blockNumber, hashBloco: r.blockHash, status: r.status, gasUsed: r.gasUsed };
            }
            falha = `${e.tipo}: ${err.message}`;
            break;
        }
    }

    // 4. evidências (gravadas também em falha parcial, marcadas como incompletas)
    const agora = new Date().toISOString();
    const completa = !falha;
    const rede = { chainId: dep.chainId, hashBloco0: dep.hashBloco0, contrato: dep.endereco, rpc: dep.rpc };
    const completo = {
        completa, falha, ancorado_em: agora, rede, conta: conta.address,
        arquivos_sha256: entrada.sha256Arquivos,
        regra_atividades: regra,
        certificado: {
            certificado_id: c.certificado_id, canonico: cert.canonico, sha256: cert.hash,
            id_preimagem: ids.preimagens.certificado, id: ids.certificado, tamanho: 1, ...resultados.certificado,
        },
        checkins: {
            semente: lote.semente, h0: lote.cadeia[0],
            itens: lote.itens.map((it, i) => ({ canonico: it.canonico, h: lote.cadeia[i + 1] })),
            fingerprint: lote.fingerprint, tamanho: lote.tamanho,
            id_preimagem: ids.preimagens.checkins, id: ids.checkins, ...resultados.checkins,
        },
    };
    fs.writeFileSync(evidencia, JSON.stringify(completo, null, 2) + '\n');

    const meta = (tipo, valor, tam) => ({ id: ids[tipo], [tipo === 'certificado' ? 'sha256' : 'fingerprint']: valor, tamanho: tam,
        tx: resultados[tipo]?.tx ?? null, bloco: resultados[tipo]?.bloco ?? null, status: resultados[tipo]?.status ?? null });
    const registros = fs.existsSync(REGISTRO) ? d.lerJson(REGISTRO) : [];
    registros.push({
        certificado_id: c.certificado_id, pasta: path.relative(d.RAIZ, path.resolve(pasta)), completa, ancorado_em: agora, rede,
        certificado: meta('certificado', cert.hash, 1),
        checkins: meta('checkins', lote.fingerprint, lote.tamanho),
    });
    fs.writeFileSync(REGISTRO, JSON.stringify(registros, null, 2) + '\n');

    console.log(`evidências: ${path.relative(d.RAIZ, path.resolve(evidencia))}`);
    console.log(`metadados:  ${path.relative(d.RAIZ, REGISTRO)}`);
    if (falha) throw new Error(`ancoragem incompleta: ${falha}`);
    console.log('ANCORADO');
}

main().catch((e) => { console.error('ERRO:', e.message); process.exit(1); });
