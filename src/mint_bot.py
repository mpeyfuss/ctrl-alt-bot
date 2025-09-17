import json
import os
import tomllib
from time import time, sleep
from dotenv import load_dotenv
import questionary
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3
from web3.exceptions import TransactionNotFound

from src.lib.flashbots import FlashbotsWeb3, flashbot
from src.lib.foundry import build_calldata
from src.lib.types import MintBotConfig

load_dotenv()


def mint_bot():
    # Setup bot
    with open(os.environ.get("CONFIG_FILE"), "rb") as f:
        config: MintBotConfig = tomllib.load(f)

    bot_keystore_pw = os.environ.get("BOT_KEYSTORE_PW")
    if not bot_keystore_pw:
        bot_keystore_pw = questionary.password("Enter the bot keystore password:").ask()

    with open(config["bot_keystore"], "r") as bot_keystore:
        bot_pk = Account.decrypt(json.load(bot_keystore), bot_keystore_pw)
        bot_account: LocalAccount = Account.from_key(bot_pk)
        questionary.print(f"Bot Loaded: {bot_account.address}", style="fg:green")

    auth_keystore_pw = os.environ.get("AUTH_KEYSTORE_PW")
    if not auth_keystore_pw:
        auth_keystore_pw = questionary.password(
            "Enter the flashbots auth keystore password:"
        ).ask()
    with open(config["auth_keystore"], "r") as auth_keystore:
        auth_pk = Account.decrypt(json.load(auth_keystore), auth_keystore_pw)
        auth_account: LocalAccount = Account.from_key(auth_pk)
        questionary.print(
            f"Auth Account Loaded: {auth_account.address}", style="fg:green"
        )

    w3: FlashbotsWeb3 = Web3(HTTPProvider(config["rpc_url"]))
    flashbot(w3, auth_account, config["relay_url"])

    # Wait until ~2 blocks prior
    now = int(time())
    seconds_until_execution = (
        config["target_timestamp"] - now - 2 * config["block_time"]
    )
    if seconds_until_execution > 0:
        questionary.print(
            f"Sleeping {seconds_until_execution} seconds...", style="fg:yellow"
        )
        sleep(seconds_until_execution)

    # Get gas data
    questionary.print("Getting gas data...", style="fg:gray")
    latest_block = w3.eth.get_block("latest")
    base_fee = int(latest_block["baseFeePerGas"] * 1.25)
    network_priority_fee = w3.eth.max_priority_fee
    priority_fee = w3.to_wei(config["priority_fee"], "gwei")
    if priority_fee < network_priority_fee:
        priority_fee = network_priority_fee
    max_fee_per_gas = 2 * base_fee + priority_fee

    # Build transaction data
    questionary.print("Building transactions...", style="fg:gray")
    nonce = w3.eth.get_transaction_count(bot_account.address)
    txs = []
    for i, transaction in enumerate(config["transactions"]):
        tx_data = build_calldata(transaction["function_signature"], transaction["args"])
        tx_value = transaction["value"].split(" ")
        tx = {
            "to": w3.to_checksum_address(transaction["to"]),
            "data": tx_data,
            "value": w3.to_wei(tx_value[0], tx_value[1]),
            "gas": transaction["gas_estimate"],
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": priority_fee,
            "nonce": nonce + i,
            "chainId": w3.eth.chain_id,
        }
        txs += [tx]

    # Create the bundle
    questionary.print("Creating bundle...", style="fg:gray")
    signed_txs = [
        w3.eth.account.sign_transaction(tx, private_key=bot_account.key) for tx in txs
    ]
    bundle = [{"signed_transaction": tx.rawTransaction} for tx in signed_txs]

    # Submit the bundle for the next 2 blocks
    submit_bundle = True
    while submit_bundle:
        questionary.print("Submitting bundle for the next 3 blocks...", style="fg:gray")
        block = w3.eth.block_number
        bundle_results = []
        for i in range(1, 4):
            bundle_result = w3.flashbots.send_bundle(
                bundle,
                target_block_number=block + i,
            )
            bundle_results += [bundle_result]

        # Check bundle statuses
        questionary.print("Checking bundle submissions...", style="fg:gray")
        for bundle_result in bundle_results:
            bundle_result.wait()
            try:
                receipts = bundle_result.receipts()
                questionary.print("🚀 Bundle Included!", style="fg:lime")
                questionary.print(
                    f"🔗 Block: {receipts[0].blockNumber}", style="fg:magenta"
                )
                questionary.print(
                    f"🫆 Transaction Hashes: {[r.transactionHash.hex() for r in receipts]}",
                    style="fg:cyan",
                )
                submit_bundle = False
                break
            except TransactionNotFound:
                questionary.print(
                    "❌ Bundle not found.",
                    style="fg:red",
                )
