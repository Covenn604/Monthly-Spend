# Spearmint

**Know where your money goes.**

Inspired by Mint. An independent, self-hosted spending tracker focused on understanding your monthly expenses. Spearmint is not affiliated with Intuit. See what came in, what went out, and which categories cost more than usual—without assigning every dollar to a budget.

**Version 0.4.2 — initial functional prototype.** Desktop and mobile web interface; manual transactions and CSV import; separate user logins and private financial records; one server-wide currency (CAD by default). Data lives in SQLite on your Docker host, not in GitHub or browser storage. No bank connections, external analytics, or runtime CDNs.

## Run with Docker Compose

Install Docker with the Compose plugin on your server, then:

```bash
git clone https://github.com/Covenn604/spearmint.git
cd spearmint
cp .env.example .env
```

Edit `.env` and set `APP_PASSWORD` to a unique password of at least 12 characters. Do not commit this file. Then:

```bash
docker compose pull
docker compose up -d
```

Open **http://YOUR-SERVER-IP:8085** from a computer or phone on your home network and sign in with username **admin** (or your configured `ADMIN_USERNAME`) and that password on first setup. The first installation needs access to GitHub Container Registry (GHCR) to download the image. The application has no third-party Python or JavaScript dependencies.

The `docker-publish.yml` workflow builds and publishes `ghcr.io/covenn604/spearmint` on pushes to `main`, or through **Actions → Build and Publish Docker Image → Run workflow**. It runs the Python tests and JavaScript syntax check before publishing `latest`, `0.4.2`, and a `sha-…` tag. Wait for a successful publish before the first pull. GitHub source changes do not update your running container automatically.

Images target **linux/amd64** (Intel/AMD servers). The workflow uses the built-in `GITHUB_TOKEN`; no custom registry secret is needed. GHCR packages can initially be private even for a public repository. For unauthenticated pulls from your home server, change the `spearmint` package visibility to public in GitHub package settings; otherwise authenticate your server to GHCR with an account/token allowed to read that package.

To build locally instead, run `docker build -t spearmint:local .`, set `APP_IMAGE=spearmint:local` in `.env`, and run `docker compose up -d` without the pull step.

### Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PASSWORD` | Required | Initial administrator password, at least 12 characters. Used only when the user database is first created. Changing it later does not reset a stored password. |
| `ADMIN_USERNAME` | `admin` | Initial administrator username; used only on first multi-user startup. |
| `APP_IMAGE` | `ghcr.io/covenn604/spearmint:latest` | Container image. Use `:0.4.2` for the current version tag or a published `:sha-…` tag for a specific source revision. |
| `APP_PORT` | `8085` | Published server port. |
| `PUID` | `10001` | Numeric UID used to run the container process. |
| `PGID` | `10001` | Numeric primary GID used to run the container process. |
| `CURRENCY` | `CAD` | Display currency, e.g. CAD or USD. All accounts must use the same currency; no exchange conversion. Choose before entering data. |
| `TZ` | `America/Vancouver` | Server timezone used for the current reporting day. |
| `COOKIE_SECURE` | `false` | Set `true` when using HTTPS through a reverse proxy. |

The original administrator’s financial database remains `/data/monthly-spend.sqlite3`. Login records and password hashes are in `/data/users.sqlite3`; other users’ financial databases are under `/data/users/<numeric-id>/monthly-spend.sqlite3`. All are persisted in the existing `monthly-spend-data` named volume. Docker Compose prefixes the volume name with the project name. The app defaults to UID/GID **10001:10001**, configurable through `PUID` and `PGID`. To use a host directory, replace `monthly-spend-data:/data` with `/your/path:/data` and make that directory and any existing database/journal files writable by the selected user/group. Keep the same volume when updating.

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

For a dedicated Spearmint bind-mount directory, stop the app before adjusting permissions. For example, if you selected 1000:1000:

```bash
sudo mkdir -p /mnt/array/appsdata/monthly_spend/data
sudo chown -R 1000:1000 /mnt/array/appsdata/monthly_spend/data
sudo chmod 750 /mnt/array/appsdata/monthly_spend/data
```

Use a directory dedicated to Spearmint; do not change ownership of another application's data directory. On hosts with filesystem ACLs, ensure the selected identity has directory traversal and read/write access through those ACLs as well. Existing database files need read/write permission. No image rebuild is needed for this Compose setting. If launching with `docker run`, the equivalent is `--user 1000:1000`; simply passing `PUID`/`PGID` as container environment variables does not change the image's user.

### Portainer

After the first successful publish, open **Stacks → Add stack** and paste `compose.yaml`. Set `APP_PASSWORD` in the stack environment, then deploy. No local build is required. If the GHCR package is private, configure registry credentials in Portainer first, or make the package public for unauthenticated pulls. To update, redeploy the same stack with the option to pull the image again enabled, keeping its data volume unchanged.

## Repository and Docker package migration (v0.4.1)

- Repository: `https://github.com/Covenn604/spearmint`
- Image: `ghcr.io/covenn604/spearmint:latest` (or `:0.4.1`)
- The workflow publishes a new `spearmint` package; it does not move or delete the old `monthly-spend` package. Existing old-image installations keep running, but must switch image names to receive future releases.

For an existing Portainer stack, edit **only its image** to `ghcr.io/covenn604/spearmint:latest`, or change the stack's `APP_IMAGE` variable if configured. Keep the existing stack name, service name, container name, `/data` mount, password settings, and UID/GID settings. Redeploy with the option to pull the image again. For a bind mount, keep your exact host directory. Do not create a fresh stack with a different named volume.

For a Git/Compose installation:

```bash
git remote set-url origin https://github.com/Covenn604/spearmint.git
git pull --ff-only
```

Change any existing `.env` entry to `APP_IMAGE=ghcr.io/covenn604/spearmint:latest`, then run `docker compose pull` and `docker compose up -d`. Updating `.env.example` does not update your real `.env` file. Keep any existing `COMPOSE_PROJECT_NAME` or `-p` override unchanged. The supplied Compose file explicitly defaults to project name `monthly-spend`, so renaming the checkout directory to `spearmint` does not change the original default volume name. If you previously used a different inferred project name, pass that same name with `docker compose -p YOUR_EXISTING_PROJECT …` or set `COMPOSE_PROJECT_NAME`.

The GHCR package may initially be private; configure GHCR credentials in Portainer or set the new package's visibility to public for unauthenticated pulls. Back up the complete data directory before migrating. No financial database migration is needed for the repository/image rename.

## Upgrade from Monthly Spend / multi-user setup

The app and repository are now **Spearmint**, and v0.4.1 publishes to `ghcr.io/covenn604/spearmint`. The Compose service/container name, data-volume key, and database filenames retain their original names to preserve installations. Keep your current data mount, stack/project name, and `PUID`/`PGID`. Follow the package migration instructions below when upgrading from the former image.

On the first v0.3.0 startup, the app creates an administrator login named **admin** (or `ADMIN_USERNAME`) using your existing `APP_PASSWORD`. That account retains your existing accounts, transactions, categories, rules, CSV formats and import records without copying or moving the original financial database. Existing sessions end on restart. The login screen now requires a username as well as a password.

Open **Profile & users** to:

- Change your own password (requires the current password).
- As administrator, create users with initial passwords and private, empty finances.
- As administrator, reset another user's password, disable their login, or enable it again. Disabling preserves their data; the administrator cannot disable itself.

Usernames are case-insensitive and contain 3–40 letters, numbers, dots, underscores or hyphens. Passwords require 12–1,024 characters and are stored as salted PBKDF2-SHA256 hashes, not plaintext. Changes and account disabling invalidate existing sessions. Give new users their credentials privately and have them change their password. There is no public registration or email-based password recovery. Once initialized, environment changes to `APP_PASSWORD` or `ADMIN_USERNAME` do not override stored credentials.

Each user gets isolated accounts, categories, merchant rules, CSV formats/previews, transactions, and exports. Financial API requests use the authenticated user's database, not a user ID provided by the browser. The administrator can manage logins but does not have a UI to browse another user's finances. The server owner and administrators who can reset passwords remain trusted; this is not encryption against the host administrator. Shared household workspaces are not implemented in this version. The currency and server timezone are shared deployment settings.

## First use

1. Open **Accounts & categories** and add each bank account and credit card.
2. Set the opening balance to the account balance immediately before the earliest transaction you will enter/import. Card debt is negative. To backfill older history later, first plan the corresponding opening-balance adjustment. Use **Edit opening balance** on the existing account to apply it.
3. Add any categories you need. Default categories are included; there are no demo financial records. Click a category’s **Edit** button to rename or delete it.
4. Enter transactions manually or import a statement.
5. Choose the statement month at the top. The overview shows income, net expenses, and surplus/deficit. Click a category to inspect its transactions.

Amounts are stored as integer cents. Enter positive amounts for manual expenses, income, refunds, and new transfers; the selected type determines the sign. When editing an imported transfer, the form displays its signed amount.

**Overview → Account balances** shows each account’s balance, its opening balance, and the net recorded activity. This uses the same balance calculation as Accounts & categories, refreshes after transaction changes/imports, and is independent of the selected reporting month. Only the signed-in user’s accounts are shown.

Account balances include the opening balance plus **all entered transactions**, including future-dated entries. They are ledger balances, not live bank balances or reconciled balances.

## Change an account opening balance

Open **Accounts & categories** and choose **Edit opening balance** beside an account. Enter the corrected amount; the dialog previews the resulting balance using the currently loaded recorded activity. Save to update the account and overview. All existing transactions, imports, and monthly income/expense totals stay unchanged. The update affects only the signed-in user's account.

For historical accuracy, use the balance immediately before the first entered transaction (negative for credit card debt). If you intentionally want a balancing adjustment, the required opening balance is **target signed balance minus net recorded activity**. This makes the ledger match the target but does not identify missing or duplicate transactions. The preview may change if transactions are added elsewhere before saving.

## Edit and delete categories

In **Accounts & categories**, click a category's **Edit** button. Renaming preserves its identity, so existing transactions and merchant rules show the new name automatically.

Unused categories can be deleted directly from the dialog. For a category in use, choose a replacement; its transactions and merchant rules move in the same database operation before the old category is removed. **Uncategorized** keeps transactions but clears their category. If merchant rules still use the category, choose a real replacement or remove those rules first. Transactions are never deleted by category deletion, and financial amounts are unchanged. Preview your CSV again after changing categories.

Changes affect only the signed-in user's categories. Deleted default categories do not reappear on a later login.

## Search and categorize across months

Open **Transactions**, set **Date range → All transactions**, and search by payee/merchant name. Search also matches notes and account names, across all recorded months. By default, **All transactions** shows only expenses and refunds without a category. Categorized records, income, and transfers are hidden from this cleanup list. Newly categorized records disappear from the list after saving. Enable **Show categorized, income and transfers** to review all records and use the category filter. This only filters the view; no records are deleted. Choose **Selected month** to return to monthly browsing. Clicking a category in the monthly overview opens that month's transactions.

Check individual expense/refund rows, or use the header checkbox to select every matching expense/refund. Choose a category and click **Apply to selected**. Confirm the number of records to replace their existing categories in one operation. Choose **Uncategorized** to clear assignments. Income and transfers are excluded because they do not use spending categories. Amounts, dates, payees, notes, and transfer links stay unchanged.

Selections clear when the search, category, or date range changes, or after records refresh. Up to 5,000 transactions can be categorized in a single operation. The all-transactions view loads recorded history into the browser, so very large histories may take longer to display. Editing/deleting a transaction also works across months. Merchant rules can categorize future purchases; bulk categorization updates the selected existing records only.

## CSV import

Use a UTF-8 CSV with a header, at most 5,000 data rows, and a file size below 2 MB. Comma, semicolon, and tab delimiters are supported, including quoted fields and a UTF-8 BOM. Other encodings must be converted to UTF-8 first.

1. Select the destination account and upload the CSV.
2. Set **Lines to skip before the header** for introductory content; count physical lines, including blank lines. Zero uses the first nonblank row as the header. Then map the date and description columns.
3. Map one signed amount column, or separate debit and credit columns.
4. Select the exact date format: `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYYMMDD`, `YYYY/MM/DD`, `DD-MM-YYYY`, or `MM-DD-YYYY`. Compact dates must have exactly eight digits.
5. Choose decimal-comma mode if needed. Parentheses are accepted for negative amounts.
6. For credit-card exports with positive purchase amounts, use **Reverse amount signs**. Final negative amounts are money out; positive amounts are money in. Separate debit/credit mode uses credit minus debit and ignores this reversal setting.
7. Map only date, description, and amounts. Extra fields (including transaction references, account numbers and row numbers) are ignored. Older profiles with an Imported ID mapping will no longer import that column.
8. Preview, inspect types and categories, select rows, and confirm the import.

Save the mapping under a format name to reuse it, including skipped header lines, date format, and your chosen sign setting. Saved mappings use column positions; check them when your bank changes its export format. Positive rows default to income: change purchase returns to **Refund**, and account movements or credit-card payments to **Transfer**.

### Duplicate detection

- New CSV imports ignore source IDs and use date, signed amount, and normalized payee for possible-duplicate checks. Legacy imported IDs already stored in the database remain unchanged.
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

When no explicit rule matches, Spearmint now learns from existing categorized expenses belonging to the signed-in user. New purchases with the same full merchant description inherit the category when all categorized expense history for that merchant agrees. Matching ignores case and repeated/leading/trailing whitespace; it does not merge different store numbers or locations. Conflicting history stays uncategorized for review. Manual and bulk category assignments both contribute to this history. Explicit merchant rules take priority. Income, transfers, and refunds do not train the expense-history lookup. Positive CSV rows still default to income and need review for refunds/transfers.

Suggestions appear in the import preview and can be overridden or cleared before import. Renames and category reassignment are reflected in future suggestions. Existing transactions are not changed automatically. The history lookup is built once per preview and is private to each user.

## Backups and updates

The transaction CSV export is useful for analysis, but is **not a full backup**: it does not include account opening balances, saved mappings, merchant rules, or linked-transfer identity. Spreadsheet formula-like text is prefixed with an apostrophe in exports. Generic import mapping does not automatically restore every exported field.

For a full backup, stop the app and copy the **entire `/data` directory**, including the user database, all per-user subdirectories, and any SQLite journal files. For example, using a dedicated backup directory on your server:

```bash
docker compose stop
mkdir -p /your/backup/path/spearmint
docker cp monthly-spend:/data/. /your/backup/path/spearmint/
docker compose start
```

Replace `/your/backup/path/spearmint` with a real location outside the source checkout and use a separate dated directory for each backup. Copying only `monthly-spend.sqlite3` is no longer a full backup: it omits logins and other users' finances.

To restore, stop the container and restore the complete backed-up data directory to the data volume, ensuring the configured `PUID`/`PGID` has read/write access. Do not combine a backed-up user database with unrelated per-user directories or leave journal files from a different database state. Preserve the directory structure and test restoration on a separate copy first.

To update after taking a backup:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
```

Do not run `docker compose down -v` unless you intend to delete your data. The initial schema is created automatically; future releases that change it will need migration handling.

## Access and limits

This is a **LAN-first personal-finance prototype**, using Python's standard-library HTTP server. It is not designed as a public multi-tenant service. Keep it on a trusted home network; for remote access use your VPN or an HTTPS reverse proxy. Plain HTTP does not encrypt the password or financial data in transit. The database itself is not encrypted; protect the host and backups.

Sessions last 12 hours and are cleared on server restart. Cookies are HttpOnly and SameSite=Strict; write APIs require a custom same-origin header; no cross-origin API access is enabled. Login attempts are rate-limited per source IP. Source code can be public without exposing local data; never upload statements, `.env`, or database backups to the repository.

Not included yet: bank sync, multi-currency conversion, transaction splits, recurring-bill forecasting, account deletion, reconciliation, shared household workspaces, category limits, or automatic transfer pairing. The initial UI is responsive, but browser interaction/visual testing has not yet been performed.

## Development and checks

Python 3.12+ is sufficient to run the app. Set `APP_PASSWORD` and optionally `DATA_DIR`, then `python app.py`. The default local port is 8080. No dependency installation is required.

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover integer-money parsing, refunds/transfers, historical and partial-month comparisons, CSV mapping, duplicate selection and replay protection, atomic rollback, login, CRUD, exports, persistence, multi-user isolation, session invalidation, administrator authorization, and category reassignment/deletion. `checks.yml` builds and smoke-tests the Docker image; `docker-publish.yml` separately runs the Python tests and JavaScript check before building and publishing to GHCR. No sample statements or personal financial data are committed.

## v0.4.0 changes

- Preselect import categories from consistent prior expense classifications, after explicit merchant rules.
- Put account balance descriptions on a separate line below account names.
- Replace the letter badge with an original white spearmint-leaf mark on login and navigation.

## v0.4.2 changes

CSV import supports skipped introductory lines and additional date formats. Only selected date, description, and amount/debit/credit fields are imported. Sign reversal remains an explicit user choice. Account-to-profile automatic selection remains queued separately in issue #4.
