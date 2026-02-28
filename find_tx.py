import requests

def find_failed_tx():
    api_key = "F65HKQKGEBHRPS4VXKVYMHDQ2MXCZ9RYG5"
    url = f"https://api.etherscan.io/api?module=proxy&action=eth_getBlockByNumber&tag=latest&boolean=true&apikey={api_key}"
    resp = requests.get(url).json()
    
    if "result" not in resp or not resp["result"]:
        return None
        
    transactions = resp["result"].get("transactions", [])
    print(f"Checking {len(transactions)} transactions in latest block...")
    
    for tx in transactions[:50]:  # Check first 50 txes
        tx_hash = tx["hash"]
        rcpt_url = f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionReceipt&txhash={tx_hash}&apikey={api_key}"
        try:
            r_resp = requests.get(rcpt_url).json()
            if r_resp.get("result", {}).get("status") == "0x0":
                print(f"FOUND FAILED TX: {tx_hash}")
                return tx_hash
        except:
            pass
            
    print("No failed transactions found in this batch.")
    return None

if __name__ == "__main__":
    find_failed_tx()
