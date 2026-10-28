# Email delivery — SMTP setup for `@everest.local`

GRC Nexus sends mail in two ways:

| Path | Trigger | Recipients |
| --- | --- | --- |
| **Immediate notification email** | A high-signal notification is raised (risk escalation, overdue item, incident SLA/GDPR deadline, KRI breach, vulnerability SLA breach, expired vendor contract, policy approval) | Named recipient, else the department HOD(s), else superusers |
| **Digest / escalation job** | `send_email_digest` and `send_escalations` | Opted-in users and responsible owners |

Both use the same outbound configuration, which lives in the database and is
edited in the UI at **Settings → Email delivery** (`/settings/email/`). You do
**not** need to edit `.env` or restart the container to change it.

The SMTP password is stored encrypted with a key derived from `SECRET_KEY`.
Rotating `SECRET_KEY` invalidates it — re-enter the password afterwards.

---

## 1. Pick an SMTP server

### Option A — Mailpit (2 minutes, recommended while you build the VM)

[Mailpit](https://mailpit.axllent.org/) is a local SMTP sink with a web inbox.
Nothing leaves the machine, and you can see every message immediately.

Add this service to `docker-compose.yml`:

```yaml
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"   # SMTP
      - "8025:8025"   # web inbox
    restart: unless-stopped
```

Start it and open <http://localhost:8025>:

```bash
docker compose up -d mailpit
```

Then configure GRC Nexus with:

| Field | Value |
| --- | --- |
| Enabled | on |
| Host | `mailpit` |
| Port | `1025` |
| Encryption | `None` |
| Username | *(blank)* |
| Password | *(blank)* |
| From address | `no-reply@everest.local` |

This is the fastest way to prove the feature works end to end. The rest of this
guide replaces Mailpit with a real Postfix server in your Ubuntu VM.

### Option B — Ubuntu + Postfix (the real `everest.local` mail server)

The steps below target Ubuntu 22.04/24.04 and a **host-only or bridged** VM
network. The finished server accepts mail for anything `@everest.local` and
delivers it into one catch-all mailbox you can read in the VM.

> `everest.local` is a private, non-public domain (`.local` is reserved for
> mDNS). That is fine for a lab: no public DNS, SPF or DKIM is required, and no
> public CA can issue a certificate for it. Keep the server on a private
> network and never expose port 25 to the internet.

---

## 2. Prepare the VM network

The web app runs in a Docker container on the Windows host. The container must
be able to open a TCP connection to the VM's SMTP port.

> The examples below use `192.168.56.10`. **Substitute the address that
> `ip -4 addr show` prints on your VM** — VirtualBox host-only is usually
> `192.168.56.x`, while VMware NAT is usually `192.168.48.x`. Using the wrong
> subnet is the most common cause of a connection timeout.

### Recommended: host-only adapter

1. In VirtualBox: **Settings → Network → Adapter 2 → Host-only Adapter**.
2. Boot Ubuntu and find the address:

   ```bash
   ip -4 addr show
   ```

   You want the `192.168.56.x` address, for example `192.168.56.10`.

3. From Windows, confirm the VM is reachable:

   ```powershell
   Test-NetConnection 192.168.56.10 -Port 22
   ```

### Alternative: NAT with port forwarding

If you cannot use host-only networking, forward a host port to the guest:

* VirtualBox → **Settings → Network → Adapter 1 → Advanced → Port Forwarding**
* Rule: host `2525` → guest `25`

Then use `host.docker.internal` and port `2525` in GRC Nexus. On Docker Desktop
for Windows this name resolves to the host automatically. If it does not, add:

```yaml
  web:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

---

## 3. Install Postfix

```bash
sudo apt update
sudo apt install -y postfix mailutils
```

The installer asks two questions:

* **General type of mail configuration** → **Internet Site**
* **System mail name** → `everest.local`

If you miss the prompts, reconfigure later:

```bash
sudo dpkg-reconfigure postfix
```

---

## 4. Configure Postfix

Back up the original, then apply the settings:

```bash
sudo cp /etc/postfix/main.cf /etc/postfix/main.cf.bak

sudo postconf -e 'myhostname = mail.everest.local'
sudo postconf -e 'mydomain = everest.local'
sudo postconf -e 'myorigin = $mydomain'
sudo postconf -e 'inet_interfaces = all'
sudo postconf -e 'inet_protocols = ipv4'

# everest.local is a *virtual alias* domain, so every address can be
# rewritten to the catch-all mailbox below.
sudo postconf -e 'mydestination = $myhostname, localhost.$mydomain, localhost'
sudo postconf -e 'virtual_alias_domains = $mydomain'
sudo postconf -e 'virtual_alias_maps = hash:/etc/postfix/virtual'

# Accept mail from the local machine, the host-only network, and the Docker
# bridge. Adjust to your own subnet if it is not 192.168.56.0/24.
sudo postconf -e 'mynetworks = 127.0.0.0/8, 192.168.56.0/24, 172.16.0.0/12'

# Only relay for trusted networks; reject everything else.
sudo postconf -e 'smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination'
sudo postconf -e 'smtpd_recipient_restrictions = permit_mynetworks, reject_unauth_destination'

sudo systemctl restart postfix
```

Check the result:

```bash
postconf -n
```

### Catch-all mailbox

Create a local Unix account that receives every `@everest.local` message:

```bash
sudo useradd -m -s /usr/sbin/nologin maildrop
```

Point the whole domain at it:

```bash
echo '@everest.local    maildrop@localhost' | sudo tee /etc/postfix/virtual
sudo postmap /etc/postfix/virtual
sudo systemctl reload postfix
```

> `maildrop@localhost` resolves to the local Unix user `maildrop`, because
> `localhost` is still in `mydestination`. Do not put `everest.local` in
> `mydestination` — the virtual alias lookup would never run.

### Firewall

Allow SMTP only from the host-only network:

```bash
sudo ufw allow from 192.168.56.0/24 to any port 25 proto tcp
sudo ufw reload
sudo ufw status verbose
```

If `ufw` is inactive, either enable it or skip this step. Do **not** run
`ufw allow 25/tcp` on a bridged VM that sits on a shared network.

---

## 5. Verify the server before touching Django

### From the Windows host

```powershell
Test-NetConnection 192.168.56.10 -Port 25
```

`TcpTestSucceeded : True` means the port is open.

### From the web container

The container is the process that actually sends mail, so test from there:

```bash
docker compose exec -T web python -c "import socket; s=socket.create_connection(('192.168.56.10', 25), 5); print(s.recv(200).decode()); s.close()"
```

You should see a banner like:

```
220 mail.everest.local ESMTP Postfix (Ubuntu)
```

If this fails but the Windows test succeeded, the container cannot route to
the host-only network. Use the NAT port-forwarding option from section 2 and
`host.docker.internal:2525` instead.

### Send a raw test message

On the VM, install `swaks` (it is the simplest SMTP client):

```bash
sudo apt install -y swaks
swaks --to someone@everest.local --from test@everest.local \
      --server 127.0.0.1 --port 25 --body 'hello from postfix'
```

Then read the catch-all mailbox:

```bash
sudo mail -f /var/mail/maildrop
```

Check the log if nothing arrives:

```bash
sudo tail -f /var/log/mail.log
```

---

## 6. Enter the settings in GRC Nexus

Sign in as a **superuser**, then open **Settings → Email delivery**
(`http://localhost:8000/settings/email/`).

Use these values for the Ubuntu VM:

| Field | Value |
| --- | --- |
| **Deliver email through this SMTP server** | on |
| **Host** | `192.168.56.10` (your VM's host-only IP) |
| **Port** | `25` |
| **Encryption** | `None — plain SMTP (local relay)` |
| **Timeout** | `20` |
| **Username** | *(blank — the relay does not authenticate)* |
| **Password** | *(blank)* |
| **From name** | `GRC Nexus` |
| **From address** | `no-reply@everest.local` |
| **Email on high-signal notifications** | on |

Click **Save email settings**.

> If you used NAT port forwarding, the host is `host.docker.internal` and the
> port is `2525`.

### Send the test message

In the **Send a test message** card, enter a real mailbox you can read (for
example `someone@everest.local`, or your own address if the VM relays onward)
and click **Send test**.

* Success → green banner, and the message appears in the Mailpit inbox or
  `/var/mail/maildrop`.
* Failure → red banner. The exact SMTP error is in the container log:

  ```bash
  docker compose logs -f web
  ```

The UI deliberately shows only a generic failure message; the log has the
detail (refused connection, authentication, relay denied, TLS mismatch).

---

## 7. What gets emailed immediately

Immediate email is sent only for high-signal notifications, so creating a
single asset does not generate three messages:

* Risk escalated / risk past its target close date
* Audit finding overdue, remediation action overdue, ticket overdue
* Risk exception expiring, risk exception awaiting approval
* Vendor contract expired or expiring
* KRI breached tolerance
* Vulnerability past its remediation SLA
* Security incident needs attention, incident past its triage SLA, GDPR
  breach-notification deadline
* Policy awaiting approval

Routine "needs an owner / needs a vendor / needs a control mapping"
housekeeping stays in the in-app notification list and in the digest.

Delivery rules:

* The email goes to the notification's named recipient if there is one.
* Otherwise it goes to the department's HOD(s).
* Otherwise it goes to active superusers.
* Each user's per-event toggle in **Settings** is honoured.
* Sending is deferred until the database transaction commits, and a mail
  failure never rolls back the save that raised the notification.

---

## 8. Per-user inboxes: Dovecot + Roundcube (or Thunderbird)

Section 4 gave you one catch-all mailbox, which is enough to prove delivery but
does not let you sign in **as** `s.shrestha@everest.local`. For that you need
real per-user mailboxes (Postfix virtual delivery) and an IMAP server
(Dovecot). Once IMAP is running you can use either:

* **Thunderbird** — desktop, fastest, no web server needed.
* **Roundcube** — Gmail-like webmail you open at
  `http://<vm-ip>/roundcube/`. [SnappyMail](https://snappymail.eu/) is a
  lighter, more modern alternative if you prefer.

### 8.1 Switch Postfix to virtual mailboxes

The catch-all alias and virtual mailboxes cannot coexist for the same domain,
so replace the section 4 alias configuration.

```bash
sudo groupadd -g 5000 vmail 2>/dev/null || true
sudo useradd -g vmail -u 5000 -d /var/vmail -m -s /usr/sbin/nologin vmail 2>/dev/null || true
sudo mkdir -p /var/vmail
sudo chown -R vmail:vmail /var/vmail

sudo postconf -e 'virtual_mailbox_domains = everest.local'
sudo postconf -e 'virtual_mailbox_base = /var/vmail'
sudo postconf -e 'virtual_mailbox_maps = hash:/etc/postfix/vmailbox'
sudo postconf -e 'virtual_uid_maps = static:5000'
sudo postconf -e 'virtual_gid_maps = static:5000'
sudo postconf -e 'virtual_alias_domains ='
sudo postconf -e 'virtual_alias_maps = hash:/etc/postfix/virtual'
```

Create one line per address. The trailing slash means **Maildir**, and the
directory name is the full address so it matches Dovecot's `%{user}`:

```bash
sudo tee /etc/postfix/vmailbox >/dev/null <<'EOF'
admin@everest.local        admin@everest.local/
test@everest.local         test@everest.local/
no-reply@everest.local     no-reply@everest.local/
s.shrestha@everest.local   s.shrestha@everest.local/
b.pandey@everest.local     b.pandey@everest.local/
s.bhattarai@everest.local  s.bhattarai@everest.local/
p.lama@everest.local       p.lama@everest.local/
r.sharma@everest.local     r.sharma@everest.local/
b.thapa@everest.local      b.thapa@everest.local/
s.gurung@everest.local     s.gurung@everest.local/
d.khadka@everest.local     d.khadka@everest.local/
s.magar@everest.local      s.magar@everest.local/
a.rai@everest.local        a.rai@everest.local/
EOF

# Remove the old catch-all alias, then rebuild both maps.
echo '# explicit aliases only' | sudo tee /etc/postfix/virtual
sudo postmap /etc/postfix/vmailbox
sudo postmap /etc/postfix/virtual
sudo systemctl restart postfix
```

Mail for a listed address now lands in
`/var/vmail/<user>@everest.local/`. Mail for an unlisted address is rejected
with `550 5.1.1 User unknown` — add it to `vmailbox` and re-run `postmap` when
you create a new app user.

### 8.2 Dovecot (IMAP)

```bash
sudo apt install -y dovecot-imapd
dovecot --version
```

Ubuntu 24.10+ ships **Dovecot 2.4**, which renamed several settings:

| Dovecot 2.3 | Dovecot 2.4 |
| --- | --- |
| `mail_location = maildir:/path/` | `mail_driver = maildir` + `mail_path = /path` |
| `disable_plaintext_auth = no` | `auth_allow_cleartext = yes` |
| `passdb { driver = passwd-file; args = ... }` | `passdb passwd-file { passwd_file_path = ... }` |
| `userdb { driver = static; args = ... }` | `userdb static { fields { ... } }` |

For 2.4, remove any 2.3 lines you added earlier, delete the package's
`mail_inbox_path`, and append the new settings:

```bash
sudo sed -i '/^mail_location = /d; /^mail_uid = /d; /^mail_gid = /d; /^first_valid_uid = /d; /^last_valid_uid = /d' /etc/dovecot/conf.d/10-mail.conf

# The Ubuntu package ships mail_inbox_path = /var/mail/%{user}, which puts INBOX
# outside the Maildir. Dovecot then tries to create /var/mail/<user> and fails
# with "Failed to autocreate mailbox: Permission denied".
sudo sed -i '/^[[:space:]]*mail_inbox_path[[:space:]]*=/d' /etc/dovecot/conf.d/10-mail.conf

sudo tee -a /etc/dovecot/conf.d/10-mail.conf >/dev/null <<'EOF'
mail_driver = maildir
mail_path = /var/vmail/%{user}
EOF
```

Verify only the intended settings remain:

```bash
sudo doveconf -n | grep -E '^mail_'
```

`mail_inbox_path` must not appear. `mail_driver = mbox` and
`mail_path = %{home}/mail` earlier in the file are fine — later lines win.

Edit `/etc/dovecot/conf.d/10-auth.conf`:

```bash
sudo sed -i 's/^!include auth-system.conf.ext/#!include auth-system.conf.ext/' /etc/dovecot/conf.d/10-auth.conf
sudo sed -i '/^disable_plaintext_auth = /d' /etc/dovecot/conf.d/10-auth.conf
sudo sed -i '\|^!include auth-passwdfile.conf.ext$|d' /etc/dovecot/conf.d/10-auth.conf

sudo tee -a /etc/dovecot/conf.d/10-auth.conf >/dev/null <<'EOF'
auth_allow_cleartext = yes
auth_mechanisms = plain login
!include auth-passwdfile.conf.ext
EOF
```

Create `/etc/dovecot/conf.d/auth-passwdfile.conf.ext`:

```conf
passdb passwd-file {
  passwd_file_path = /etc/dovecot/users
}
userdb static {
  fields {
    uid = 5000
    gid = 5000
    home = /var/vmail/%{user}
  }
}
```

Create the accounts (one line per mailbox). Use a real password, not this
example:

```bash
sudo tee /etc/dovecot/users >/dev/null <<'EOF'
admin@everest.local:{PLAIN}Everest@123
test@everest.local:{PLAIN}Everest@123
s.shrestha@everest.local:{PLAIN}Everest@123
b.pandey@everest.local:{PLAIN}Everest@123
EOF

sudo chown root:dovecot /etc/dovecot/users
sudo chmod 640 /etc/dovecot/users
sudo systemctl restart dovecot
```

Disable TLS for the lab (plain IMAP on a private network only) by setting
`ssl = no` in `/etc/dovecot/conf.d/10-ssl.conf`, then restart again.

Test authentication and the listener:

```bash
sudo doveadm auth test test@everest.local 'Everest@123'
ss -lntp | grep ':143'
```

### 8.3 Option A — Thunderbird (fastest)

Create an account with:

| Setting | Value |
| --- | --- |
| Protocol | IMAP |
| Server | `192.168.48.142` (your VM IP) |
| Port | `143` |
| Connection security | None |
| Authentication | Normal password |
| Username | `test@everest.local` |
| SMTP server | `192.168.48.142`, port `25`, no security, no auth |

Repeat for each `@everest.local` user. Thunderbird keeps several identities in
one profile, so you can switch between them from the folder pane.

### 8.4 Option B — Roundcube (Gmail-like webmail)

```bash
sudo apt install -y roundcube roundcube-sqlite3
```

The package installs Apache and enables `/roundcube`. When `dbconfig-common`
asks, choose **SQLite** (simplest) and accept the defaults.

> **PHP 8.5:** the distro package may ship an unguarded `array_first()`
> polyfill and crash with `Cannot redeclare function array_first()`. Upgrade
> Roundcube first (`sudo apt install --only-upgrade roundcube roundcube-core`);
> if no newer package exists, apply the patch in section 9.

Edit `/etc/roundcube/config.inc.php` and set:

```php
$config['imap_host'] = 'localhost:143';
$config['smtp_host'] = 'localhost:25';
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
$config['username_domain'] = 'everest.local';
$config['des_key'] = 'replace-with-24-random-characters';
$config['product_name'] = 'Everest Mail';
```

Generate a key with `openssl rand -base64 24`. Then:

```bash
sudo systemctl restart apache2
```

### Logging in to the webmail

Open `http://192.168.48.142/roundcube/` and use the credentials from
`/etc/dovecot/users`. These are **mailbox** accounts, separate from the GRC
Nexus application logins — the app password does not work here.

| Username | Password | Mailbox |
| --- | --- | --- |
| `test` | `Everest@123` | `test@everest.local` |
| `admin` | `Everest@123` | `admin@everest.local` |
| `s.shrestha` | `Everest@123` | `s.shrestha@everest.local` |
| `b.pandey` | `Everest@123` | `b.pandey@everest.local` |

With `$config['username_domain'] = 'everest.local'` you can type the short name
(`test`). If login fails, use the full address (`test@everest.local`) — that
form always works and removes the domain-suffix setting from the equation.

Only addresses listed in `/etc/dovecot/users` can log in. An address that is
only in `/etc/postfix/vmailbox` receives mail but has no password, so add it to
both files:

```bash
echo 'new.user@everest.local:{PLAIN}Everest@123' | sudo tee -a /etc/dovecot/users
echo 'new.user@everest.local new.user@everest.local/' | sudo tee -a /etc/postfix/vmailbox
sudo postmap /etc/postfix/vmailbox
sudo systemctl reload dovecot postfix
```

Changing a password means editing that line and reloading Dovecot:

```bash
sudo doveadm pw -s PLAIN -p 'NewPassword'   # prints {PLAIN}NewPassword
sudo systemctl reload dovecot
```

Allow the web ports from your lab subnet only:

```bash
sudo ufw allow from 192.168.48.0/24 to any port 143 proto tcp
sudo ufw allow from 192.168.48.0/24 to any port 80 proto tcp
sudo ufw reload
```

> Keep IMAP (143) and the webmail on the private network. Plaintext IMAP and
> a self-signed/no-TLS setup must never be exposed to the internet.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Connection refused` | Postfix not listening, or wrong IP/port | `sudo systemctl status postfix`; `ss -lntp \| grep :25`; check the VM IP |
| `Connection timed out` | Firewall, wrong IP/subnet, or container cannot route to the VM | Run `ip -4 addr show` on the VM and use that exact address; `sudo ufw allow from <subnet> to any port 25 proto tcp`; `Test-NetConnection` from Windows |
| `Name or service not known` | Host is a name the container cannot resolve | Use the IP address, or add an `extra_hosts` entry |
| `550 5.7.1 Relay access denied` | Client is not in `mynetworks`, or the recipient domain is not local | Add the client subnet to `mynetworks`; confirm `virtual_mailbox_domains` and `mydestination` |
| `554 5.7.1 ... Client host rejected` | A restriction rejects the container | Keep `permit_mynetworks` first in the restriction lists |
| `SMTPNotSupportedError: STARTTLS` | Encryption is STARTTLS but the relay offers plain SMTP on 25 | Set encryption to **None** |
| `SSLCertVerificationError` | STARTTLS/SSL against a self-signed certificate | Use port 25 with **None** for the lab, or install a trusted certificate |
| `535 Authentication failed` | Wrong username/password, or the relay does not require auth | Clear both fields for the local relay; re-enter the password if `SECRET_KEY` changed |
| Mail arrives but is in spam | No SPF/DKIM and a `.local` sender | Expected for a lab; whitelist `no-reply@everest.local` in the client |
| Nothing in the mailbox | Alias/mailbox map not rebuilt, or the address is unlisted | `sudo postmap /etc/postfix/vmailbox`; `sudo tail -50 /var/log/mail.log`; `postconf virtual_mailbox_maps` |
| `550 5.1.1 User unknown` | Recipient has no `vmailbox` entry | Add the address, `sudo postmap /etc/postfix/vmailbox`, restart Postfix |
| Webmail login fails | Dovecot auth file or `username_domain` mismatch | `sudo doveadm auth test user@everest.local 'password'`; check `/etc/dovecot/users` permissions |
| `Server Error: STATUS: Internal error occurred` after login | Authentication worked; Dovecot cannot open INBOX (usually `mail_inbox_path` pointing at `/var/mail`, or wrong ownership) | See **Mailbox cannot be opened** below |
| `Cannot redeclare function array_first()` | PHP 8.5 added the function natively; the distro Roundcube polyfill is unguarded | Upgrade Roundcube, or apply the patch below |
| Test passes but real notifications do not arrive | Notification kind is not high-signal, SMTP is disabled, or the user opted out | Check **Email on high-signal notifications**, the user's Settings toggles, and the log |

### Mailbox cannot be opened

`STATUS: Internal error occurred. Refer to server log for more information.`
means the IMAP **login succeeded** and the mailbox itself could not be opened.
Roundcube hides the real reason; Dovecot has it. Always start with the debug
run, which prints the path Dovecot actually resolved:

```bash
sudo doveadm -D mailbox status -u test@everest.local messages INBOX 2>&1 | grep -Ei 'namespace|euid|home|permission'
```

#### Cause 1 — INBOX is not in the Maildir (most common)

Symptom in the output:

```
Namespace inbox: /var/mail/test@everest.local doesn't exist yet
Error: Mailbox INBOX: mkdir_parents(/var/mail/test@everest.local) failed: Permission denied
```

The Ubuntu package sets `mail_inbox_path = /var/mail/%{user}`, which overrides
`mail_path` **for INBOX only**. Dovecot then tries to create an mbox file in
`/var/mail` as uid 5000 and fails. Ownership of `/var/vmail` is irrelevant here.

```bash
sudo sed -i '/^[[:space:]]*mail_inbox_path[[:space:]]*=/d' /etc/dovecot/conf.d/10-mail.conf
sudo systemctl restart dovecot
sudo doveadm mailbox status -u test@everest.local messages INBOX
```

Expect `INBOX messages=N`. If `doveconf -n | grep mail_` still lists
`mail_inbox_path`, a later file re-adds it — delete it there too.

#### Cause 2 — ownership

If the debug output shows `/var/vmail/...` and still fails, fix ownership and
create the Maildir skeleton for every address, then release deferred mail:

```bash
sudo mkdir -p /var/vmail

# One Maildir per address that is in /etc/dovecot/users
for u in admin test no-reply s.shrestha b.pandey; do
  sudo mkdir -p "/var/vmail/$u@everest.local"/{cur,new,tmp}
done

sudo chown -R 5000:5000 /var/vmail
sudo chmod -R 700 /var/vmail
sudo postqueue -f
sudo systemctl restart dovecot
```

#### Cause 3 — userdb syntax

In Dovecot 2.4 the static userdb **requires** the `fields` block. The flat form
fails to start with `uid: Unknown setting: uid (userdb_uid or userdb_static_uid
not found either.)`:

```conf
# correct
userdb static {
  fields {
    uid = 5000
    gid = 5000
    home = /var/vmail/%{user}
  }
}
```

Check what Dovecot resolved:

```bash
sudo doveadm user test@everest.local
```

Expected `uid 5000`, `gid 5000`, `home /var/vmail/test@everest.local`.

Confirm delivery without the webmail at all:

```bash
sudo ls -ln /var/vmail/test@everest.local/new/
sudo doveadm mailbox status -u test@everest.local messages INBOX
```

`doveadm` reading the mailbox proves Dovecot is fine and the problem is Roundcube
configuration; Roundcube failing while `doveadm` works means `imap_host` or the
login username is wrong.

### Roundcube on PHP 8.5

PHP 8.5 added `array_first()` and `array_last()` as native functions. Older
Roundcube releases define their own copies, which is a fatal error. Upgrade
first:

```bash
sudo apt update
sudo apt install --only-upgrade roundcube roundcube-core
```

If the repository still ships the broken version, guard the polyfills:

```bash
FILE=/usr/share/roundcube/program/lib/Roundcube/bootstrap.php
sudo cp "$FILE" "$FILE.bak"
sudo sed -i 's/^?>$//' "$FILE"

for fn in array_first array_last; do
  sudo sed -i "s/^[[:space:]]*function ${fn}(/function rcube_polyfill_${fn}(/" "$FILE"
done

sudo tee -a "$FILE" >/dev/null <<'EOF'

if (!function_exists('array_first') && function_exists('rcube_polyfill_array_first')) {
    function array_first($array) { return rcube_polyfill_array_first($array); }
}
if (!function_exists('array_last') && function_exists('rcube_polyfill_array_last')) {
    function array_last($array) { return rcube_polyfill_array_last($array); }
}
EOF

sudo systemctl reload apache2
```

Useful commands:

```bash
# Is Postfix listening?
ss -lntp | grep ':25'

# Effective configuration
postconf -n

# Live log
sudo tail -f /var/log/mail.log

# Mail queue
mailq

# Retry everything queued
sudo postqueue -f
```

---

## 10. Security notes

* Keep the SMTP VM on a **host-only** network, or firewall port 25 to the
  Docker host only.
* `mynetworks` is an open relay list. Never include `0.0.0.0/0`.
* `everest.local` cannot have a publicly trusted certificate. Do not enable
  STARTTLS with a self-signed certificate unless you also configure Django to
  trust it.
* The SMTP password is encrypted at rest, but anyone with both the database and
  `SECRET_KEY` can decrypt it. Protect both.
* Rotate the password by entering a new one in the UI; leaving the field blank
  keeps the existing value.
* If you later point at a real provider (Gmail, Microsoft 365, SES, Mailgun),
  use STARTTLS on 587 or SSL on 465 and an app-specific password.
