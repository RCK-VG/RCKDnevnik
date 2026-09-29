# Nadzor učeničkih računala

Modul koji s učeničkih računala prima zapise o aktivnosti (instalirani i
pokrenuti programi, nove mape u AppData, nove ikone, promjena pozadine) i veže
ih uz učenika iz e-Dnevnika.

- **Server** je aplikacija `nadzor` unutar Mali e-Dnevnika (ista baza, isti
  Docker). Zapise vidiš u izborniku **Nadzor**.
- **Klijent** je ova mapa: PowerShell skripta koja se na učeničkom računalu
  pokreće pri svakoj prijavi.

> **Važno:** učenik se prijavljuje samo razredom, imenom i prezimenom, bez
> lozinke. Može upisati i kolegu. Zapis zato pokazuje tko se *prijavio*, a ne
> siguran dokaz identiteta: evidencija, ne sigurnosna kontrola.

## Sadržaj mape

| Datoteka | Čemu služi |
|---|---|
| `nadzor.ps1` | glavna skripta (prozor za prijavu, provjere, red čekanja) |
| `pokreni.vbs` | pokreće skriptu bez treptanja crnog prozora |
| `zadatak.ps1` | registrira pokretanje pri svakoj prijavi (koristi ga instalacija) |
| `instaliraj.bat` / `deinstaliraj.bat` | instalacija i uklanjanje na računalu |
| `preskoci_procese.txt` | procesi koji se ne javljaju kao "POKRENUTA APLIKACIJA" |
| `config.example.json` | primjer postavki; pravi `config.json` radi se na serveru |
| `config.json`, `rck-ca.crt` | **generiraš ih sam** (sadrže ključ/certifikat, nisu u gitu) |

---

## 1. Postavljanje na serveru (Raspberry Pi), jednom

### 1.1 Ključ i adresa u `.env`

Na Pi-ju, u mapi `~/dnevnik`, otvori `.env` (`nano .env`) i dodaj:

```
NADZOR_API_KEY=<dugi nasumični niz>
NADZOR_HOST=<IP adresa Pi-ja u školskoj mreži, npr. 192.168.1.50>
```

Ključ generiraj naredbom:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ostale postavke imaju razumne zadane vrijednosti (vidi `.env.example`):
`NADZOR_TOKEN_DAYS=7`, `NADZOR_PRIJAVA_MAX_POKUSAJA=30`.

### 1.2 Pokretanje (uključuje HTTPS na portu 8443)

```bash
git pull
docker compose up -d --build
```

Uz dnevnik se sad pokreće i **Caddy** koji na `https://<NADZOR_HOST>:8443`
poslužuje aplikaciju s vlastitim (internim) certifikatom. Nastavnici i dalje
mogu koristiti stari `http://<IP>:8080`.

Ako Pi ima vatrozid (`ufw`), otvori port: `sudo ufw allow 8443/tcp`.

### 1.3 Pripremi datoteke za računala

```bash
cd ~/dnevnik
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt klijent/rck-ca.crt
docker compose exec -T web python manage.py nadzor_klijent_config --url https://192.168.1.50:8443 > klijent/config.json
```

(Umjesto `192.168.1.50` upiši isti `NADZOR_HOST`.) Naredba uzme ključ iz
`.env`, pa je ključ na jednom mjestu. Ako ga promijeniš, ponovi ovaj korak i
instalaciju na računalima.

Zatim cijelu mapu `klijent` kopiraj na USB (npr. `scp -r` na svoje računalo).

### 1.4 Tko vidi zapise

Admin vidi uvijek. Nastavniku daješ pristup u **Django admin → Korisnici →
(nastavnik)**, pri dnu stranice u dijelu "Profile" uključiš kvačicu
**"Smije vidjeti nadzor računala"** i spremiš.

## 2. Instalacija na učeničko računalo

1. Kopiraj mapu `klijent` (s `config.json` i `rck-ca.crt`) na računalo, npr. na radnu površinu admina.
2. Desni klik na `instaliraj.bat` → **Pokreni kao administrator**.
3. Odjavi se i prijavi (ili prijavi učenika). Pojavi se prozor za prijavu.

Instalacija:
- kopira skriptu u `C:\ProgramData\RCKNadzor`, gdje je učenik smije samo čitati, ne mijenjati,
- uveze `rck-ca.crt` u pouzdane certifikate računala,
- registrira zadatak **"RCK Nadzor"** koji se pokreće pri prijavi svakog korisnika.

Nakon toga mapu s USB-a možeš obrisati s računala.

**Nadogradnja** (nova verzija skripte, promjena ključa ili popisa procesa):
ponovno pokreni `instaliraj.bat`. **Uklanjanje:** `deinstaliraj.bat` kao administrator.

## 3. Što radi na računalu

- Pri prijavi prikaže prozor: razred (padajući izbornik sa servera), ime,
  prezime. Ako učenik ne postoji, javi grešku i pita ponovno. Ako prozor
  zatvori bez prijave, prozor se ponovno pojavi nakon 5 minuta.
- Svakih 60 sekundi provjerava i javlja:
  - `INSTALIRAN PROGRAM` (registry Uninstall ključevi)
  - `NOVA APLIKACIJA (AppData)` (nova mapa u AppData\Roaming, Local ili LocalLow, npr. Roblox)
  - `NOVA IKONA/PRECAC` (radna površina korisnika i zajednička)
  - `PROMJENA POZADINE`
  - `POKRENUTA APLIKACIJA` (svaka aplikacija jednom po prijavi; preskaču se programi iz `C:\Windows` i iz `preskoci_procese.txt`)
- Server sam upiše `PRIJAVA` kad se učenik prijavi.
- "Novo" znači novo u odnosu na ono što je skripta zapamtila na tom
  korisničkom profilu. Pri prvom pokretanju na profilu samo zapamti postojeće
  stanje i ništa ne javlja. Nešto instalirano dok nitko nije bio prijavljen
  javi se pri sljedećoj prijavi, pod učenikom koji se tada prijavio.
- **Ako server ne radi**, zapisi se spremaju u `%LOCALAPPDATA%\RCKNadzor\red.jsonl`
  i šalju čim proradi, s točnim vremenom kad su se dogodili.

Dnevnik skripte (za rješavanje problema): `%LOCALAPPDATA%\RCKNadzor\nadzor.log`.

## 4. Proba bez učeničkog računala (curl, na Pi-ju)

```bash
cd ~/dnevnik
KLJUC=$(grep ^NADZOR_API_KEY .env | cut -d= -f2-)
URL=https://192.168.1.50:8443/api/nadzor/v1

# popis razreda
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" $URL/razredi/

# prijava učenika -> vrati token
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"razred":"1.C","ime":"Luka","prezime":"Čolić","racunalo":"ROBOTIKA5"}' $URL/prijava/

# jedan zapis (TOKEN iz prethodnog odgovora)
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"token":"TOKEN","racunalo":"ROBOTIKA5","vrsta":"INSTALIRAN PROGRAM","detalji":"Roblox"}' $URL/zapisi/

# više zapisa odjednom (tako klijent šalje red čekanja)
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"token":"TOKEN","racunalo":"ROBOTIKA5","zapisi":[{"vrsta":"POKRENUTA APLIKACIJA","detalji":"RobloxPlayerBeta","vrijeme":"2026-09-29T08:05:00+02:00"}]}' $URL/zapisi/
```

Odgovori: `200` prijava uspjela, `201` zapisi primljeni, `400` neispravan
zahtjev, `401` token neispravan ili istekao, `403` krivi ključ, `404` učenik
nije pronađen, `409` dva učenika istog imena u razredu, `429` previše
neuspjelih prijava, `503` ključ nije postavljen na serveru.

Skriptu možeš probati i na običnom računalu, bez instalacije i bez prozora:

```powershell
powershell -ExecutionPolicy Bypass -File .\nadzor.ps1 -Razred 1.C -Ime Luka -Prezime Čolić -JednomProvjeri
```

## 5. Čuvanje i brisanje zapisa

Zapisi se **ne brišu automatski**. Brišeš ih ručno: Django admin → Nadzor
računala → Zapisi aktivnosti → označi → akcija "Delete". U
`nadzor/models.py` je komentar gdje bi se kasnije dodalo brisanje po roku.

Pazi na prostor na SD kartici: baza raste sa zapisima, a dnevni backup čuva
`BACKUP_KEEP` (zadano 14) cijelih kopija baze. Po potrebi smanji `BACKUP_KEEP`.

## 6. Na što treba paziti

- **API ključ nije prava tajna.** Skripta radi pod učeničkim računom, pa
  učenik može pročitati `config.json` (samo ga ne može mijenjati). Ključ zato
  omogućuje samo popis razreda, prijavu i slanje zapisa, nikad čitanje
  zapisa. Tko ga zna, može slati lažne zapise.
- **Certifikat:** `rck-ca.crt` je korijenski certifikat Caddyja na Pi-ju i
  računala mu vjeruju. Čuvaj Pi (lozinke, ažuriranja), jer tko preuzme Pi
  mogao bi izdavati certifikate kojima ta računala vjeruju.
- **Obavijest učenicima:** prozor za prijavu kaže da se aktivnost bilježi.
  Neka to škola ima i u pravilima korištenja računala.
