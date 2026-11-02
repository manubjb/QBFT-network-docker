'use strict';
// Partes comuns de ancorar.js e verificar.js: leitura da pasta, regra das
// atividades, ids no contrato e conexão conferida com o deployment.json.

const fs = require('fs');
const path = require('path');
const { normalizarCertificado, canonicoCertificado, sha256Hex, MODO_SOMA } = require('./canonico');
const { fingerprintLote } = require('./lote');

const DEMO = path.resolve(__dirname, '..');
const RAIZ = path.resolve(DEMO, '..');
const Web3 = require(path.join(RAIZ, 'caliper-workspace/node_modules/web3'));
const DEPLOYMENT = path.join(DEMO, 'deployment.json');
const ARTEFATO = path.join(RAIZ, 'caliper-workspace/networks/contracts/RegistroDeBatches.json');

function lerJson(arq) { return JSON.parse(fs.readFileSync(arq, 'utf8')); }

// Lê certificado.json e checkins.json da pasta e calcula hash e fingerprint.
function lerPasta(pasta) {
    const arqCert = path.join(pasta, 'certificado.json');
    const arqChk = path.join(pasta, 'checkins.json');
    const bruto = { certificado: fs.readFileSync(arqCert), checkins: fs.readFileSync(arqChk) };
    const certificadoEntrada = JSON.parse(bruto.certificado.toString('utf8'));
    const checkinsEntrada = JSON.parse(bruto.checkins.toString('utf8'));
    return {
        certificadoEntrada,
        checkinsEntrada,
        sha256Arquivos: { 'certificado.json': sha256Hex(bruto.certificado), 'checkins.json': sha256Hex(bruto.checkins) },
    };
}

function calcularCertificado(entrada) {
    const certificado = normalizarCertificado(entrada);
    const canonico = canonicoCertificado(entrada);
    return { certificado, canonico, hash: sha256Hex(canonico) };
}

// Regra da demonstração: cada atividade do certificado tem ao menos um
// check-in do titular, no mesmo evento, naquela atividade.
function regraAtividades(certificado, itensLote) {
    if (certificado.modo_carga_horaria !== MODO_SOMA) {
        return { ok: true, aplicavel: false, motivo: `modo ${certificado.modo_carga_horaria}: certificado sem atividades`, atividades: [] };
    }
    const atividades = certificado.atividades.map((a) => {
        const n = itensLote.filter(({ registro: r }) => r.atividade_id === a.id
            && r.participante === certificado.participante && r.evento_id === certificado.evento_id).length;
        return { id: a.id, nome: a.nome, checkins_do_titular: n, ok: n > 0 };
    });
    return { ok: atividades.every((a) => a.ok), aplicavel: true, atividades };
}

function formatarRegra(regra) {
    if (!regra.aplicavel) return `regra das atividades: não se aplica (${regra.motivo})`;
    const linhas = regra.atividades.map((a) => `    ${a.ok ? 'ok   ' : 'FALTA'} ${a.nome} (${a.id}): ${a.checkins_do_titular} check-in(s) do titular`);
    return `regra das atividades: ${regra.ok ? 'CUMPRIDA' : 'NAO CUMPRIDA'}\n` + linhas.join('\n');
}

function preimagens(certificadoId) {
    return { certificado: 'certificado:' + certificadoId, checkins: 'checkins:' + certificadoId };
}

function idsNoContrato(web3, certificadoId) {
    const p = preimagens(certificadoId);
    const k = (s) => web3.utils.keccak256(web3.utils.utf8ToHex(s));
    return { preimagens: p, certificado: k(p.certificado), checkins: k(p.checkins) };
}

// Conecta no RPC do deployment.json e recusa se chainId ou hash do bloco 0 não baterem.
async function conectar() {
    if (!fs.existsSync(DEPLOYMENT)) throw new Error('deployment.json não encontrado');
    const dep = lerJson(DEPLOYMENT);
    const web3 = new Web3(dep.rpc);
    const chainId = await web3.eth.getChainId();
    if (chainId !== dep.chainId) throw new Error(`chainId ${chainId} ≠ ${dep.chainId} do deployment.json; abortado`);
    const bloco0 = (await web3.eth.getBlock(0)).hash;
    if (bloco0 !== dep.hashBloco0) throw new Error(`hash do bloco 0 ${bloco0} ≠ ${dep.hashBloco0} do deployment.json; abortado`);
    if ((await web3.eth.getCode(dep.endereco)) === '0x') throw new Error(`sem código em ${dep.endereco}; abortado`);
    const contrato = new web3.eth.Contract(lerJson(ARTEFATO).abi, dep.endereco);
    return { web3, dep, contrato };
}

async function consultar(contrato, id) {
    const r = await contrato.methods.consultarPorId(id).call();
    return {
        existe: r.existe,
        fingerprint: r.fingerprint,
        registradoEm: Number(r.registradoEm),
        tamanho: Number(r.tamanho),
        registradoPor: r.registradoPor,
    };
}

const bytes32 = (hex) => '0x' + hex;

module.exports = {
    DEMO, RAIZ, lerJson, lerPasta, calcularCertificado, fingerprintLote, regraAtividades, formatarRegra,
    idsNoContrato, conectar, consultar, bytes32,
};
