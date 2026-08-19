'use strict';

const { WorkloadModuleBase } = require('@hyperledger/caliper-core');
const crypto = require('crypto');

class RegistrarBatchWorkload extends WorkloadModuleBase {
    constructor() {
        super();
    }

    async submitTransaction() {
        // Gera um batchId e fingerprint únicos por transação,
        // simulando um novo lote de check-ins sendo ancorado
        const batchId = '0x' + crypto.randomBytes(32).toString('hex');
        const fingerprint = '0x' + crypto.randomBytes(32).toString('hex');
        const tamanho = Math.floor(Math.random() * 100) + 1; // placeholder de N check-ins no lote

        const request = {
            contract: 'registroDeBatches',
            verb: 'registrarBatch',
            args: [batchId, fingerprint, tamanho],
            readOnly: false
        };

        await this.sutAdapter.sendRequests(request);
    }
}

function createWorkloadModule() {
    return new RegistrarBatchWorkload();
}

module.exports.createWorkloadModule = createWorkloadModule;