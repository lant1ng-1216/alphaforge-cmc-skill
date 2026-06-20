"""
AlphaForge — ERC-8004 Agent Identity Registration on BNB Chain

Contract: 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432 (8004: Identity Registry)
Network:  BNB Chain Mainnet (chainId 56)

Usage:
    pip install web3
    export WALLET_PRIVATE_KEY=0x...
    python scripts/register_erc8004.py
"""

import json
import base64
import os

REGISTRY_ADDRESS = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
BNB_RPC = "https://bsc-dataseed2.binance.org/"

REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "agentURI", "type": "string"},
            {
                "components": [
                    {"internalType": "string", "name": "metadataKey", "type": "string"},
                    {"internalType": "bytes",  "name": "metadataValue", "type": "bytes"},
                ],
                "internalType": "struct IdentityRegistryUpgradeable.MetadataEntry[]",
                "name": "metadata",
                "type": "tuple[]",
            },
        ],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

AGENT_METADATA = {
    "name": "alphaforge-strategy-skill",
    "description": (
        "Quantopian-style crypto strategy generation Skill powered by CoinMarketCap. "
        "Converts natural-language trading ideas into structured, backtestable strategy "
        "specifications with live CMC data, 8-regime market classifier, 365-day backtest, "
        "walk-forward consistency check, and CMC Data MCP cross-validation."
    ),
    "version": "1.0.0",
    "endpoints": [
        {"type": "github", "url": "https://github.com/lant1ng-1216/alphaforge-cmc-skill"}
    ],
    "tags": ["strategy", "crypto", "backtest", "bnb-chain", "cmc", "quantitative"],
}


def build_agent_uri(metadata: dict) -> str:
    encoded = base64.b64encode(
        json.dumps(metadata, separators=(",", ":")).encode()
    ).decode()
    return f"data:application/json;base64,{encoded}"


def register():
    try:
        from web3 import Web3
    except ImportError:
        print("web3 not installed. Run: pip install web3")
        return

    private_key = os.environ.get("WALLET_PRIVATE_KEY")
    if not private_key:
        print("Set WALLET_PRIVATE_KEY environment variable first.")
        print("Example: export WALLET_PRIVATE_KEY=0xyour_private_key_here")
        return

    w3 = Web3(Web3.HTTPProvider(BNB_RPC))
    if not w3.is_connected():
        print(f"Cannot connect to BNB RPC: {BNB_RPC}")
        return

    account = w3.eth.account.from_key(private_key)
    print(f"Wallet address: {account.address}")

    bnb_balance = w3.eth.get_balance(account.address)
    print(f"BNB balance:    {w3.from_wei(bnb_balance, 'ether'):.4f} BNB")

    if bnb_balance < w3.to_wei(0.001, "ether"):
        print("Balance too low — need at least 0.001 BNB for gas.")
        return

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(REGISTRY_ADDRESS),
        abi=REGISTRY_ABI,
    )

    agent_uri = build_agent_uri(AGENT_METADATA)
    metadata_tuples = [
        {
            "metadataKey": "built_with",
            "metadataValue": "https://github.com/lant1ng-1216/alphaforge-cmc-skill".encode("utf-8"),
        }
    ]

    print("\nRegistering AlphaForge on ERC-8004 registry...")
    print(f"  agentURI length: {len(agent_uri)} chars")

    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.functions.register(agent_uri, metadata_tuples).build_transaction(
        {
            "chainId": 56,
            "from": account.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("3", "gwei"),
        }
    )

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"\n  TX sent: {tx_hash.hex()}")
    print("  Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] == 1:
        print(f"\n  Registration successful!")
        print(f"  BscScan: https://bscscan.com/tx/{tx_hash.hex()}")
        print(f"\n  Add this to your README:")
        print(f"  On-Chain Identity: https://bscscan.com/tx/{tx_hash.hex()}")
    else:
        print(f"\n  Transaction failed. Check: https://bscscan.com/tx/{tx_hash.hex()}")


if __name__ == "__main__":
    register()
