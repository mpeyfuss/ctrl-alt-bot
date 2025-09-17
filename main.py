from questionary import select
from src.mint_bot import mint_bot

bot = select("Select which bot to run:", choices=["Mint Bot"]).ask()

match bot:
    case "Mint Bot":
        mint_bot()
