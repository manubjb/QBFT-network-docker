'use strict';
// Serialização canônica do certificado (regras da #162 do QRCheck) e SHA-256.
//
// - chaves em ordem alfabética em todos os níveis; sem espaços;
// - strings sem escape de não ASCII: só ", \ e controles (U+0000–U+001F) são escapados;
// - sem normalização Unicode (o texto entra como veio);
// - UUIDs em minúsculas;
// - emitido_em em UTC, AAAA-MM-DDTHH:MM:SS.ffffffZ (microssegundos);
// - atividades só no modo SOMA_ATIVIDADES, ordenadas pelo id, soma das cargas = total;
// - SHA-256 sobre os bytes UTF-8, hexadecimal minúsculo.

const crypto = require('crypto');

const RE_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const RE_INSTANTE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$/;
const MODO_SOMA = 'SOMA_ATIVIDADES';

function erro(msg) { throw new Error(msg); }

// JSON canônico genérico: objetos com chaves ordenadas, arrays na ordem dada.
// Só aceita strings bem formadas, inteiros seguros, booleanos e null.
function json(valor) {
    if (valor === null) return 'null';
    if (typeof valor === 'boolean') return valor ? 'true' : 'false';
    if (typeof valor === 'number') {
        if (!Number.isSafeInteger(valor)) erro(`número não inteiro ou fora do intervalo seguro: ${valor}`);
        return String(valor);
    }
    if (typeof valor === 'string') {
        if (!valor.isWellFormed()) erro('string com surrogate isolado');
        // JSON.stringify escapa só ", \ e U+0000–U+001F; não escapa não ASCII.
        return JSON.stringify(valor);
    }
    if (Array.isArray(valor)) return '[' + valor.map(json).join(',') + ']';
    if (typeof valor === 'object') {
        const chaves = Object.keys(valor).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
        return '{' + chaves.map((k) => {
            if (valor[k] === undefined) erro(`chave ${k} com valor undefined`);
            return json(k) + ':' + json(valor[k]);
        }).join(',') + '}';
    }
    erro(`tipo não suportado: ${typeof valor}`);
}

function sha256Hex(texto) {
    return crypto.createHash('sha256').update(Buffer.from(texto, 'utf8')).digest('hex');
}

function uuid(valor, campo) {
    if (typeof valor !== 'string') erro(`${campo}: UUID ausente`);
    const v = valor.toLowerCase();
    if (!RE_UUID.test(v)) erro(`${campo}: UUID inválido (${valor})`);
    return v;
}

function uuidOuNull(valor, campo) {
    return valor === null ? null : uuid(valor, campo);
}

// Confere o formato AAAA-MM-DDTHH:MM:SS.ffffffZ e se a data existe.
function instante(valor, campo) {
    const m = typeof valor === 'string' && valor.match(RE_INSTANTE);
    if (!m) erro(`${campo}: esperado AAAA-MM-DDTHH:MM:SS.ffffffZ em UTC (${valor})`);
    const [ano, mes, dia, h, min, s] = m.slice(1, 7).map(Number);
    const d = new Date(Date.UTC(ano, mes - 1, dia, h, min, s));
    if (d.getUTCFullYear() !== ano || d.getUTCMonth() !== mes - 1 || d.getUTCDate() !== dia
        || d.getUTCHours() !== h || d.getUTCMinutes() !== min || d.getUTCSeconds() !== s) {
        erro(`${campo}: data/hora inexistente (${valor})`);
    }
    return valor;
}

function inteiroPositivo(valor, campo) {
    if (!Number.isSafeInteger(valor) || valor <= 0) erro(`${campo}: inteiro positivo esperado (${valor})`);
    return valor;
}

function texto(valor, campo) {
    if (typeof valor !== 'string' || valor === '') erro(`${campo}: texto não vazio esperado`);
    return valor;
}

function exatamente(obj, chaves, onde) {
    const extras = Object.keys(obj).filter((k) => !chaves.includes(k));
    if (extras.length) erro(`${onde}: chaves não previstas: ${extras.join(', ')}`);
}

const CHAVES_CERT = ['atividades', 'carga_horaria_minutos', 'certificado_id', 'emitido_em', 'emitido_por',
    'evento_id', 'evento_nome', 'modo_carga_horaria', 'nome_titular', 'participante', 'substitui', 'tipo', 'v'];
const CHAVES_ATIV = ['carga_horaria_minutos', 'id', 'nome'];

// Valida e normaliza o certificado para a forma canônica (objeto).
function normalizarCertificado(c) {
    if (!c || typeof c !== 'object' || Array.isArray(c)) erro('certificado: objeto esperado');
    exatamente(c, CHAVES_CERT, 'certificado');
    if (c.tipo !== 'certificado') erro(`tipo: esperado "certificado" (${c.tipo})`);
    if (c.v !== 1) erro(`v: versão não suportada (${c.v})`);

    const n = {
        carga_horaria_minutos: inteiroPositivo(c.carga_horaria_minutos, 'carga_horaria_minutos'),
        certificado_id: uuid(c.certificado_id, 'certificado_id'),
        emitido_em: instante(c.emitido_em, 'emitido_em'),
        emitido_por: uuid(c.emitido_por, 'emitido_por'),
        evento_id: uuid(c.evento_id, 'evento_id'),
        evento_nome: texto(c.evento_nome, 'evento_nome'),
        modo_carga_horaria: texto(c.modo_carga_horaria, 'modo_carga_horaria'),
        nome_titular: texto(c.nome_titular, 'nome_titular'),
        participante: uuid(c.participante, 'participante'),
        substitui: uuidOuNull(c.substitui, 'substitui'), // obrigatório: UUID ou null
        tipo: 'certificado',
        v: 1,
    };

    if (n.modo_carga_horaria === MODO_SOMA) {
        if (!Array.isArray(c.atividades) || c.atividades.length === 0) erro('atividades: obrigatórias no modo SOMA_ATIVIDADES');
        const ativ = c.atividades.map((a, i) => {
            if (!a || typeof a !== 'object' || Array.isArray(a)) erro(`atividades[${i}]: objeto esperado`);
            exatamente(a, CHAVES_ATIV, `atividades[${i}]`);
            return {
                carga_horaria_minutos: inteiroPositivo(a.carga_horaria_minutos, `atividades[${i}].carga_horaria_minutos`),
                id: uuid(a.id, `atividades[${i}].id`),
                nome: texto(a.nome, `atividades[${i}].nome`),
            };
        }).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        for (let i = 1; i < ativ.length; i++) if (ativ[i].id === ativ[i - 1].id) erro(`atividades: id repetido ${ativ[i].id}`);
        const soma = ativ.reduce((s, a) => s + a.carga_horaria_minutos, 0);
        if (soma !== n.carga_horaria_minutos) erro(`atividades: soma das cargas (${soma}) ≠ carga_horaria_minutos (${n.carga_horaria_minutos})`);
        n.atividades = ativ;
    } else if (c.atividades !== undefined) {
        erro(`atividades: só são permitidas no modo SOMA_ATIVIDADES (modo ${n.modo_carga_horaria})`);
    }
    return n;
}

function canonicoCertificado(c) {
    return json(normalizarCertificado(c));
}

function hashCertificado(c) {
    return sha256Hex(canonicoCertificado(c));
}

module.exports = {
    json, sha256Hex, uuid, uuidOuNull, instante, normalizarCertificado, canonicoCertificado, hashCertificado, MODO_SOMA,
};
