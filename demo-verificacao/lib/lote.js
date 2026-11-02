'use strict';
// Fingerprint encadeado do lote de check-ins (mesmo algoritmo do artigo):
//   h0  = SHA256(semente)
//   h_i = SHA256(hex(h_{i-1}) + canon(registro_i))
// hex minúsculo; concatenação como texto, SHA-256 sobre os bytes UTF-8.
// canon = mesma serialização ordenada de lib/canonico.js.
//
// Ordem dos registros: horario_checkin, depois atividade_id. Em empate exato
// nesses dois campos, desempata pela própria string canônica, para que a
// ordem (e o fingerprint) nunca dependa da ordem de leitura do arquivo.

const { json, sha256Hex, uuid, uuidOuNull, instante } = require('./canonico');

const SEMENTE = 'QRCHECK-DEMO-CHECKINS-v1';
const CHAVES = ['atividade_id', 'evento_id', 'feito_por', 'horario_checkin', 'participante', 'tipo'];

function normalizarCheckin(r, i = 0) {
    if (!r || typeof r !== 'object' || Array.isArray(r)) throw new Error(`checkins[${i}]: objeto esperado`);
    const extras = Object.keys(r).filter((k) => !CHAVES.includes(k));
    if (extras.length) throw new Error(`checkins[${i}]: chaves não previstas: ${extras.join(', ')}`);
    if (r.tipo !== 'checkin') throw new Error(`checkins[${i}].tipo: esperado "checkin" (${r.tipo})`);
    return {
        atividade_id: uuid(r.atividade_id, `checkins[${i}].atividade_id`),
        evento_id: uuid(r.evento_id, `checkins[${i}].evento_id`),
        feito_por: uuidOuNull(r.feito_por, `checkins[${i}].feito_por`),
        horario_checkin: instante(r.horario_checkin, `checkins[${i}].horario_checkin`),
        participante: uuid(r.participante, `checkins[${i}].participante`),
        tipo: 'checkin',
    };
}

const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// Devolve os registros normalizados, já na ordem do encadeamento, com o canon de cada um.
function ordenar(checkins) {
    if (!Array.isArray(checkins)) throw new Error('checkins: lista esperada');
    return checkins
        .map((r, i) => { const n = normalizarCheckin(r, i); return { registro: n, canonico: json(n) }; })
        .sort((a, b) => cmp(a.registro.horario_checkin, b.registro.horario_checkin)
            || cmp(a.registro.atividade_id, b.registro.atividade_id)
            || cmp(a.canonico, b.canonico));
}

function fingerprintLote(checkins) {
    const itens = ordenar(checkins);
    const cadeia = [sha256Hex(SEMENTE)];
    for (const it of itens) cadeia.push(sha256Hex(cadeia[cadeia.length - 1] + it.canonico));
    return { semente: SEMENTE, itens, cadeia, fingerprint: cadeia[cadeia.length - 1], tamanho: itens.length };
}

module.exports = { SEMENTE, normalizarCheckin, ordenar, fingerprintLote };
