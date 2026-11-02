'use strict';
// Verifica um certificado e o lote de check-ins contra o RegistroDeBatches.
//
// uso (na raiz do repositório):
//   node demo-verificacao/verificar.js <certificado_id> <pasta>
//
// Os ids consultados no contrato vêm do certificado_id informado (como viria do
// QR code), não do arquivo. Hash e fingerprint são recalculados a partir de
// <pasta>/certificado.json e <pasta>/checkins.json; nenhuma evidência gravada é usada.
// Vereditos (rótulos da #193 do QRCheck): VALIDO, ADULTERADO, NAO_ANCORADO.
// Saída 0 se ambos forem VALIDO e a regra das atividades for cumprida; 2 caso
// contrário; 1 em erro de execução (rede errada, arquivo ausente, argumentos).

const d = require('./lib/demo');
const { uuid } = require('./lib/canonico');

function situacao(onchain, recalculado, tamanho) {
    if (!onchain.existe) return 'NAO_ANCORADO';
    if (recalculado === null) return 'ADULTERADO';
    return onchain.fingerprint === d.bytes32(recalculado) && onchain.tamanho === tamanho ? 'VALIDO' : 'ADULTERADO';
}

function quando(seg) {
    return seg ? `${new Date(seg * 1000).toISOString()} (registradoEm ${seg})` : '-';
}

async function main() {
    const [idArg, pasta] = process.argv.slice(2);
    if (!idArg || !pasta) throw new Error('uso: node demo-verificacao/verificar.js <certificado_id> <pasta>');
    const certificadoId = uuid(idArg, 'certificado_id');

    const { web3, dep, contrato } = await d.conectar();
    const ids = d.idsNoContrato(web3, certificadoId);
    console.log(`rede: chainId ${dep.chainId}, bloco 0 ${dep.hashBloco0} (confere com deployment.json), contrato ${dep.endereco}`);
    console.log(`certificado_id: ${certificadoId}  pasta: ${pasta}\n`);

    const entrada = d.lerPasta(pasta);

    // certificado
    let cert = null;
    let erroCert = null;
    try { cert = d.calcularCertificado(entrada.certificadoEntrada); } catch (e) { erroCert = e.message; }
    const ocCert = await d.consultar(contrato, ids.certificado);
    const sCert = situacao(ocCert, cert && cert.hash, 1);
    console.log(`CERTIFICADO  ${sCert}`);
    if (erroCert) console.log(`  arquivo não passa na serialização canônica: ${erroCert}`);
    else {
        if (cert.certificado.certificado_id !== certificadoId) console.log(`  certificado.json traz outro certificado_id: ${cert.certificado.certificado_id}`);
        console.log(`  sha256 recalculado: 0x${cert.hash}`);
    }
    console.log(`  no contrato:        ${ocCert.existe ? ocCert.fingerprint : '(id inexistente)'}`);
    console.log(`  id ${ids.certificado} = keccak256("${ids.preimagens.certificado}")`);
    console.log(`  registrado: ${quando(ocCert.registradoEm)} por ${ocCert.registradoPor}\n`);

    // check-ins
    let lote = null;
    let erroLote = null;
    try { lote = d.fingerprintLote(entrada.checkinsEntrada); } catch (e) { erroLote = e.message; }
    const ocLote = await d.consultar(contrato, ids.checkins);
    const sLote = situacao(ocLote, lote && lote.fingerprint, lote ? lote.tamanho : -1);
    console.log(`CHECK-INS    ${sLote}`);
    if (erroLote) console.log(`  arquivo não passa na serialização canônica: ${erroLote}`);
    else console.log(`  fingerprint recalculado: 0x${lote.fingerprint} (${lote.tamanho} check-ins)`);
    console.log(`  no contrato:             ${ocLote.existe ? `${ocLote.fingerprint} (${ocLote.tamanho} check-ins)` : '(id inexistente)'}`);
    console.log(`  id ${ids.checkins} = keccak256("${ids.preimagens.checkins}")`);
    console.log(`  registrado: ${quando(ocLote.registradoEm)} por ${ocLote.registradoPor}\n`);

    // regra
    let regraOk = false;
    if (cert && lote) {
        const regra = d.regraAtividades(cert.certificado, lote.itens);
        regraOk = regra.ok;
        console.log(d.formatarRegra(regra));
    } else {
        console.log('regra das atividades: não avaliada (arquivo inválido)');
    }

    const tudoOk = sCert === 'VALIDO' && sLote === 'VALIDO' && regraOk;
    console.log(`\nRESULTADO: ${tudoOk ? 'VALIDO' : 'NAO VALIDO'}`);
    process.exit(tudoOk ? 0 : 2);
}

main().catch((e) => { console.error('ERRO:', e.message); process.exit(1); });
