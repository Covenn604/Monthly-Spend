# Monthly Spend

A small, self-hosted spending tracker for one household. See what came in, what went out, and which categories cost more than usual—without assigning every dollar to a budget.

**Version 0.2.0 — initial functional prototype.** Desktop and mobile web interface; manual transactions and CSV import; one shared household password and one currency (CAD by default). Data lives in SQLite on your Docker host, not in GitHub or browser storage. No bank connections, external analytics, or runtime CDNs.

## Run with Docker Compose

Install Docker with the Compose plugin on your server, then:

```bash
git clone https://github.com/Covenn604/Monthly-Spend.git
cd Monthly-Spend
cp .env.example .env
```

Edit `.env` and set `APP_PASSWORD` to a unique password of at least 12 characters. Do not commit this file. Then:

```bash
docker compose pull
docker compose up -d
```

Open **http://YOUR-SERVER-IP:8085** from a computer or phone on your home network and sign in with that password. The first installation needs access to GitHub Container Registry (GHCR) to download the image. The application has no third-party Python or JavaScript dependencies.

The `docker-publish.yml` workflow builds and publishes `ghcr.io/covenn604/monthly-spend` on pushes to `main`, or through **Actions → Build and Publish Docker Image → Run workflow**. It runs the Python tests and JavaScript syntax check before publishing `latest`, `0.2.0`, and a `sha-…` tag. Wait for a successful publish before the first pull. GitHub source changes do not update your running container automatically.

Images target **linux/amd64** (Intel/AMD servers). The workflow uses the built-in `GITHUB_TOKEN`; no custom registry secret is needed. GHCR packages can initially be private even for a public repository. For unauthenticated pulls from your home server, change the `monthly-spend` package visibility to public in GitHub package settings; otherwise authenticate your server to GHCR with an account/token allowed to read that package.

To build locally instead, run `docker build -t monthly-spend:local .`, set `APP_IMAGE=monthly-spend:local` in `.env`, and run `docker compose up -d` without the pull step.

### Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PASSWORD` | Required | Shared household password, at least 12 characters. |
| `APP_IMAGE` | `ghcr.io/covenn604/monthly-spend:latest` | Container image. Use `:0.2.0` for the current version tag or a published `:sha-…` tag for a specific source revision. |
| `APP_PORT` | `8085` | Published server port. |
| `PUID` | `10001` | Numeric UID used to run the container process. |
| `PGID` | `10001` | Numeric primary GID used to run the container process. |
| `CURRENCY` | `CAD` | Display currency, e.g. CAD or USD. All accounts must use the same currency; no exchange conversion. Choose before entering data. |
| `TZ` | `America/Vancouver` | Server timezone used for the current reporting day. |
| `COOKIE_SECURE` | `false` | Set `true` when using HTTPS through a reverse proxy. |

The database is `/data/monthly-spend.sqlite3` inside the container, persisted in the `monthly-spend-data` named volume. Docker Compose prefixes the volume name with the project name. The app defaults to UID/GID **10001:10001**, configurable through `PUID` and `PGID`. To use a host directory, replace `monthly-spend-data:/data` with `/your/path:/data` and make that directory and any existing database/journal files writable by the selected user/group. Keep the same volume when updating.

### Container user and data-folder permissions

Compose sets the actual process identity using:

```yaml
user: "${PUID:-10001}:${PGID:-10001}"
```

Set `PUID` and `PGID` in `.env`, or in **Portainer → Stack → Environment variables**, then redeploy the stack. For example, to run under host user/group 1000:

```dotenv
PUID=1000
PGID=1000
```

Choose IDs that have access to your host directory. Check its numeric owner and group with:

```bash
ls -ldn /mnt/array/appsdata/monthly_spend/data
```

Changing these values changes the process identity; it does **not** change ownership or ACLs on existing files or volumes. A new named volume is initially owned by the image's default UID/GID 10001:10001, so using a different identity requires preparing its permissions too. Keep the defaults for an unchanged named-volume installation unless you also update volume permissions.

For a dedicated Monthly Spend bind-mount directory, stop the app before adjusting permissions. For example, if you selected 1000:1000:

```bash
sudo mkdir -p /mnt/array/appsdata/monthly_spend/data
sudo chown -R 1000:1000 /mnt/array/appsdata/monthly_spend/data
sudo chmod 750 /mnt/array/appsdata/monthly_spend/data
```

Use a directory dedicated to Monthly Spend; do not change ownership of another application's data directory. On hosts with filesystem ACLs, ensure the selected identity has directory traversal and read/write access through those ACLs as well. Existing database files need read/write permission. No image rebuild is needed for this Compose setting. If launching with `docker run`, the equivalent is `--user 1000:1000`; simply passing `PUID`/`PGID` as container environment variables does not change the image's user.

### Portainer

After the first successful publish, open **Stacks → Add stack** and paste `compose.yaml`. Set `APP_PASSWORD` in the stack environment, then deploy. No local build is required. If the GHCR package is private, configure registry credentials in Portainer first, or make the package public for unauthenticated pulls. To update, redeploy the same stack with the option to pull the image again enabled, keeping its data volume unchanged.

## First use

1. Open **Accounts & categories** and add each bank account and credit card.
2. Set the opening balance to the account balance immediately before the earliest transaction you will enter/import. Card debt is negative. To backfill older history later, first plan the corresponding opening-balance adjustment; account editing is not implemented in this prototype.
3. Add any categories you need. Default categories are included; there are no demo financial records.
4. Enter transactions manually or import a statement.
5. Choose the statement month at the top. The overview shows income, net expenses, and surplus/deficit. Click a category to inspect its transactions.

Amounts are stored as integer cents. Enter positive amounts for manual expenses, income, refunds, and new transfers; the selected type determines the sign. When editing an imported transfer, the form displays its signed amount.

Account balances include the opening balance plus **all entered transactions**, including future-dated entries. They are ledger balances, not live bank balances or reconciled balances.

## Search and categorize across months

Open **Transactions**, set **Date range → All transactions**, and search by payee/merchant name. Search also matches notes and account names, across all recorded months. The category filter can narrow the list further, including **Uncategorized**. Choose **Selected month** to return to monthly browsing. Clicking a category in the monthly overview opens that month's transactions.

Check individual expense/refund rows, or use the header checkbox to select every matching expense/refund. Choose a category and click **Apply to selected**. Confirm the number of records to replace their existing categories in one operation. Choose **Uncategorized** to clear assignments. Income and transfers are excluded because they do not use spending categories. Amounts, dates, payees, notes, and transfer links stay unchanged.

Selections clear when the search, category, or date range changes, or after records refresh. Up to 5,000 transactions can be categorized in a single operation. The all-transactions view loads recorded history into the browser, so very large histories may take longer to display. Editing/deleting a transaction also works across months. Merchant rules can categorize future purchases; bulk categorization updates the selected existing records only.

## CSV import

Use a UTF-8 CSV with a header, at most 5,000 data rows, and a file size below 2 MB. Comma, semicolon, and tab delimiters are supported, including quoted fields and a UTF-8 BOM. Other encodings must be converted to UTF-8 first.

1. Select the destination account and upload the CSV.
2. Map the date and description columns.
3. Map one signed amount column, or separate debit and credit columns.
4. Select the exact date format: `YYYY-MM-DD`, `DD/MM/YYYY`, or `MM/DD/YYYY`.
5. Choose decimal-comma mode if needed. Parentheses are accepted for negative amounts.
6. For credit-card exports with positive purchase amounts, use **Reverse amount signs**. Final negative amounts are money out; positive amounts are money in. Separate debit/credit mode uses credit minus debit and ignores this reversal setting.
7. Map a stable bank transaction ID/reference if available. Do not use a statement ID shared by multiple rows.
8. Preview, inspect types and categories, select rows, and confirm the import.

Save the mapping under a format name to reuse it. Saved mappings use column positions; check them when your bank changes its export format. Positive rows default to income: change purchase returns to **Refund**, and account movements or credit-card payments to **Transfer**.

### Duplicate detection

- A matching imported ID within the same account is blocked, including repeated IDs in the file.
- A matching date, signed amount, and normalized payee is a **possible duplicate**, unchecked by default. You may select it to affirm it is a distinct purchase.
- Invalid rows are excluded with a reason.
- Imports run in one database transaction. Matches are checked again when committing. A changed match can require a fresh preview.
- A preview expires after one hour and cannot be committed twice.

No fuzzy date matching is attempted. Changing a payee or date may prevent a possible-duplicate match. No automated method can prove two identical purchases are the same transaction without a reliable bank ID.

Use **Undo this import** on the completion panel to remove the imported batch, including later edits to those rows. That shortcut is available in the current page session; after leaving/reloading, use transaction deletion. Deleted imported IDs can be imported again.

### Transfers and card payments

For a new manual transfer, select source and destination accounts. The app creates linked opposing entries; deleting one deletes both. To change a linked transfer, delete and recreate it.

For imported transfers, mark the entry as **Transfer** on each account. The app does not generate a second entry or automatically pair imported rows. If only one account is tracked, mark its movement as Transfer and no counterpart is required. To reclassify an existing imported payment, edit its type; the form keeps the original sign when switching to Transfer.

Card purchases remain expenses. Card bill payments are transfers, preventing double-counting.

## How comparisons work

- **Income:** transactions marked Income.
- **Net expenses:** expenses minus refunds. Transfers are excluded.
- **Left over / Over income:** recorded income minus net expenses. This is not a safe-to-spend forecast and does not reserve upcoming bills.
- **Usual category spending:** mean net expense across the prior three calendar months, excluding months earlier than the earliest recorded non-transfer transaction. Zero-spend months after that starting month count as zero. Partial or missing history can distort the average; the comparison lists the months used.
- **Current month:** overview includes entries through the server's current day. Historical category comparisons use that same day-of-month, capped at the earlier month's last day. Future-dated transactions remain visible in the transaction list.
- **Past months:** full-month comparison. The six-month chart shows full earlier months and month-to-date for the current month; it is separate from the same-day category baseline.
- **Above usual** indicates increased spending, not a judgment that the category is unaffordable. Overall overspending means expenses exceed recorded income.

Merchant rules apply to new manual entries without an explicit category and to newly previewed expense imports. Matching is case-insensitive, first rule wins. Rules do not modify prior transactions.

## Backups and updates

The transaction CSV export is useful for analysis, but is **not a full backup**: it does not include account opening balances, saved mappings, merchant rules, or linked-transfer identity. Spreadsheet formula-like text is prefixed with an apostrophe in exports. Generic import mapping does not automatically restore every exported field.

For a full backup, stop the app and copy its database to the server:

```bash
docker compose stop
mkdir -p backups
docker cp monthly-spend:/data/monthly-spend.sqlite3 ./backups/monthly-spend.sqlite3
docker compose start
```

Keep dated copies of backups outside the source checkout, or move `backups` elsewhere. The `.gitignore` excludes database files. If using a filesystem snapshot rather than the command above, stop the container and capture the **entire data directory**, including any SQLite journal files.

To restore, stop the container, replace the database in the data volume with your backed-up database, remove stale `monthly-spend.sqlite3-wal` and `monthly-spend.sqlite3-shm` files from the stopped volume if present, ensure the configured `PUID`/`PGID` owns the restored database, then start the container. Test restoration on a separate copy before relying on a backup.

To update after taking a backup:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
```

Do not run `docker compose down -v` unless you intend to delete your data. The initial schema is created automatically; future releases that change it will need migration handling.

## Access and limits

This is a **LAN-first household prototype**, using Python's standard-library HTTP server. It is not designed as a public multi-tenant service. Keep it on a trusted home network; for remote access use your VPN or an HTTPS reverse proxy. Plain HTTP does not encrypt the password or financial data in transit. The database itself is not encrypted; protect the host and backups.

Sessions last 12 hours and are cleared on server restart. Cookies are HttpOnly and SameSite=Strict; write APIs require a custom same-origin header; no cross-origin API access is enabled. Login attempts are rate-limited per source IP. Source code can be public without exposing local data; never upload statements, `.env`, or database backups to the repository.

Not included yet: bank sync, multi-currency conversion, transaction splits, recurring-bill forecasting, account/category editing or deletion, reconciliation, separate user profiles, category limits, or automatic transfer pairing. The initial UI is responsive, but browser interaction/visual testing has not yet been performed.

## Development and checks

Python 3.12+ is sufficient to run the app. Set `APP_PASSWORD` and optionally `DATA_DIR`, then `python app.py`. The default local port is 8080. No dependency installation is required.

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover integer-money parsing, refunds/transfers, historical and partial-month comparisons, CSV mapping, duplicate selection and replay protection, atomic rollback, login, CRUD, exports, and persistence. `checks.yml` builds and smoke-tests the Docker image; `docker-publish.yml` separately runs the Python tests and JavaScript check before building and publishing to GHCR. No sample statements or personal financial data are committed.
