powershell
py -3 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt


9229840385:AAGwuuPvKKwegdw10yO2yu_AxRCXJDvxioQ.example
powershell
Copy-Item .env.example .env
BOT_TOKEN=9229840385:AAGwuuPvKKwegdw10yO2yu_AxRCXJDvxioQ
NFT_IMAGE_URL=https://example.com
DATABASE_PATH=offers.sqlite3
OFFER_TTL_HOURS=8
powershell
python bot.py
