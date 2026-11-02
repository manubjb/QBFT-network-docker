'use strict';
// Confere lib/canonico.js contra o vetor de referência e algumas regras de rejeição.
// uso: node demo-verificacao/testes/conferir-vetor.js

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const can = require('../lib/canonico');

const vetor = JSON.parse(fs.readFileSync(path.join(__dirname, 'vetor-referencia.json'), 'utf8'));
let falhas = 0;

function caso(nome, fn) {
    try { fn(); console.log(`ok    ${nome}`); }
    catch (e) { falhas++; console.log(`FALHA ${nome}\n      ${e.message}`); }
}
const clone = (o) => JSON.parse(JSON.stringify(o));
const rejeita = (o, padrao) => assert.throws(() => can.canonicoCertificado(o), padrao);

caso('entrada com atividades fora de ordem (pré-condição do vetor)', () => {
    const ids = vetor.entrada.atividades.map((a) => a.id);
    assert.notDeepStrictEqual(ids, [...ids].sort());
});

let gerado;
caso('string canônica idêntica à esperada', () => {
    gerado = can.canonicoCertificado(vetor.entrada);
    assert.strictEqual(gerado, vetor.canonico_esperado);
});

caso(`SHA-256 = ${vetor.sha256_esperado}`, () => {
    assert.strictEqual(can.hashCertificado(vetor.entrada), vetor.sha256_esperado);
});

caso('exemplo/certificado.json é igual à entrada do vetor', () => {
    const ex = JSON.parse(fs.readFileSync(path.join(__dirname, '../exemplo/certificado.json'), 'utf8'));
    assert.deepStrictEqual(ex, vetor.entrada);
});

caso('UUID em maiúsculas é normalizado para minúsculas (mesmo hash)', () => {
    const c = clone(vetor.entrada);
    c.certificado_id = c.certificado_id.toUpperCase();
    assert.strictEqual(can.hashCertificado(c), vetor.sha256_esperado);
});

caso('sem normalização Unicode: NFD gera hash diferente', () => {
    const c = clone(vetor.entrada);
    c.nome_titular = c.nome_titular.normalize('NFD');
    assert.notStrictEqual(can.hashCertificado(c), vetor.sha256_esperado);
});

caso('controle é escapado; não ASCII não', () => {
    assert.strictEqual(can.json('a\n\u0001é"\\'), '"a\\n\\u0001é\\"\\\\"');
});

caso('rejeita soma das cargas diferente do total', () => {
    const c = clone(vetor.entrada); c.carga_horaria_minutos = 211; rejeita(c, /soma das cargas/);
});

caso('rejeita atividades fora do modo SOMA_ATIVIDADES', () => {
    const c = clone(vetor.entrada); c.modo_carga_horaria = 'FIXA'; rejeita(c, /só são permitidas/);
});

caso('rejeita emitido_em sem microssegundos ou fora de UTC', () => {
    for (const t of ['2026-10-24T14:32:07.123Z', '2026-10-24T14:32:07.123456+00:00', '2026-02-30T14:32:07.123456Z']) {
        const c = clone(vetor.entrada); c.emitido_em = t; rejeita(c, /emitido_em/);
    }
});

caso('rejeita chave não prevista', () => {
    const c = clone(vetor.entrada); c.extra = 1; rejeita(c, /não previstas/);
});

if (gerado !== undefined) {
    console.log('\ngerado: ' + gerado);
    console.log('sha256: ' + can.sha256Hex(gerado));
}
console.log(falhas ? `\n${falhas} FALHA(S)` : '\ntodos os casos ok');
process.exit(falhas ? 1 : 0);
