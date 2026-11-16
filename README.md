# POD Bot: trends → designs → Printful → Etsy

From 9am to 5pm Eastern, every 40 minutes, this bot reads the news and Google Trends and
comes up with 2 product ideas (about 24 a day, 70% text designs, 30% illustrations). It sends each one to your phone on Telegram.
Tap **Approve** and it makes Printful product photos and lists the design on Etsy as a
t-shirt, hoodie, mug and sticker. When someone buys, it sends the order to Printful and
puts the tracking number back on Etsy. You never touch an order.

It runs for free on GitHub. Your computer doesn't need to be on.

```
News + Trends ──► Claude picks ideas ──► Claude safety check ──► Design files
                                                                    │
           Etsy listing ◄── Printful mockups ◄── You tap ✅ on Telegram
                │
  Customer buys ──► Printful prints + ships ──► Tracking sent to Etsy
```

---

## Setup (about 45 minutes, one time)

You'll collect a handful of keys (like passwords for the bot) and paste them into GitHub.
Keep a notes file open to hold them as you go.

### 1. Telegram bot (5 min)
1. In Telegram, open a chat with **@BotFather** and send `/newbot`. Pick any name.
2. BotFather replies with a **token** (looks like `123456:ABC-xyz...`). Save it as `TELEGRAM_BOT_TOKEN`.
3. Open a chat with your new bot and send it the message `hi`.
4. In a browser, go to `https://api.telegram.org/bot<YOUR TOKEN>/getUpdates`
   (paste your token where it says `<YOUR TOKEN>`). Find `"chat":{"id":` followed by a number.
   Save that number as `TELEGRAM_CHAT_ID`.

### 2. Claude API key (3 min)
1. Go to **console.anthropic.com** → API Keys → Create Key. Save it as `ANTHROPIC_API_KEY`.
2. Under Billing, add $10 of credit. The daily batch costs a few cents.

### 3. OpenAI API key, for illustrations (3 min)
1. Go to **platform.openai.com** → API keys → Create new secret key. Save as `OPENAI_API_KEY`.
2. Add $10 of credit under Billing. If it asks you to verify your organization
   (needed for image models), do that too.

### 4. Printful (5 min)
1. In Printful: **Stores → Add store → "Manual order platform / API"**. Name it "Etsy Bot".
   (This is separate from any Etsy connection you already have. Leave that one alone.
   Printful won't touch the bot's listings, because they aren't synced there.)
2. Go to **developers.printful.com → Your tokens → Create token**. Choose the "Etsy Bot"
   store and turn on every permission. Save it as `PRINTFUL_TOKEN`.
3. Make sure a payment card is on file in Printful (Billing). Printful charges you
   for each order when it goes into production.

### 5. Etsy shop settings (10 min)
In **Shop Manager → Settings**:
1. **Production partners** → Add a production partner → Printful. (Etsy requires this.)
2. **Delivery / Shipping** → create a shipping profile with rates close to Printful's
   (about $4.75 for a US tee). If you have more than one profile, the bot uses the first.
3. **Processing profiles** (if your shop has them) → make one that's "Made to order",
   2 to 5 days.

### 6. Etsy API app (10 min)
1. Go to **etsy.com/developers** → Create a new app → choose **Seller app** (own shop).
   Approval is usually instant.
2. In the app settings, add this callback URL: `http://localhost:3003/callback`
3. Save the **Keystring** as `ETSY_KEYSTRING` and the **Shared secret** as `ETSY_SHARED_SECRET`.
4. Connect it to your shop. On your Mac, open Terminal and run:
   ```
   cd ~/Downloads/pod-bot
   python3 scripts/etsy_connect.py
   ```
   Paste your keystring when asked, click **Allow access** in the browser, and copy the
   long token it prints. Save it as `ETSY_REFRESH_TOKEN`.
   (Or ask Claude to run this step for you on your computer.)

### 7. GitHub (10 min)
1. Create a new repository called `pod-bot`. Make it **Public**. Public is what lets
   Printful download the design files, and it keeps GitHub's runs free. Your keys stay
   hidden in Secrets.
2. Upload everything in this folder. On a Mac, press **Cmd + Shift + .** in Finder first
   so the hidden `.github` folder shows up and gets uploaded too.
3. Make a key that lets the bot keep its Etsy sign-in fresh:
   github.com → your photo → Settings → Developer settings → Personal access tokens →
   **Fine-grained tokens** → Generate. Repository access: only `pod-bot`.
   Permissions: **Secrets: Read and write**. Save it as `GH_PAT`.
4. In the repo: **Settings → Secrets and variables → Actions**.
   Under **Secrets**, add each of these by clicking "New repository secret":
   `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PRINTFUL_TOKEN`, `ETSY_KEYSTRING`,
   `ETSY_SHARED_SECRET`, `ETSY_REFRESH_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GH_PAT`
5. Under the **Variables** tab, add:
   - `DRY_RUN` = `true`
   - `SHOP_NAME` = your Etsy shop name

### 8. Turn it on
1. Open the **Actions** tab and click "I understand my workflows, go ahead and enable them".
2. Click **Check setup → Run workflow**. In a minute you'll get a Telegram message showing
   ✅ or ❌ for each connection. Fix any ❌ and run it again.
3. Click **POD bot → Run workflow**. Your first designs arrive on Telegram within a few minutes.

---

## Using it day to day

- Designs show up in Telegram through the workday. Tap **✅ Approve** or **❌ Skip**.
  Taps are picked up on the next run. Taps after 5pm are handled at 9am.
- Before approving, take 10 seconds to ask yourself whether the phrase or image could
  belong to someone. If you're not sure, search it on Etsy. The AI checks too, but you're
  the last line of defense against a trademark strike.
- Telegram commands: `/status`, `/more` (new batch now), `/pause`, `/resume`.

### Dry run → live
While `DRY_RUN` is `true`, the bot makes designs and Printful mockups but **doesn't post
anything to Etsy or place orders**. When the designs look good, change the `DRY_RUN`
variable to `false`. Anything you approved during the dry run goes live on the next run.

### Costs
- GitHub: free
- Claude: a few cents a day
- Illustrations: roughly 10 to 30 cents each
- Etsy: $0.20 per listing, so $0.80 per approved design (4 products), plus Etsy's usual sales fees
- Printful: charged per order, out of what the customer paid you

## Changing things
Everything adjustable is in `bot/settings.py`: products, prices and markups, colors,
working hours, designs per run, the text vs. illustration mix, fonts and news feeds. Edit it on
GitHub (pencil icon) and the change applies on the next run.

## Safety switches
| Setting | Where | What it does |
|---|---|---|
| `DRY_RUN` | GitHub variable | `true` = nothing posted to Etsy, no orders |
| `PUBLISH_LIVE` | GitHub variable | `false` = listings saved as Etsy drafts for you to review |
| `AUTO_CONFIRM_ORDERS` | GitHub variable | `false` = orders wait in Printful for you to confirm |
| `/pause` | Telegram | stops new designs; orders still get handled |

## What's in here
```
bot/run.py          main loop (9-5 Eastern, every 40 min)
bot/scout.py        reads trends, asks Claude for ideas, safety check
bot/render.py       typesets text designs, makes illustrations, builds print files
bot/designer.py     saves design files and sends previews to Telegram
bot/publisher.py    Printful mockups → Etsy listings with variations and pricing
bot/fulfillment.py  Etsy orders → Printful, tracking → Etsy
bot/check.py        setup tester
bot/settings.py     every adjustable setting
scripts/etsy_connect.py   one-time Etsy sign-in
fonts/              open-license fonts (SIL OFL), license files included
```
