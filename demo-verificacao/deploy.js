'use strict';
// Deploy do RegistroDeBatches na instância persistente da demonstração (qbft-demo).
// Usa o mesmo artefato compilado do benchmark e a web3 já instalada no caliper-workspace.
//
// uso (na raiz do repositório):
//   DEMO_DEPLOYER_KEY=0x... node demo-verificacao/deploy.js
//
// Recusa rodar se o chainId não for 1338 (protege a rede do benchmark, chainId 1337)
// ou se demo-verificacao/deployment.json já existir.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execSync } = require('child_process');

const RAIZ = path.resolve(__dirname, '..');
const Web3 = require(path.join(RAIZ, 'caliper-workspace/node_modules/web3'));

const RPC = 'http://127.0.0.1:9545';
const CHAIN_ID = 1338;
const ARTEFATO = 'caliper-workspace/networks/contracts/RegistroDeBatches.json';
const SAIDA = path.join(__dirname, 'deployment.json');

async function main() {
    if (fs.existsSync(SAIDA)) throw new Error(`${SAIDA} já existe; não refaço o deploy`);
    const chave = process.env.DEMO_DEPLOYER_KEY;
    if (!chave) throw new Error('defina DEMO_DEPLOYER_KEY');

    const web3 = new Web3(RPC);
    const chainId = await web3.eth.getChainId();
    if (chainId !== CHAIN_ID) throw new Error(`chainId ${chainId} != ${CHAIN_ID}; abortado`);

    const conta = web3.eth.accounts.privateKeyToAccount(chave);
    const bruto = fs.readFileSync(path.join(RAIZ, ARTEFATO));
    const artefato = JSON.parse(bruto);

    const data = new web3.eth.Contract(artefato.abi).deploy({ data: artefato.bytecode }).encodeABI();
    const nonce = await web3.eth.getTransactionCount(conta.address, 'pending');
    const gas = await web3.eth.estimateGas({ from: conta.address, data });
    const gasPrice = await web3.eth.getGasPrice();
    const assinada = await conta.signTransaction({ data, nonce, gas: Math.ceil(gas * 1.2), gasPrice, chainId });
    const recibo = await web3.eth.sendSignedTransaction(assinada.rawTransaction);
    if (!recibo.status || !recibo.contractAddress) throw new Error('deploy falhou: ' + JSON.stringify(recibo));

    const codigo = await web3.eth.getCode(recibo.contractAddress);

    const bloco0 = await web3.eth.getBlock(0);
    const sh = (c) => execSync(c, { cwd: RAIZ }).toString().trim();

    const registro = {
        rede: 'qbft-demo (demo-verificacao/rede/docker-compose.yml)',
        rpc: RPC,
        chainId,
        hashBloco0: bloco0.hash,
        contrato: 'RegistroDeBatches',
        endereco: recibo.contractAddress,
        blocoDeploy: recibo.blockNumber,
        hashBlocoDeploy: recibo.blockHash,
        txDeploy: recibo.transactionHash,
        contaDeploy: conta.address,
        nonceDeploy: nonce,
        artefato: ARTEFATO,
        artefatoSha256: crypto.createHash('sha256').update(bruto).digest('hex'),
        codigoOnChainIgualAoDeployedBytecode: codigo.toLowerCase() === artefato.deployedBytecode.toLowerCase(),
        commit: sh('git rev-parse HEAD'),
        branch: sh('git branch --show-current'),
        arvoreComAlteracoesNaoCommitadas: sh('git status --porcelain') !== '',
        dataDeploy: new Date().toISOString(),
    };
    fs.writeFileSync(SAIDA, JSON.stringify(registro, null, 2) + '\n');
    console.log(JSON.stringify(registro, null, 2));
}

main().catch((e) => { console.error('ERRO:', e.message); process.exit(1); });
