import requests
import json

api_key = 'F65HKQKGEBHRPS4VXKVYMHDQ2MXCZ9RYG5'
url = f'https://api.etherscan.io/api?module=proxy&action=eth_blockNumber&apikey={api_key}'
latest = int(requests.get(url).json()['result'], 16)

found = False
for i in range(latest, latest - 10, -1):
    url2 = f'https://api.etherscan.io/api?module=proxy&action=eth_getBlockByNumber&tag={hex(i)}&boolean=true&apikey={api_key}'
    block = requests.get(url2).json()['result']
    for tx in block['transactions'][:50]:
        rcpt_url = f'https://api.etherscan.io/api?module=proxy&action=eth_getTransactionReceipt&txhash={tx["hash"]}&apikey={api_key}'
        r = requests.get(rcpt_url).json()
        if r.get('result') and r['result'].get('status') == '0x0':
            print(f"REAL FAILED: {tx['hash']}")
            found = True
            break
    if found:
        break
