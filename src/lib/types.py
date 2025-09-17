from typing import TypedDict


class TransactionConfig(TypedDict):
    to: str
    function_signature: str
    value: str
    args: list[any]
    gas_estimate: int


class MintBotConfig(TypedDict):
    rpc_url: str
    relay_url: str
    block_time: int
    bot_keystore: str
    auth_keystore: str
    target_timestamp: int
    priority_fee: int
    transactions: list[TransactionConfig]
