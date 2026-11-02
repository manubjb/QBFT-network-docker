'use strict';
// Executa o bloco <script id="nucleo"> de pagina/index.html no Node e confere contra
// lib/ (serialização, fingerprint, regra), web3 (keccak256, seletor, checksum, decodificação)
// e os dados de deployment.json, ancoragens.json e exemplo/.
// Se a instância qbft-demo estiver no ar, confere também a decodificação de eth_call real.
//
// uso: node demo-verificacao/testes/conferir-pagina.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const assert = require('assert');

const DEMO = path.resolve(__dirname, '..');
const RAIZ = path.resolve(DEMO, '..');
const Web3 = require(path.join(RAIZ, 'caliper-workspace/node_modules/web3'));
const web3 = new Web3();
const can = require('../lib/canonico');
const { fingerprintLote } = require('../lib/lote');
const d = require('../lib/demo');

const html = fs.readFileSync(path.join(DEMO, 'pagina/index.html'), 'utf8');
const bloco = (id) => {
    const m = html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)</script>`));
    if (!m) throw new Error(`bloco ${id} não encontrado na página`);
    return m[1];
};
const N = vm.runInNewContext(bloco('nucleo') + '\n;Nucleo', { TextEncoder });
const lerJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const dep = lerJson(path.join(DEMO, 'deployment.json'));
const ancoragens = lerJson(path.join(DEMO, 'ancoragens.json'));
const exCert = lerJson(path.join(DEMO, 'exemplo/certificado.json'));
const exChk = lerJson(path.join(DEMO, 'exemplo/checkins.json'));
const vetor = lerJson(path.join(DEMO, 'testes/vetor-referencia.json'));
const abi = lerJson(path.join(RAIZ, 'caliper-workspace/networks/contracts/RegistroDeBatches.json')).abi;

let falhas = 0;
async function caso(nome, fn) {
    try { await fn(); console.log(`ok    ${nome}`); } catch (e) { falhas++; console.log(`FALHA ${nome}\n      ${e.message}`); }
}
const plain = (o) => JSON.parse(JSON.stringify(o)); // objetos do vm têm outro Object.prototype

(async () => {
    await caso('keccak256("") = c5d24601…5d85a470 (valor conhecido)', () => {
        assert.strictEqual(N.keccakTexto(''), '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470');
    });
    await caso('keccak256 igual ao da web3 para entradas de 0 a 400 bytes (bordas de bloco 135/136/137, 271/272/273)', () => {
        for (let n = 0; n <= 400; n++) {
            const s = crypto.randomBytes(n).toString('base64').slice(0, n);
            // sha3Raw: a web3 1.x devolve null em keccak256('') e sha3('')
            assert.strictEqual(N.keccakTexto(s), web3.utils.sha3Raw(web3.utils.utf8ToHex(s)), `n=${n}`);
        }
    });
    for (const a of ancoragens) {
        await caso(`ids de ${a.certificado_id} iguais aos do ancoragens.json`, () => {
            const ids = N.idsNoContrato(a.certificado_id);
            assert.strictEqual(ids.certificado, a.certificado.id);
            assert.strictEqual(ids.checkins, a.checkins.id);
        });
    }
    await caso('seletor de consultarPorId (assinatura montada do ABI do artefato) igual ao da web3', () => {
        const f = abi.find((x) => x.name === 'consultarPorId');
        const assinatura = `${f.name}(${f.inputs.map((i) => i.type).join(',')})`;
        assert.strictEqual(assinatura, N.ASSINATURA_CONSULTA);
        assert.strictEqual(N.seletor(assinatura), web3.eth.abi.encodeFunctionSignature(f));
        console.log(`      ${assinatura} -> ${N.seletor(assinatura)}`);
    });
    await caso('SHA-256 igual ao do Node (0–300 bytes, ASCII e Unicode)', () => {
        for (let n = 0; n <= 300; n++) {
            for (const s of ['a'.repeat(n), 'é—Ñ😀'.repeat(n).slice(0, n)]) {
                if (!s.isWellFormed()) continue;
                assert.strictEqual(N.sha256Hex(s), can.sha256Hex(s), `n=${n}`);
            }
        }
    });
    await caso('vetor de referência: string canônica e SHA-256', () => {
        const c = N.calcularCertificado(vetor.entrada);
        assert.strictEqual(c.canonico, vetor.canonico_esperado);
        assert.strictEqual(c.hash, vetor.sha256_esperado);
    });
    await caso('exemplo: hash do certificado e fingerprint do lote iguais aos de lib/ (verificar.js)', () => {
        assert.strictEqual(N.calcularCertificado(exCert).hash, can.hashCertificado(exCert));
        const lp = N.fingerprintLote(exChk);
        const ll = fingerprintLote(exChk);
        assert.deepStrictEqual(plain(lp.cadeia), ll.cadeia);
        assert.deepStrictEqual(lp.itens.map((i) => i.canonico), ll.itens.map((i) => i.canonico));
        console.log(`      certificado ${N.calcularCertificado(exCert).hash}\n      lote        ${lp.fingerprint}`);
    });
    await caso('mesmas recusas que lib/ (soma, modo, emitido_em, chave extra, UUID)', () => {
        const casos = [
            (c) => { c.carga_horaria_minutos = 211; }, (c) => { c.modo_carga_horaria = 'FIXA'; },
            (c) => { c.emitido_em = '2026-10-24T14:32:07.123Z'; }, (c) => { c.extra = 1; }, (c) => { c.participante = 'x'; },
        ];
        for (const f of casos) {
            const c = plain(exCert); f(c);
            let ep = null; let el = null;
            try { N.calcularCertificado(c); } catch (e) { ep = e.message; }
            try { can.canonicoCertificado(c); } catch (e) { el = e.message; }
            assert.ok(ep && el, 'ambos devem recusar');
            assert.strictEqual(ep, el);
        }
    });
    await caso('regra das atividades igual à de lib/demo.js', () => {
        const rp = N.regraAtividades(N.calcularCertificado(exCert).certificado, N.fingerprintLote(exChk).itens);
        const rl = d.regraAtividades(can.normalizarCertificado(exCert), fingerprintLote(exChk).itens);
        assert.strictEqual(rp.ok, rl.ok);
        assert.deepStrictEqual(rp.atividades.map((a) => [a.id, a.checkins_do_titular]), rl.atividades.map((a) => [a.id, a.checkins_do_titular]));
    });
    await caso('checksum de endereço igual ao da web3', () => {
        for (const a of [dep.endereco, dep.contaDeploy, '0x' + 'ab'.repeat(20)]) assert.strictEqual(N.checksum(a), web3.utils.toChecksumAddress(a));
    });
    await caso('página embute chainId, bloco 0, contrato e rpc do deployment.json', () => {
        const impl = JSON.parse(bloco('implantacao'));
        assert.deepStrictEqual(impl, { chainId: dep.chainId, hashBloco0: dep.hashBloco0, endereco: dep.endereco, rpc: dep.rpc });
    });
    await caso('página embute exatamente exemplo/certificado.json e exemplo/checkins.json', () => {
        assert.deepStrictEqual(JSON.parse(bloco('exemplo-certificado')), exCert);
        assert.deepStrictEqual(JSON.parse(bloco('exemplo-checkins')), exChk);
    });
    await caso('página não embute nada de dados/', () => {
        const dir = path.join(DEMO, 'dados');
        const arquivos = fs.existsSync(dir) ? fs.readdirSync(dir, { recursive: true }).filter((f) => f.endsWith('.json')) : [];
        for (const f of arquivos) {
            const txt = fs.readFileSync(path.join(dir, f), 'utf8');
            for (const m of txt.matchAll(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi)) {
                assert.ok(!html.toLowerCase().includes(m[0].toLowerCase()), `UUID de dados/${f} aparece na página`);
            }
        }
        console.log(`      ${arquivos.length} arquivo(s) JSON em dados/ conferidos`);
    });

    // Com a rede no ar: decodificação de eth_call real igual à da web3.
    let conexao = null;
    try { conexao = await d.conectar(); } catch (e) { console.log(`(pulado) eth_call real: ${e.message}`); }
    if (conexao) {
        const { web3: w3, contrato } = conexao;
        const idInexistente = w3.utils.keccak256(w3.utils.utf8ToHex('demo-verificacao:id-inexistente'));
        for (const [nome, id] of [['certificado do exemplo', ancoragens[0].certificado.id], ['check-ins do exemplo', ancoragens[0].checkins.id], ['id inexistente', idInexistente]]) {
            await caso(`eth_call real (${nome}): decodificação da página igual à da web3`, async () => {
                const bruto = await w3.eth.call({ to: dep.endereco, data: N.dadosConsulta(id) });
                const p = plain(N.decodificarConsulta(bruto));
                const r = await contrato.methods.consultarPorId(id).call();
                assert.deepStrictEqual(p, {
                    fingerprint: r.fingerprint, registradoEm: Number(r.registradoEm), tamanho: Number(r.tamanho),
                    registradoPor: r.registradoPor, existe: r.existe,
                });
            });
        }
    }

    console.log(falhas ? `\n${falhas} FALHA(S)` : '\ntodos os casos ok');
    process.exit(falhas ? 1 : 0);
})();
