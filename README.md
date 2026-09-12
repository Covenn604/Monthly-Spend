# Spearmint

**Know where your money goes.**

Spearmint is a self-hosted spending tracker inspired by Mint. Record your transactions, see how much you spend each month, and find the categories where spending has increased—without maintaining an envelope budget.

Use it from a computer or phone on your home network. Import bank statements or enter transactions manually; your financial records stay on your server.

**Current version: 0.5.4** · [Docker image](https://github.com/Covenn604/spearmint/pkgs/container/spearmint) · [Report an issue](https://github.com/Covenn604/spearmint/issues)

Spearmint is an independent project and is not affiliated with Mint or Intuit. It is an early-stage application intended for personal use on a trusted network.

## What you can do

- **Understand monthly spending:** view income, net expenses, money left over, category comparisons, and a six-month trend.
- **Track account balances:** see opening balances plus recorded activity for bank accounts and credit cards.
- **Import CSV statements:** map the columns you need, preview transactions, review possible duplicates, and save reusable formats.
- **Automate repeat imports:** give each account its own default format, including date, header, separator, and amount settings.
- **Categorize faster:** reuse categories from previous purchases at the same merchant, or define merchant rules.
- **Clean up across months:** search all transactions and categorize matching purchases in bulk.
- **Handle card payments correctly:** classify movements between accounts as transfers so they do not inflate income or expenses.
- **Keep separate finances:** create user logins with private accounts, transactions, categories, rules, and import formats.

## Windows standalone edition

Spearmint also has a standalone Windows 11 x64 installer. It bundles Python, the backend, and the interface; Docker and a separate server are not required. Both editions share the same application features, but their databases are independent and do not synchronize.

1. Open the [Spearmint Releases](https://github.com/Covenn604/spearmint/releases) and download the `Spearmint-<version>-Windows-x64-Setup.exe` installer from **Assets**.
2. Run the `Spearmint-<version>-Windows-x64-Setup.exe` installer. It installs for the current Windows user and offers a desktop shortcut.
3. Open Spearmint and create your administrator username and password in the first-run setup window.
4. Sign in, complete your password and security questions, then add accounts or import CSVs as usual.

If Microsoft WebView2 Runtime is missing, the installer runs Microsoft's signed bootstrapper; this requires internet access. Normal financial tracking works offline. Initial builds are unsigned and Windows may show a publisher/reputation warning; code signing is not configured yet.

Financial data is stored in `%LOCALAPPDATA%\Spearmint\data`. The backend listens only on `127.0.0.1` using an available port and stops when the desktop window closes. Only one desktop instance may use that data folder at a time. Other devices cannot connect to the standalone edition; use Docker for server access.

To back up Windows data, close Spearmint and copy the entire data folder to a separate backup location. To restore, close the app and restore a complete backup to that folder. Install a newer installer over the existing installation to update. Uninstall removes program files and shortcuts but preserves financial data. **Export transactions** opens a Windows Save As dialog so you can choose the CSV filename and destination. The Windows app checks GitHub Releases on startup and hourly while open. New stable releases prompt you to update; declining silences automatic prompts for 24 hours, including across restarts. **Check for updates** performs an immediate check even during that pause. Accepting downloads and verifies the installer against GitHub’s SHA-256 digest, closes the app, installs into the existing program directory, and reopens Spearmint. Saved data is preserved; save any form edits before accepting. Offline or failed background checks do not interrupt normal use. Download or verification failures leave the running version in place. There is no synchronization between installations.

Install v0.5.4 manually once to enable future updates. The updater only uses published, non-prerelease GitHub Releases with a newer version and a matching `Spearmint-<version>-Windows-x64-Setup.exe` asset containing a GitHub SHA-256 digest. Supported tags include `0.5.4`, `v0.5.4`, and `Spearmint-v0.5.4`. Actions artifacts and Docker images do not trigger Windows prompts. Continue uploading the installer to Releases when publishing a Windows version. Update preferences, staged installers, and `install.log` are stored in `%LOCALAPPDATA%\Spearmint\updates`, separately from financial data. Docker has no automatic update checks.

The Windows workflow tests the packaged backend, installed WebView2 login window, installation, and data preservation on uninstall. It cannot replace hands-on testing of first-run setup, CSV file selection, and everyday use on Windows 11. Windows installers are distributed through [GitHub Releases](https://github.com/Covenn604/spearmint/releases).

## Install with Docker Compose

The published image targets **Linux amd64** (Intel/AMD servers). You need Docker with the Compose plugin and persistent storage for `/data`.

```bash
git clone https://github.com/Covenn604/spearmint.git
cd spearmint
cp .env.example .env
```

Edit `.env` and set `APP_PASSWORD` to a unique password of at least 12 characters. Then start Spearmint:

```bash
docker compose pull
docker compose up -d
```

Open **http://YOUR-SERVER-IP:8085**. On a new installation, sign in as **admin** using the password you configured. Set `ADMIN_USERNAME` before the first startup if you want a different administrator username.

The supplied [compose.yaml](compose.yaml) uses a persistent named volume, runs as a non-root user, and keeps the container filesystem read-only except for its data and temporary storage.

### Install through Portainer

1. Create a stack and paste the contents of [compose.yaml](compose.yaml).
2. Set `APP_PASSWORD` in the stack's environment variables. Add any other settings from the table below.
3. Leave `DATA_LOCATION` at its default for the named volume, or set it to an absolute host directory path.
4. Deploy the stack and open the server address above.

If pulling the image requires authentication, configure credentials for `ghcr.io` in Portainer. For an existing installation, update the same stack and preserve its data mount.

### Configuration

These variables are read by the supplied Compose file. Set them in `.env` or in your Portainer stack environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PASSWORD` | Required | Initial administrator password; at least 12 characters. Changing it later does not reset an existing password. |
| `ADMIN_USERNAME` | `admin` | Administrator username on first setup. |
| `APP_IMAGE` | `ghcr.io/covenn604/spearmint:latest` | Image to run. Use `:0.5.4` for the current release tag or a published `:sha-…` tag for a specific source revision. |
| `APP_PORT` | `8085` | Port exposed on the host; the container listens on `8080`. |
| `DATA_LOCATION` | `spearmint-data` | Default named volume, or an absolute host directory mounted at `/data`. |
| `PUID` | `10001` | Numeric user ID for the container process. |
| `PGID` | `10001` | Numeric group ID for the container process. |
| `CURRENCY` | `CAD` | Display currency shared by all users and accounts. No currency conversion is performed. |
| `TZ` | `America/Vancouver` | Server timezone used for the current reporting day. |
| `COOKIE_SECURE` | `false` | Set to `true` when accessing Spearmint through HTTPS. |

### Host folders and permissions

To store data in a host folder, set `DATA_LOCATION` in `.env` or in the Portainer stack environment:

```dotenv
DATA_LOCATION=/mnt/array/appsdata/spearmint/data
```

Compose mounts it using:

```yaml
volumes:
  - "${DATA_LOCATION:-spearmint-data}:/data"
```

Leaving the variable unset or empty uses the `spearmint-data` named volume. Compose prefixes its actual name with the project name, normally `spearmint_spearmint-data`. Use an absolute path for a host directory; the container always uses `/data`. The variable is a Compose setting, not an application environment variable.

For an existing bind-mount installation, set it to your **current host directory** before redeploying the updated Compose file. Changing this setting does not move data: a different empty directory starts a separate installation. To relocate data, stop the app and copy the complete existing data directory to the new location first, preserving access permissions.

The selected `PUID` and `PGID` must have read/write access to the folder and existing database files, plus permission to traverse parent directories. Changing these variables does not change file ownership or filesystem ACLs.

For example, to prepare a **new, dedicated directory** for UID/GID `1000:1000`:

```bash
sudo mkdir -p /your/spearmint/data
sudo chown 1000:1000 /your/spearmint/data
sudo chmod 750 /your/spearmint/data
```

Then set `PUID=1000` and `PGID=1000`. For existing data, stop the app before adjusting ownership and permissions on its files. On hosts using ACLs, grant the same access through the ACLs.

The image defaults to `10001:10001`. Keep those IDs for the supplied named volume unless you also prepare that volume for a different owner. With `docker run`, use `--user UID:GID`; passing `PUID` and `PGID` as container environment variables alone does not change the process identity.

## Set up your finances

1. Open **Accounts & categories** and add your bank accounts and credit cards.
2. Enter each account's balance immediately before the earliest transaction you plan to record. Credit card debt is negative.
3. Create or rename your spending categories.
4. Add transactions manually or import a CSV statement.
5. Select a month to review spending, then use **Transactions** to correct types or assign categories.

For manual entries, enter a positive amount and choose **Expense**, **Income**, **Refund**, or **Transfer**. The transaction type determines its direction. An existing imported transfer is edited using its signed amount.

### Account balances

Spearmint calculates:

**Account balance = opening balance + all recorded transactions**

Balances include future-dated entries and do not change with the selected reporting month. They are ledger balances, not live bank balances.

For credit cards, purchases reduce the balance and payments increase it toward zero. Negative amounts are displayed in red with parentheses. For example, **($300.00)** means **$300 owing**. Editable numeric fields and CSV exports retain signed numbers.

Use **Edit opening balance** to correct an account's starting value. The dialog previews the resulting balance. This does not change transactions or monthly spending totals.

If you deliberately want to adjust the starting value to match a target balance, use:

**Opening balance = target signed balance − net recorded activity**

An adjustment can align the total, but does not resolve missing transactions, duplicates, or reversed import signs. Check those first if an account does not match your statement.

### Transfers and credit card payments

A credit card purchase is an expense. Paying the card bill is a transfer.

| Entry | Signed amount | Type |
| --- | --- | --- |
| Card payment leaving a bank account | Negative | Transfer |
| The same payment arriving on the credit card | Positive | Transfer |

Both entries affect their account balances. Neither counts toward income or spending.

A **new manual transfer** creates linked entries in the source and destination accounts. Deleting either removes both; to change a linked transfer, delete and recreate it.

For **imported transfers**, mark the existing entry on each account as Transfer. Spearmint does not create a counterpart or pair imported entries automatically. If you track only one side, its entry can still be a transfer.

## Import CSV statements

Open **Import transactions**, select the destination account, and upload the CSV file. Extract ZIP archives before uploading.

### Supported formats

| Setting | Support |
| --- | --- |
| Encoding | UTF-8, UTF-16 LE, and UTF-16 BE. BOMs are supported; BOM-less UTF-16 is detected when ASCII headings identify its byte order. |
| Separators | Comma, semicolon, or tab; quoted fields are supported. |
| Introductory content | Skip up to 1,000 physical lines before the header, including blank lines. |
| Dates | `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYYMMDD`, `YYYY/MM/DD`, `DD-MM-YYYY`, `MM-DD-YYYY`, or `DD Mon YYYY`, such as `07 Sep 2026`. Month abbreviations are English. |
| Amounts | One signed amount column, or separate debit and credit columns. Parenthesized negatives and optional decimal-comma formatting are supported. |
| Size | Up to 2,000,000 bytes and 5,000 data rows, with at most 100 header columns. |

The selected **date, description, and amount fields** are imported, plus an optional **category column**. Leave the category column unmapped for normal bank imports. For migration files, existing category names match without regard to capitalization or extra spaces. New names appear as **New: …** in the preview and are created only for selected expenses or refunds when you confirm the import. You can choose another category or Uncategorized per row. Blank category cells use the usual automatic suggestions; an explicit Uncategorized value leaves the row uncategorized. Income and transfers do not receive spending categories. The category mapping is saved with your import profile. Account identifiers, cheque numbers, running balances, source IDs, and other unmapped fields are ignored. Saved mappings use column positions, so review them if a bank changes its export layout.

### Import workflow

1. **Choose the account.** Its default saved format loads automatically, if one is associated.
2. **Upload the CSV.** Set the separator and number of lines to skip if needed. A value of zero uses the first nonblank row as the header.
3. **Map the columns.** Choose date, description, and either a signed amount or separate debit/credit columns.
4. **Check dates and signs.** Select the exact date format. Use **Reverse amount signs** for a signed column when the statement's direction is opposite to Spearmint's. Negative means money out; positive means money in. Split-column mode uses the absolute credit amount minus the absolute debit amount and ignores the reversal checkbox.
5. **Preview transactions.** Check amounts, categories, types, and duplicate warnings. Positive rows initially count as income: change refunds and transfers to their correct types.
6. **Import selected transactions.** Only checked, valid rows are committed after confirmation.

### Saved mappings and account defaults

| Control | What it does |
| --- | --- |
| **Save new format** | Saves the current mapping under a new name and makes it the selected account's default. |
| **Update selected format** | Replaces the selected format's saved settings with the current mapping. Upload a CSV first to edit its column mapping. |
| **Rename format** | Changes its name while preserving account associations. No file upload is required. |
| **Delete format** | Removes the format and clears defaults that refer to it. Imported transactions are kept. |
| **Use as account default** | Associates an existing saved format with the selected account. |
| **Clear account default** | Removes the association while keeping the saved format. |

Every account can have its own default. Switching accounts restores that account's separator, header lines, date format, columns, and amount settings. An account without a default starts with fresh settings, including sign reversal turned off.

For existing formats, select the account and format, then click **Use as account default** once. Selecting an alternate format for a one-off import does not replace the stored default. Editing a format affects future use by every account associated with it.

### Duplicates and undo

Spearmint checks for matching **account, date, signed amount, and normalized merchant description** against transactions already saved in the account. Possible duplicates are unchecked by default. Select one only when it represents a separate transaction you want to keep.

Repeated new charges within a CSV stay selected and are labeled **similar new charge**. If you select two or more with the same date, merchant, and signed amount, Spearmint asks you to confirm adding each group as separate transactions. Cancel to review and adjust your selections. Selecting only one does not need this extra confirmation.

Checks run again when committing the import. Invalid rows show a reason and cannot be imported. Previews expire after one hour and cannot be committed twice; changing the account or mapping requires a new preview.

Duplicate detection does not use fuzzy dates or new source transaction IDs. Different dates or descriptions can prevent a match, and two genuine purchases can have identical details.

After importing, **Undo this import** removes the batch, including later edits to its rows. The shortcut is available on the completion panel in the current page session. After reloading, use transaction deletion instead.

## Categorize and review transactions

### Search across months

In **Transactions**, select **Date range → All transactions** to search across recorded history. Search matches merchant descriptions, notes, and account names. Notes appear in their own column between category and amount in both date ranges. Use **Edit** on a transaction to add or change its notes.

By default, this view shows uncategorized expenses and refunds for cleanup. Categorized records disappear from that view after saving. Enable **Show categorized, income and transfers** to see the complete history. Filtering does not delete records.

Use the table header checkbox to select all shown transactions, or **Select all transactions** to clear filters and select every date and category. Choose **Delete selected** and confirm the irreversible-deletion warning to permanently remove the selection. Both sides of linked transfers are removed together, including a counterpart outside the current filters. Accounts, opening balances, categories, rules, and mappings remain; balances and spending totals recalculate. Canceling the prompt deletes nothing.

Select matching expense/refund rows, choose a category, and click **Apply to selected**. Choose **Uncategorized** to clear assignments. Up to 5,000 records can be categorized in one operation. Use **Selected month** to return to monthly browsing.

### Automatic categorization

Spearmint first checks explicit merchant rules. Matching is case-insensitive, and the first matching rule wins.

If no rule matches, it can reuse a category from previous categorized expenses with the same full merchant description. Matching ignores capitalization and repeated whitespace. If those past expenses disagree on the category, no history-based suggestion is made.

Suggestions appear in the CSV preview and can be changed or cleared. Classifying past purchases manually or in bulk helps categorize future imports. Existing transactions are not recategorized automatically. Income, refunds, and transfers do not train the history lookup.

### Manage categories

In **Accounts & categories**, use a category's **Edit** control to rename or delete it. Renaming updates its display throughout the app.

When deleting a category, choose another category or **Uncategorized** for its transactions. If merchant rules still use it, reassign them to a valid category or remove those rules first. Transactions are preserved.

## Understand the monthly overview

| Measure | Meaning |
| --- | --- |
| Income | Recorded transactions marked Income. |
| Net expenses | Expenses minus refunds; transfers are excluded. |
| Left over / Over income | Income minus net expenses. This does not reserve money for upcoming bills. |
| Usual category spending | Average net spending across eligible months among the previous three calendar months. |
| Account balances | Opening balances plus all recorded activity, independent of the reporting month. |

For the **current month**, spending includes entries through the server's current day. Category comparisons use the same day of each earlier month, capped at that month's last day. Past-month comparisons use full months.

The baseline excludes months before the earliest recorded non-transfer transaction. Zero-spend months after that starting month count toward the average. The overview identifies the months used; incomplete history can make comparisons misleading.

The six-month trend uses full earlier months and month-to-date for the current month. **Above usual** means spending increased relative to your history; it does not mean that category exceeded a configured budget.

## Users and access

Open **Profile & users** to change your password. Administrators can also create users, reset their passwords, and disable or re-enable logins. Disabled users retain their data.

To permanently remove a user, select them under **Manage an existing user**, choose **Delete user permanently**, and apply the change. Review the warning and type their username exactly to confirm. Deletion removes their login and all saved transactions, accounts, categories, merchant rules, and CSV mappings, and ends their sessions. The administrator cannot be deleted. Existing backups are not modified. If data cleanup fails, the user stays disabled; correct the data-folder permissions and retry deletion.

Each user has separate financial records and CSV formats. There are no shared household workspaces. The administrator manages logins but has no interface to browse another user's finances; the server owner and anyone able to reset passwords remain trusted administrators.

Passwords are stored as salted PBKDF2-SHA256 hashes. Usernames are case-insensitive, and passwords require 12–1,024 characters. There is no public registration or email-based password recovery. Self-service recovery uses the security questions described below. Once initialized, changing `APP_PASSWORD` or `ADMIN_USERNAME` in the environment does not replace stored credentials.

Sessions last 12 hours and end on server restart. Password changes and disabling a user invalidate their sessions.

Spearmint uses Python's standard-library HTTP server and is intended for a trusted LAN. Use your VPN or an HTTPS reverse proxy for remote access; set `COOKIE_SECURE=true` for HTTPS. HTTP does not encrypt traffic, and database files are not encrypted at rest. Protect the server and its backups. Do not commit statements, passwords, or financial databases to this repository.

### First-login setup and password recovery

On their first login, every user—including the administrator—must choose a password and answer all three questions before accessing financial records. Existing users upgrading from an earlier release enroll on their next login. Administrator password resets require the affected user to complete setup again.

1. What is your mother's middle name?
2. What was the name of the town or city where you were born?
3. What was the first and last name of your childhood best friend?

Answers are case-insensitive and ignore leading/trailing whitespace. They are stored as individually salted hashes, never readable answer text. Remember the answers you supply; they grant access to password recovery.

Choose **Forgot password?** on the login screen, enter your username, and answer the two randomly selected questions. After both answers are verified, choose and confirm a new password. Question challenges expire after ten minutes; verified reset tokens expire after five minutes and can be used only once. Recovery attempts are rate-limited by account and source IP. A reset invalidates previous login sessions. Disabled users cannot recover their accounts.

### Upgrade from versions before v0.5.0

Stop all old app instances and back up the complete data folder before upgrading. Financial databases are automatically migrated from `monthly-spend.sqlite3` to `spearmint.sqlite3`, including additional users' databases. SQLite checkpoints committed journal data before the rename. The login database remains `users.sqlite3`.

If both old and new financial filenames exist in one folder, startup refuses to overwrite either. Restore or reconcile the correct complete backup before retrying. Do not manually rename a database while the app is running. After migration, older Spearmint releases cannot find the renamed financial files; rolling back requires restoring the complete pre-upgrade backup with the old release.

The Windows executable, installer, shortcuts, setup window, and application window now use the Spearmint leaf icon. Windows may cache existing pinned shortcuts; unpin and re-pin after upgrading if an old icon remains.

## Back up and update

### Backups

Back up the **entire `/data` directory**. It includes:

| Path inside the container | Contents |
| --- | --- |
| `/data/users.sqlite3` | User logins and password hashes. |
| `/data/spearmint.sqlite3` | Original administrator's finances. |
| `/data/users/<id>/spearmint.sqlite3` | Each additional user's finances. |

Preserve the directory structure and any SQLite journal files. The transaction CSV export is useful for analysis, but omits opening balances, user accounts, mappings, rules, and transfer links; it is not a full backup.

For the supplied Compose configuration, stop the app and copy its data to a **new backup directory** outside the checkout:

```bash
docker compose stop
mkdir -p /your/backups/spearmint-backup
docker cp spearmint:/data/. /your/backups/spearmint-backup/
docker compose start
```

Replace the example path and use a distinct directory for each backup. Adjust the container name if your installation uses a different one.

To restore, stop the app and restore one complete backup to its data mount. Keep files from different backups separate and restore the configured user's access permissions before starting. Verify restoration on a separate copy before relying on the backup.

### Updates

After backing up, update a Git/Compose installation with:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
```

In Portainer, redeploy the **existing stack** with the option to pull the image again enabled. If you pinned `APP_IMAGE` to a version or commit tag, change that value when choosing a newer release.

Keep the same data mount and user/group permissions. If upgrading from the old Compose names, follow the migration steps below before redeploying. **Do not use `docker compose down -v` unless you intend to delete the named volume.**

### Existing Monthly Spend installations

Use `ghcr.io/covenn604/spearmint:latest` for current images and `https://github.com/Covenn604/spearmint.git` for the repository remote.

The Compose project, service, and container are now named `spearmint`, with `spearmint-data` as the default volume key. Financial databases use `spearmint.sqlite3` from v0.5.0 onward; existing files are migrated automatically as described above.

Before replacing an older Compose configuration:

1. Back up the complete data directory. Use the old container name (`monthly-spend`) in the backup command if that is what is currently running.
2. Identify its current `/data` mount in Portainer or with `docker inspect monthly-spend --format '{{json .Mounts}}'`.
3. For a **bind mount**, set `DATA_LOCATION` to that exact existing host directory.
4. For an **existing named volume**, set `DATA_LOCATION=spearmint-data` and replace the top-level volume declaration in the new Compose file with the following, substituting the actual existing volume name:

```yaml
volumes:
  spearmint-data:
    external: true
    name: YOUR_EXISTING_VOLUME_NAME
```

This gives the existing volume the new Compose alias without moving or deleting its contents. Do not put an undeclared old volume name directly in `DATA_LOCATION`.

Stop and remove the old container without deleting its volume before starting the new service, so both containers do not compete for the port or access the same database. With the old Compose configuration still in place, `docker compose down` removes its containers while retaining named volumes; **do not add `-v`**. In Portainer, stop/remove the old deployment while retaining its storage, then deploy the updated configuration with the mount configured above. Confirm that your existing accounts and transactions appear after startup.

Changing project, container, or volume names does not migrate data automatically. Starting the new defaults without pointing them to existing storage creates an empty installation.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Container fails after changing the data mount or UID/GID | Confirm the host directory exists and the configured identity can traverse directories and read/write all data files. Inspect `docker compose logs --tail=100`. |
| Image pull is denied | Confirm the image name and registry credentials. Authenticate to GHCR if the package requires it. |
| App opens but shows “Failed to fetch” | Check container logs and connectivity to the server and published port. If using a reverse proxy, check that it forwards `/api/` as well as the page. |
| Login fails after changing `.env` | Existing credentials are stored in the user database. Use the password-change or administrator-reset controls; environment changes do not reset them. |
| Login will not persist over HTTP | Check whether `COOKIE_SECURE=true` is set. Secure cookies require HTTPS. |
| CSV headings are wrong | Check encoding, delimiter, and introductory lines. Convert unsupported encodings to UTF-8 and select the CSV rather than a ZIP. |
| CSV rows show invalid dates | Select the matching date format. `YYYYMMDD` requires eight digits; `DD Mon YYYY` uses English month abbreviations. |
| A saved mapping does not load for an account | Select the account and saved format, then click **Use as account default**. |
| A payment inflates income or spending | Mark the payment as Transfer on each tracked account and check its signs. |
| A balance differs from the bank | Check the opening balance, missing or duplicate records, sign inversion, and pending or future-dated entries. |

## Development

The app uses **Python 3.12**, SQLite, and plain HTML/CSS/JavaScript. There are no third-party Python or JavaScript runtime dependencies. Amounts are stored as integer cents.

To run without Docker, set `APP_PASSWORD` in your shell environment and start:

```bash
python app.py
```

The local server defaults to port `8080` and a `data` directory beside `app.py`. Override these with `PORT` and `DATA_DIR`. A local Python launch does not automatically load `.env`.

Run the checks with Python and Node.js installed:

```bash
python -m unittest discover -s tests -v
node --check static/app.js
node --test tests/test_csv_*.js
```

Tests cover financial calculations, imports and encoding, duplicates, profiles and account defaults, categorization, authentication, and user isolation. CI also builds the image and checks container startup. Browser interaction and visual testing are not part of the automated checks.

To build your own image:

```bash
docker build -t spearmint:local .
```

Set `APP_IMAGE=spearmint:local` and run `docker compose up -d` without pulling from the registry.

The [publishing workflow](.github/workflows/docker-publish.yml) runs on pushes to `main` and manual dispatch. After tests pass, it publishes `latest`, the configured version tag, and a `sha-…` tag to GHCR using `GITHUB_TOKEN`. Publishing an image does not update running installations.

## Current scope

Spearmint currently supports manual entry and CSV imports. Bank synchronization, transaction splits, recurring-bill forecasts, reconciliation workflows, account deletion, multi-currency conversion, category spending limits, shared household workspaces, and automatic pairing of imported transfers are not implemented.

For a bug report, include the app version, reproduction steps, and exact error. For CSV problems, provide a small **synthetic** example that preserves the layout and date/amount formats without exposing personal transactions or account details.
